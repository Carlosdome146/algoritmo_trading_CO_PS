"""Auditoría y Backtesting de la Estrategia Técnica de TauricResearch/TradingAgents.

Ejecuta el backtest en M15 y M30 sobre datos históricos reales de MetaTrader 5
(hasta 8.5 años) y actualiza automáticamente el cuadro de mando maestro.
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
    POINT,
    COST_PER_LOT,
    CAPITAL_BASE,
    wilson_lower_bound,
)
from trading_v2.strategies.github_imports.tradingagents_technical import (
    compute_tradingagents_indicators,
    generate_tradingagents_signals,
)
from scripts.backtest_strategy import (
    fetch_symbol_bars,
    simulate_backtest,
    update_dashboard_markdown,
)


def run_audit():
    print("=" * 95)
    print("EVALUACIÓN DE REPOSITORIO GITHUB: TauricResearch/TradingAgents")
    print("Estrategia: TradingAgents Technical Confluence (EMA10 + SMA50 + SMA200 + MACD + RSI14 + Bollinger)")
    print("Criterios de Carlos: Win Rate > 70% | Max DD < 5% | M15 / M30 | Costes reales MT5")
    print("=" * 95)
    print(f"{'ACTIVO':<10} | {'TF':<4} | {'N TRADES':<8} | {'WIN RATE':<9} | {'W-LB':<7} | {'PF':<6} | {'MaxDD%':<7} | {'E[R]':<8} | {'ESTADO':<15}")
    print("-" * 95)

    assets = ["GERMANY40", "[SP500]", "US100", "EURUSD"]
    timeframes = [("M30", mt5.TIMEFRAME_M30), ("M15", mt5.TIMEFRAME_M15)]

    results = []

    for sym in assets:
        session = SESSION_UTC.get(sym, (7, 17))
        for tf_str, tf_code in timeframes:
            try:
                df = fetch_symbol_bars(sym, tf_code, 99999)
                df = compute_tradingagents_indicators(df)
                df["hour_utc"] = df.index.hour
                df["weekday"] = df.index.weekday

                signals = generate_tradingagents_signals(df)

                # Probamos con SL dinámico a 2.0 ATR y TP a 1.5 ATR (o trailing)
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
                res["strategy_name"] = "TradingAgents_Technical_Confluence"
                res["symbol"] = sym
                res["timeframe"] = tf_str

                status_str = "APROBADA" if "PASS" in res["verdict"] else "DESCARTADA"
                print(f"{sym:<10} | {tf_str:<4} | {res['n']:<8} | {res['wr']:<8.1f}% | {res['wilson_lb']:<6.1f}% | {res['pf']:<6.2f} | {res['max_dd_pct']:<6.2f}% | {res['mean_r']:+7.4f} | {status_str}")
                
                # Actualizar el dashboard
                update_dashboard_markdown(res)
                results.append(res)
            except Exception as e:
                print(f"{sym:<10} | {tf_str:<4} | ERROR: {e}")

    print("=" * 95)
    mt5.shutdown()
    return results


if __name__ == "__main__":
    run_audit()
