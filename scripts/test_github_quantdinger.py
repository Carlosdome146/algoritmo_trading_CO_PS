"""Auditoría y Backtesting de las Estrategias de OpenByteInc/QuantDinger.

Prueba 2 estrategias extraídas de QuantDinger:
1. QuantDinger_MTF_Cross (M15 MA10xMA30 con filtro macro H1)
2. QuantDinger_Keltner_Reversion (Canales de Keltner 20/10/2.0x con filtro SMA200)

Ejecuta sobre datos reales de MT5 (hasta 99.999 barras: 4.5 a 8.9 años) y
actualiza automáticamente el Cuadro Maestro CUADRO_ESTRATEGIAS_INTRADIA.md.
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trading_v2.backtesting.intraday_engine import (
    SESSION_UTC,
    add_h1_trend,
    add_base_indicators,
)
from trading_v2.strategies.github_imports.quantdinger_strategies import (
    generate_quantdinger_mtf_cross_signals,
    generate_quantdinger_keltner_signals,
    compute_quantdinger_keltner,
)
from scripts.backtest_strategy import (
    fetch_symbol_bars,
    simulate_backtest,
    update_dashboard_markdown,
)


def run_quantdinger_audit():
    print("=" * 100)
    print("AUDITORÍA DE REPOSITORIO GITHUB: OpenByteInc/QuantDinger")
    print("Criterios de Carlos: Win Rate > 70% | Max DD < 5% | M15 / M30 | Costes reales MT5")
    print("=" * 100)
    print(f"{'ESTRATEGIA':<24} | {'ACTIVO':<10} | {'TF':<4} | {'N':<6} | {'WIN RATE':<9} | {'PF':<6} | {'MaxDD%':<7} | {'E[R]':<8} | {'ESTADO':<15}")
    print("-" * 100)

    assets = ["GERMANY40", "[SP500]", "US100", "EURUSD"]
    timeframes = [("M30", mt5.TIMEFRAME_M30), ("M15", mt5.TIMEFRAME_M15)]

    strategies = [
        ("QuantDinger_MTF_Cross", generate_quantdinger_mtf_cross_signals, True),
        ("QuantDinger_Keltner_Reversion", generate_quantdinger_keltner_signals, False),
    ]

    results = []

    for strat_name, sig_fn, needs_h1 in strategies:
        for sym in assets:
            session = SESSION_UTC.get(sym, (7, 17))
            for tf_str, tf_code in timeframes:
                try:
                    df = fetch_symbol_bars(sym, tf_code, 99999)
                    df = add_base_indicators(df)
                    if needs_h1:
                        df = add_h1_trend(df, sym)

                    signals = sig_fn(df)

                    # Salida dinámica por EMA o Take Profit
                    res = simulate_backtest(
                        df=df,
                        symbol=sym,
                        signals=signals,
                        stop_atr=2.0,
                        tp_atr=1.5,
                        dynamic_exit_ema=9,
                        session_start_h=session[0],
                        session_end_h=session[1],
                    )
                    res["strategy_name"] = strat_name
                    res["symbol"] = sym
                    res["timeframe"] = tf_str

                    status_str = "APROBADA" if "PASS" in res["verdict"] else "DESCARTADA"
                    print(f"{strat_name:<24} | {sym:<10} | {tf_str:<4} | {res['n']:<6} | {res['wr']:<8.1f}% | {res['pf']:<6.2f} | {res['max_dd_pct']:<6.2f}% | {res['mean_r']:+7.4f} | {status_str}")

                    update_dashboard_markdown(res)
                    results.append(res)
                except Exception as e:
                    print(f"{strat_name:<24} | {sym:<10} | {tf_str:<4} | ERROR: {e}")

    print("=" * 100)
    mt5.shutdown()
    return results


if __name__ == "__main__":
    run_quantdinger_audit()
