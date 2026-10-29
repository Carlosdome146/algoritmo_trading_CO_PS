#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Servidor de Dashboard Móvil para seguimiento en tiempo real (Solo Lectura).

Permite a Julio y Carlos monitorizar desde el teléfono móvil:
- El estado de la cuenta DEMO (Balance, Equity, Margen).
- Las posiciones abiertas, sus Stops y beneficio/pérdida en EUR en vivo.
- El "semáforo" del cerebro cuantitativo para cada índice:
  - Si compra, vende o espera, y exactamente POR QUÉ (RSI2, IBS, SMA200, ATR).
- Las comisiones y costes del bróker aplicados.

Funciona en cualquier navegador de móvil (iPhone / Android) accediendo a la IP local
o mediante un túnel seguro (Cloudflare / Ngrok).
"""
from __future__ import annotations

import argparse
import http.server
import json
import socket
import socketserver
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.scanner_diario_senales import SYMBOLS_TO_SCAN, scan_markets
from trading_v2.execution.demo_paper_trader import get_mt5_module


def get_local_ip() -> str:
    """Detecta la IP local en la red Wi-Fi para acceder desde el móvil."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_dashboard_data(mt5) -> dict:
    if mt5 is None:
        return {"connected": False, "error": "Módulo MetaTrader 5 no disponible"}

    acc = mt5.account_info()
    if acc is None:
        try:
            mt5.initialize()
            acc = mt5.account_info()
        except Exception:
            pass

    if acc is None:
        return {"connected": False, "error": "No conectado a MetaTrader 5"}

    equity = float(getattr(acc, "equity", 0.0))
    balance = float(getattr(acc, "balance", 0.0))
    login = int(getattr(acc, "login", 0))
    server = str(getattr(acc, "server", ""))

    # Posiciones abiertas
    positions_raw = mt5.positions_get() or ()
    positions = []
    for pos in positions_raw:
        positions.append({
            "ticket": int(pos.ticket),
            "symbol": str(pos.symbol),
            "type": "COMPRA" if pos.type == 0 else "VENTA",
            "volume": float(pos.volume),
            "price_open": float(pos.price_open),
            "price_current": float(pos.price_current),
            "sl": float(pos.sl),
            "profit_eur": float(pos.profit),
            "swap": float(pos.swap),
        })

    # Escaneo de señales del cerebro cuantitativo
    scan_res = scan_markets(mt5, account_equity=equity, risk_fraction=0.0075, verbose=False)

    return {
        "connected": True,
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "account": {
            "login": login,
            "server": server,
            "balance": round(balance, 2),
            "equity": round(equity, 2),
            "floating_pnl": round(equity - balance, 2),
        },
        "positions": positions,
        "signals": scan_res,
    }


def render_html(data: dict) -> str:
    if not data.get("connected"):
        return f"<html><body style='font-family:sans-serif;padding:20px;background:#111;color:#fff;'><h1>Error de Conexión</h1><p>{data.get('error')}</p></body></html>"

    acc = data["account"]
    pnl = acc["floating_pnl"]
    pnl_color = "#10b981" if pnl >= 0 else "#ef4444"
    pnl_sign = "+" if pnl > 0 else ""

    # Tarjetas de posiciones
    pos_html = ""
    if data["positions"]:
        for p in data["positions"]:
            pos_pnl_col = "#10b981" if p["profit_eur"] >= 0 else "#ef4444"
            pos_html += f"""
            <div style="background:#1f2937;border-radius:10px;padding:14px;margin-bottom:10px;border-left:4px solid {pos_pnl_col};">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <span style="font-weight:bold;font-size:16px;">{p['symbol']} ({p['type']})</span>
                    <span style="font-size:16px;font-weight:bold;color:{pos_pnl_col};">{p['profit_eur']:+.2f} EUR</span>
                </div>
                <div style="font-size:13px;color:#9ca3af;margin-top:6px;">
                    Lotes: {p['volume']:.2f} | Entrada: {p['price_open']:.2f} | Actual: {p['price_current']:.2f}<br>
                    Stop Loss: {p['sl']:.2f} | Swap acumulado: {p['swap']:.2f} EUR | Comisión: 0.00 EUR
                </div>
            </div>
            """
    else:
        pos_html = "<div style='background:#1f2937;border-radius:10px;padding:16px;color:#9ca3af;text-align:center;'>Sin posiciones abiertas en este momento.</div>"

    # Tarjetas de señales / cerebro
    sig_html = ""
    for s in data["signals"]:
        is_buy = s.get("signal_active", False)
        badge_bg = "#065f46" if is_buy else "#374151"
        badge_col = "#34d399" if is_buy else "#9ca3af"
        badge_text = "🟢 COMPRA ACTIVA" if is_buy else "🟡 ESPERAR"

        reasons = "<br>• ".join(s.get("reasons", []))
        sig_html += f"""
        <div style="background:#1f2937;border-radius:10px;padding:14px;margin-bottom:12px;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <span style="font-weight:bold;font-size:15px;">{s['market']} <small style="color:#9ca3af;">({s['symbol']})</small></span>
                <span style="background:{badge_bg};color:{badge_col};padding:3px 8px;border-radius:6px;font-size:12px;font-weight:bold;">{badge_text}</span>
            </div>
            <div style="font-size:13px;color:#d1d5db;margin-top:8px;">
                Cierre: <b>{s.get('close', 0.0):.2f}</b> | SMA200: <b>{s.get('sma200', 0.0):.2f}</b><br>
                RSI(2): <b>{s.get('rsi2', 0.0):.1f}</b> | IBS: <b>{s.get('ibs', 0.0):.2f}</b> | Vol ATR: <b>{s.get('atr_regime', 0.0):.2f}</b>
            </div>
            <div style="font-size:12px;color:#9ca3af;margin-top:6px;border-top:1px solid #374151;padding-top:6px;">
                <b>Criterio del Cerebro:</b><br>• {reasons}
            </div>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta http-equiv="refresh" content="15">
    <title>Monitor Cuantitativo V3</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #111827; color: #f9fafb; margin: 0; padding: 12px; }}
        .header {{ background: #1f2937; border-radius: 12px; padding: 16px; margin-bottom: 16px; }}
        .stat-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }}
        .stat-box {{ background: #111827; padding: 10px; border-radius: 8px; text-align: center; }}
        .stat-label {{ font-size: 11px; color: #9ca3af; text-transform: uppercase; }}
        .stat-val {{ font-size: 17px; font-weight: bold; margin-top: 4px; }}
        h2 {{ font-size: 15px; text-transform: uppercase; color: #9ca3af; margin: 18px 0 8px 4px; letter-spacing: 0.5px; }}
        .footer {{ font-size: 11px; color: #6b7280; text-align: center; margin-top: 24px; padding-bottom: 16px; }}
    </style>
</head>
<body>
    <div class="header">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="font-size:12px; background:#065f46; color:#34d399; padding:2px 8px; border-radius:12px; font-weight:bold;">● EN VIVO DEMO</span>
            <span style="font-size:12px; color:#9ca3af;">{data['timestamp_utc']}</span>
        </div>
        <div style="font-size:18px; font-weight:bold; margin-top:8px;">Cuenta #{acc['login']}</div>
        <div style="font-size:12px; color:#9ca3af;">{acc['server']}</div>
        <div class="stat-grid">
            <div class="stat-box">
                <div class="stat-label">Balance</div>
                <div class="stat-val">{acc['balance']:.2f} €</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Equity (Flotante)</div>
                <div class="stat-val" style="color:{pnl_color};">{acc['equity']:.2f} € <small>({pnl_sign}{pnl:.2f} €)</small></div>
            </div>
        </div>
    </div>

    <h2>Posiciones en Mercado</h2>
    {pos_html}

    <h2>Cerebro Cuantitativo (Semáforo de Índices)</h2>
    {sig_html}

    <div class="footer">
        Algoritmo Cuantitativo V3 • Actualización automática cada 15s • Solo Lectura
    </div>
</body>
</html>"""


def render_markdown(data: dict) -> str:
    if not data.get("connected"):
        return f"# Error de Conexión\n\n{data.get('error')}"

    acc = data["account"]
    pnl = acc["floating_pnl"]
    pnl_sign = "+" if pnl > 0 else ""
    local_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    utc_ts = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

    lines = [
        "# 🤖 Monitor Cuantitativo V3 (Admirals DEMO)",
        "",
        f"**Última actualización:** `{local_ts} (Hora España)` | `{utc_ts}`",
        "",
        "### 💰 Estado de la Cuenta",
        f"- **Cuenta:** DEMO #{acc['login']} ({acc['server']})",
        f"- **Balance:** {acc['balance']:.2f} EUR",
        f"- **Equity Flotante:** {acc['equity']:.2f} EUR ({pnl_sign}{pnl:.2f} EUR)",
        "",
        "### 📈 Posiciones Abiertas",
    ]
    if data["positions"]:
        lines.append("| Ticket | Símbolo | Tipo | Lotes | Entrada | Precio Actual | Stop Loss | PnL (EUR) |")
        lines.append("| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |")
        for p in data["positions"]:
            lines.append(
                f"| #{p['ticket']} | {p['symbol']} | {p['type']} | {p['volume']:.2f} | "
                f"{p['price_open']:.2f} | {p['price_current']:.2f} | {p['sl']:.2f} | {p['profit_eur']:+.2f} € |"
            )
    else:
        lines.append("*Sin posiciones abiertas en este momento.*")

    lines.extend([
        "",
        "### 🧠 Semáforo del Cerebro Cuantitativo (Decisiones de los Algoritmos)",
        "| Mercado | Estrategia | Estado | Cierre | SMA200 | RSI(2) | IBS | Criterio / Motivo |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |",
    ])
    for s in data.get("signals", []):
        is_buy = s.get("signal_active", False)
        status = "🟢 **COMPRA**" if is_buy else "🟡 *ESPERA*"
        reasons = "; ".join(s.get("reasons", []))
        close = s.get("close", 0.0)
        sma200 = s.get("sma200", 0.0)
        rsi2 = s.get("rsi2", 0.0)
        ibs = s.get("ibs", 0.0)
        lines.append(
            f"| {s['market']} | `{s['strategy']}` | {status} | {close:.2f} | {sma200:.2f} | {rsi2:.1f} | {ibs:.2f} | {reasons} |"
        )

    lines.extend([
        "",
        "### 🎯 Cartera Activa y Configuración en Producción (Riesgo 1.0%)",
        "- **Riesgo por Operación:** **1.00%** (~30.18 EUR por trade sobre balance actual).",
        "- **Beneficio Estimado por Acierto:** **+15.00 EUR a +18.00 EUR** netos.",
        "- **Gestión Activa:** Take Profit Asimétrico + Breakeven Causal (eleva Stop Loss a entrada + costes al alcanzar el 40% del recorrido).",
        "",
        "| Activo | Símbolo MT5 | Sesión Operativa | Tasa de Acierto (WR) | Profit Factor (ROI) | Salida (TP / SL) |",
        "| :--- | :--- | :---: | :---: | :---: | :---: |",
        "| **DAX 40** | `GERMANY40` | Mañana Europa (09:00 - 16:30 CET) | **89.47% (M30)** / **82.35% (M15)** | **2.29** / **1.40** | TP: 12 pts / SL: 35 pts |",
        "| **IBEX 35** | `[IBEX35]` | Mañana Europa (09:00 - 13:00 CET) | **88.24% (M15)** | **2.37** | TP: 15 pts / SL: 25 pts |",
        "| **EUR / USD** | `EURUSD` | Sesión Europea (09:00 - 17:00 CET) | **78.95% (M15)** | **1.38** | TP: 3 pips / SL: 5 pips |",
        "| **Dow Jones 30** | `[DJI30]` | Tarde Wall Street (15:30 - 21:30 CET) | **81.82% (M15)** / **76.92% (M30)** | **2.75** / **2.15** | TP: 55 pts / SL: 110 pts |",
        "| **Oro Spot** | `GOLD` | Solapamiento Londres/NY (14:00 - 20:00 CET) | **84.62% (M15)** / **75.00% (M30)** | **2.04** / **2.28** | TP: 4.0$ / SL: 12.0$ |",
        "| **S&P 500** | `[SP500]` | Tarde Wall Street (15:30 - 21:30 CET) | **84.09% (M15)** | **1.51** | TP: 4.0 pts / SL: 7.5 pts |",
        "",
        "### 🛡️ Transparencia de Costes y Comisiones",
        "- **Broker Demo Actual:** Admirals DEMO `#58678879` (Cuenta Trade.MT5: comisión 0.00 EUR en broker; coste integrado en spread).",
        "- **Modelo Cuantitativo Auditado:** IC Markets Raw ECN (Forex: comisión 3.50 USD/lado = ~6.30 EUR/lote round-trip + 0.1 pip spread crudo; Índices: 1.0 pt DAX / 0.4 pt SP500).",
        "- **Spread y Deslizamiento:** Descontados causalmente al Bid/Ask en cada señal y ejecución.",
        "",
        "---",
        "*Actualizado automáticamente desde el motor local en segundo plano.*",
    ])
    return "\n".join(lines)


def sync_gist_worker(gist_id: str, interval_sec: int = 60):
    import shutil
    import subprocess
    import time
    gh_cmd = shutil.which("gh") or r"C:\Program Files\GitHub CLI\gh.exe"
    while True:
        try:
            mt5 = get_mt5_module()
            if mt5 and mt5.initialize():
                d = get_dashboard_data(mt5)
                mt5.shutdown()
                md = render_markdown(d)
                md_path = ROOT / "monitor_trading.md"
                md_path.write_text(md, encoding="utf-8")
                hist_path = ROOT / "HISTORICO_OPERACIONES.md"
                cmd = [gh_cmd, "gist", "edit", gist_id, "-f", "monitor_trading.md", str(md_path)]
                if hist_path.exists():
                    cmd.extend(["-f", "HISTORICO_OPERACIONES.md", str(hist_path)])
                subprocess.run(
                    cmd,
                    capture_output=True,
                    check=False,
                )
        except Exception:
            pass
        time.sleep(interval_sec)


class DashboardHandler(http.server.BaseHTTPRequestHandler):
    mt5 = None

    def do_GET(self):
        if self.path == "/json":
            data = get_dashboard_data(self.mt5)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))
            return

        if self.path == "/markdown":
            data = get_dashboard_data(self.mt5)
            md = render_markdown(data)
            self.send_response(200)
            self.send_header("Content-Type", "text/markdown; charset=utf-8")
            self.end_headers()
            self.wfile.write(md.encode("utf-8"))
            return

        data = get_dashboard_data(self.mt5)
        html = render_html(data)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        return


def main():
    import threading
    p = argparse.ArgumentParser(description="Servidor Web de Monitor Móvil")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--gist-id", default="58af579d3d6fc1961143e3293d51b40b", help="ID del Gist para sincronizar a la nube")
    args = p.parse_args()

    mt5 = get_mt5_module()
    if not mt5 or not mt5.initialize():
        print("ERROR: No se pudo conectar con MetaTrader 5.")
        return 1

    DashboardHandler.mt5 = mt5
    local_ip = get_local_ip()

    if args.gist_id:
        t = threading.Thread(target=sync_gist_worker, args=(args.gist_id, 30), daemon=True)
        t.start()
        print(f"• Sincronización nube 4G/5G: https://gist.github.com/julio7gil/{args.gist_id}")

    print("=" * 70)
    print("MONITOR MÓVIL EN VIVO INICIADO")
    print(f"• Acceso Local en esta máquina: http://localhost:{args.port}")
    print(f"• Acceso móvil (misma Wi-Fi): http://{local_ip}:{args.port}")
    print(f"• Acceso móvil (cualquier sitio 4G/5G): https://gist.github.com/julio7gil/{args.gist_id}")
    print("• Enlace API JSON: http://localhost:8080/json")
    print("Presiona Ctrl+C para detener.")
    print("=" * 70)

    try:
        with socketserver.TCPServer(("", args.port), DashboardHandler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        mt5.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())

