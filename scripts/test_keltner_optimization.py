"""Optimización Cuantitativa de la Estrategia Keltner de QuantDinger (M15).

Objetivo:
- Mantener el Win Rate > 70% (observado 71.7% en SP500)
- Reducir el Max Drawdown de 6.13% a < 5.0%
- Elevar el Profit Factor de 1.07 a > 1.25
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trading_v2.backtesting.intraday_engine import add_base_indicators, SESSION_UTC, CAPITAL_BASE
from trading_v2.strategies.github_imports.quantdinger_strategies import compute_quantdinger_keltner
from scripts.backtest_strategy import fetch_symbol_bars, simulate_backtest


def optimize_keltner():
    print("=" * 90)
    print("OPTIMIZACIÓN REFINADA: KELTNER REVERSION DE QUANTDINGER EN [SP500] M15")
    print("=" * 90)
    print(f"{'MULT':<5} | {'STOP':<5} | {'BE_TRG':<6} | {'N':<5} | {'WIN RATE':<9} | {'PF':<6} | {'MaxDD%':<7} | {'E[R]':<8} | {'ESTADO':<10}")
    print("-" * 90)

    sym = "[SP500]"
    df_raw = fetch_symbol_bars(sym, mt5.TIMEFRAME_M15, 99999)
    df = add_base_indicators(df_raw)
    session = SESSION_UTC.get(sym, (13, 21))

    for multiplier in [2.0, 2.2, 2.5]:
        ind = compute_quantdinger_keltner(df, period=20, atr_period=10, multiplier=multiplier)
        c = ind["Close"].to_numpy(dtype=float)
        sma200 = ind["sma200"].to_numpy(dtype=float)
        k_pos = ind["keltner_pos"].to_numpy(dtype=float)
        lower_wick = ind["lower_wick"].to_numpy(dtype=float)

        # Señales Long-only en índice alcista
        signals = np.zeros(len(ind), dtype=int)
        for i in range(205, len(ind) - 1):
            if c[i] > sma200[i] and k_pos[i] <= 0.05 and lower_wick[i] >= 0.25:
                signals[i] = 1

        for stop_atr in [1.5, 2.0, 2.5]:
            for be_trg in [0.35, 0.50, None]:
                res = simulate_backtest(
                    df=ind,
                    symbol=sym,
                    signals=signals,
                    stop_atr=stop_atr,
                    tp_atr=None,
                    dynamic_exit_ema=9,
                    use_breakeven=(be_trg is not None),
                    be_trigger_atr=be_trg or 0.40,
                    be_lock_atr=0.05,
                    session_start_h=session[0],
                    session_end_h=session[1],
                )
                if res["n"] >= 50:
                    status = "PASS" if (res["wr"] >= 70.0 and res["max_dd_pct"] <= 5.0 and res["pf"] >= 1.25) else (
                        "CANDIDATA" if (res["wr"] >= 70.0 and res["max_dd_pct"] <= 5.5) else "FAIL"
                    )
                    be_str = f"{be_trg:.2f}" if be_trg else "None"
                    print(f"{multiplier:<5.1f} | {stop_atr:<5.1f} | {be_str:<6} | {res['n']:<5} | {res['wr']:<8.1f}% | {res['pf']:<6.2f} | {res['max_dd_pct']:<6.2f}% | {res['mean_r']:+7.4f} | {status}")

    print("=" * 90)
    mt5.shutdown()


if __name__ == "__main__":
    optimize_keltner()
