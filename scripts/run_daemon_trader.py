"""Supervisor Desatendido con Auto-Sync de GitHub para MetaTrader 5.

Funcionalidad:
1. Ejecuta el bot de trading demo_paper_trader en vivo con la estrategia institucional sniper scalp.
2. Cada 5 minutos comprueba si Julio o Carlos han hecho nuevos commits en origin/main en GitHub.
3. Si detecta cambios, realiza git pull origin main y reinicia limpiamente el proceso del bot
   para cargar en caliente las nuevas mejoras sin intervención manual.
4. Redirige y mantiene logs limpios en daemon_trading.log.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
LOG_FILE = BASE_DIR / "daemon_trading.log"


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] [SUPERVISOR] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def get_commit_hash(ref: str) -> str:
    try:
        res = subprocess.run(
            ["git", "rev-parse", ref],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception as e:
        log(f"Error comprobando commit para {ref}: {e}")
        return ""


def git_fetch():
    try:
        subprocess.run(
            ["git", "fetch", "origin", "main"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as e:
        log(f"Error en git fetch: {e}")


def git_pull() -> bool:
    try:
        res = subprocess.run(
            ["git", "pull", "--rebase", "origin", "main"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=45,
        )
        log(f"Git pull ejecutado:\n{res.stdout.strip()}")
        return res.returncode == 0
    except Exception as e:
        log(f"Error en git pull: {e}")
        return False


def start_bot_process() -> subprocess.Popen:
    cmd = [
        sys.executable,
        "-u",
        "-m",
        "trading_v2.execution.demo_paper_trader",
        "--live",
        "--strategy",
        "institutional_sniper_scalp",
        "--timeframe",
        "M15_M30",
        "--symbols",
        "GERMANY40",
        "[SP500]",
        "US100",
        "[DJI30]",
        "GOLD",
        "--risk-fraction",
        "0.0100",
        "--max-concurrent-indices",
        "2",
        "--max-european-indices",
        "1",
        "--max-us-indices",
        "1",
        "--runner-ratio",
        "0.30",
        "--poll-seconds",
        "15.0",
        "--reset-risk-pause",
    ]
    log(f"Iniciando proceso del bot: {' '.join(cmd[1:])}")
    
    # Abrir log file para stdout/stderr del bot
    f_log = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
    proc = subprocess.Popen(
        cmd,
        cwd=BASE_DIR,
        stdout=f_log,
        stderr=subprocess.STDOUT,
    )
    return proc


def stop_bot_process(proc: subprocess.Popen):
    if proc.poll() is None:
        log(f"Deteniendo bot (PID {proc.pid})...")
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            log("Forzando cierre con kill...")
            proc.kill()
            proc.wait(timeout=5)
        log("Bot detenido con éxito.")


def main():
    log("Iniciando Supervisor Desatendido de Trading con Auto-Sync GitHub...")
    proc = start_bot_process()
    last_check_time = time.time()
    CHECK_INTERVAL = 300  # cada 5 minutos

    try:
        while True:
            time.sleep(10)
            
            # Verificar si el proceso del bot cayó inesperadamente
            if proc.poll() is not None:
                rc = proc.returncode
                log(f"ALERTA: El bot se detuvo con código {rc}. Reiniciando en 5 segundos...")
                time.sleep(5)
                proc = start_bot_process()

            # Comprobar actualizaciones de GitHub periódicamente
            now = time.time()
            if now - last_check_time >= CHECK_INTERVAL:
                last_check_time = now
                log("Comprobando actualizaciones en GitHub (origin/main)...")
                git_fetch()
                local_head = get_commit_hash("HEAD")
                remote_head = get_commit_hash("origin/main")
                
                if local_head and remote_head and local_head != remote_head:
                    # Comprobar si hay cambios en archivos ejecutables de código (.py, .bat)
                    diff_res = subprocess.run(
                        ["git", "diff", "--name-only", local_head, remote_head],
                        cwd=BASE_DIR,
                        capture_output=True,
                        text=True,
                    )
                    changed_files = diff_res.stdout.splitlines()
                    code_changed = any(f.endswith(".py") or f.endswith(".bat") for f in changed_files)

                    if code_changed:
                        log(f"NUEVA ACTUALIZACIÓN DE CÓDIGO DETECTADA ({local_head[:7]} -> {remote_head[:7]}). Reiniciando bot...")
                        stop_bot_process(proc)
                        if git_pull():
                            log("Código actualizado con éxito. Reiniciando bot con la nueva versión...")
                        else:
                            log("Fallo al actualizar código. Reiniciando con versión actual...")
                        proc = start_bot_process()
                    else:
                        log(f"Actualización de documentación/logs ({local_head[:7]} -> {remote_head[:7]}). Sincronizando sin reiniciar el bot...")
                        git_pull()
                else:
                    log(f"El bot está al día con GitHub (Commit: {local_head[:7]}).")

    except KeyboardInterrupt:
        log("Interrupción por usuario. Cerrando todo...")
        stop_bot_process(proc)
    except Exception as e:
        log(f"Error fatal en supervisor: {e}")
        stop_bot_process(proc)


if __name__ == "__main__":
    main()
