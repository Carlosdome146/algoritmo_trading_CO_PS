"""Auditoría y Backtesting de Estrategias de brainbrick-trades/The-Quant-Trading-Vault.

Prueba 3 estrategias extraídas de The Quant Trading Vault:
1. Vault_BB_VWAP_Anomaly
2. Vault_Connors_RSI2_Reversal
3. Vault_Consecutive_Candle_Reversal

Ejecuta sobre datos reales de MT5 (hasta 99.999 barras: 4.5 a 8.9 años) y
evalúa estrictamente contra los criterios de Carlos:
- Win Rate >= 70.0%
- Max Drawdown < 5.0%
- E[R] > 0 y PF > 1.25
- Muestra N >= 100
"""
from __future__ import annotations

import os
import sys

# Forzar codificación UTF-8 en stdout para Windows cmd/powershell
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from pathlib import Path
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from trading_v2.backtesting.intraday_engine import (
    SESSION_UTC,
    add_base_indicators,
)
from trading_v2.strategies.github_imports.the_quant_vault_strategies import (
    generate_vault_bb_vwap_signals,
    generate_vault_connors_rsi2_signals,
    generate_vault_consecutive_candle_signals,
)
from scripts.backtest_strategy import (
    fetch_symbol_bars,
    simulate_backtest,
)

DASHBOARD_MD_PATH = BASE_DIR / "CUADRO_ESTRATEGIAS_INTRADIA.md"


def run_the_quant_vault_audit():
    print("=" * 110)
    print("AUDITORÍA DE REPOSITORIO GITHUB: brainbrick-trades/The-Quant-Trading-Vault")
    print("Criterios de Carlos: Win Rate > 70% | Max DD < 5% | M15 / M30 | Costes reales MT5")
    print("=" * 110)
    print(f"{'ESTRATEGIA':<35} | {'ACTIVO':<10} | {'TF':<4} | {'N':<6} | {'WIN RATE':<9} | {'PF':<6} | {'MaxDD%':<7} | {'E[R]':<8} | {'ESTADO':<15}")
    print("-" * 110)

    assets = ["GERMANY40", "[SP500]", "US100", "EURUSD", "GOLD"]
    timeframes = [("M30", mt5.TIMEFRAME_M30), ("M15", mt5.TIMEFRAME_M15)]

    strategies = [
        ("Vault_BB_VWAP_Anomaly", generate_vault_bb_vwap_signals, 1.5, 9, 65.0),
        ("Vault_Connors_RSI2_Reversal", generate_vault_connors_rsi2_signals, 1.5, 9, 70.0),
        ("Vault_Consecutive_Candle_Reversal", generate_vault_consecutive_candle_signals, 1.5, 9, 65.0),
    ]

    all_results = []

    for strat_name, sig_fn, stop_atr, dyn_ema, dyn_rsi in strategies:
        for sym in assets:
            session = SESSION_UTC.get(sym, (7, 17))
            for tf_str, tf_code in timeframes:
                try:
                    df = fetch_symbol_bars(sym, tf_code, 99999)
                    df = add_base_indicators(df)
                    signals = sig_fn(df)

                    res = simulate_backtest(
                        df=df,
                        symbol=sym,
                        signals=signals,
                        stop_atr=stop_atr,
                        tp_atr=None,
                        dynamic_exit_ema=dyn_ema,
                        dynamic_exit_rsi=dyn_rsi,
                        use_breakeven=True,
                        be_trigger_atr=0.40,
                        be_lock_atr=0.05,
                        session_start_h=session[0],
                        session_end_h=session[1],
                    )
                    res["strategy_name"] = strat_name
                    res["symbol"] = sym
                    res["timeframe"] = tf_str

                    estado = "[APROBADA]" if "PASS" in res["verdict"] else "[DESCARTADA]"
                    print(
                        f"{strat_name:<35} | {sym:<10} | {tf_str:<4} | {res['n']:<6} | "
                        f"{res['wr']:<8.1f}% | {res['pf']:<6.2f} | {res['max_dd_pct']:<6.2f}% | "
                        f"{res['mean_r']:<+7.4f} | {estado:<15}"
                    )
                    all_results.append(res)
                except Exception as e:
                    print(f"Error testeando {strat_name} en {sym} {tf_str}: {e}")

    return all_results


def append_to_dashboard(results: list[dict]):
    if not DASHBOARD_MD_PATH.exists():
        print("No se encontró CUADRO_ESTRATEGIAS_INTRADIA.md")
        return

    content = DASHBOARD_MD_PATH.read_text(encoding="utf-8")
    
    # Si ya existía una ronda 5 parcial, limpiarla antes de escribir la completa
    marker_start = "### 🔴 Ronda 5: Evaluación brainbrick-trades/The-Quant-Trading-Vault"
    marker_end = "## 🛠️ Cómo Probar Estrategias de Repositorios de GitHub"
    if marker_start in content and marker_end in content:
        p1 = content.split(marker_start)[0]
        p2 = content.split(marker_end)[1]
        content = p1 + marker_end + p2

    section_header = "### 🔴 Ronda 5: Evaluación brainbrick-trades/The-Quant-Trading-Vault (GitHub)\n"
    section_header += "> **Fuente:** https://github.com/brainbrick-trades/The-Quant-Trading-Vault  \n"
    section_header += "> **Lógicas Evaluadas:**  \n"
    section_header += "> 1. `Vault_BB_VWAP_Anomaly`: Tendencia EMA50>200 + VWAP + anomalía de precio bajo Bollinger Bands (20, 2.0).  \n"
    section_header += "> 2. `Vault_Connors_RSI2_Reversal`: Connors RSI(2) < 10 con filtro SMA200 y salida dinámica por EMA9.  \n"
    section_header += "> 3. `Vault_Consecutive_Candle_Reversal`: Reversión de 3 velas bajistas con mecha de absorción a favor de EMA200.  \n\n"
    section_header += "| Fecha | Estrategia / Fuente | Activo | TF | N | Win Rate | PF | Max DD | E[R] | Estado | Diagnóstico / Motivo del Descarte |\n"
    section_header += "| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |\n"

    rows = []
    for r in results:
        status_icon = "🟢 APROBADA" if "PASS" in r["verdict"] else "🔴 DESCARTADA"
        reason = "CUMPLE TODOS LOS CRITERIOS" if "PASS" in r["verdict"] else "; ".join(r["fail_reasons"])
        row = (
            f"| 2026-11-03 | {r['strategy_name']} | {r['symbol']} | {r['timeframe']} | "
            f"{r['n']} | **{r['wr']:.1f}%** | {r['pf']:.2f} | {r['max_dd_pct']:.2f}% | "
            f"{r['mean_r']:+.4f} | {status_icon} | {reason} |\n"
        )
        rows.append(row)

    new_section = section_header + "".join(rows) + "\n---\n\n"
    
    if marker_end in content:
        parts = content.split(marker_end)
        updated_content = parts[0] + new_section + marker_end + parts[1]
    else:
        updated_content = content + "\n" + new_section

    DASHBOARD_MD_PATH.write_text(updated_content, encoding="utf-8")
    print(f"\n[DASHBOARD ACTUALIZADO CON ÉXITO] -> {DASHBOARD_MD_PATH.name}")


def main():
    if not mt5.initialize():
        print("MT5 init failed")
        return

    results = run_the_quant_vault_audit()
    append_to_dashboard(results)

    mt5.shutdown()


if __name__ == "__main__":
    main()
