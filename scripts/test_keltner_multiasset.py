"""Evaluación Multi-Activo de la estrategia QuantDinger Keltner Reversion en M15."""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trading_v2.backtesting.intraday_engine import add_base_indicators, SESSION_UTC
from trading_v2.strategies.github_imports.quantdinger_strategies import compute_quantdinger_keltner
from scripts.backtest_strategy import fetch_symbol_bars, simulate_backtest, update_dashboard_markdown

mt5.initialize()
print("=" * 85)
print("EVALUACIÓN MULTIACTIVO: QUANTDINGER KELTNER REVERSION M15")
print("Configuración: Keltner 2.0x, Stop 2.5 ATR, Breakeven @ +0.50 ATR, Salida EMA9")
print("=" * 85)
print(f"{'ACTIVO':<12} | {'N':<5} | {'WIN RATE':<9} | {'PF':<6} | {'MaxDD%':<7} | {'E[R]':<8} | {'ESTADO':<10}")
print("-" * 85)

for sym in ["[SP500]", "US100", "GERMANY40", "EURUSD"]:
    df_raw = fetch_symbol_bars(sym, mt5.TIMEFRAME_M15, 99999)
    df = add_base_indicators(df_raw)
    ind = compute_quantdinger_keltner(df, period=20, atr_period=10, multiplier=2.0)
    c = ind["Close"].to_numpy(dtype=float)
    sma200 = ind["sma200"].to_numpy(dtype=float)
    k_pos = ind["keltner_pos"].to_numpy(dtype=float)
    lower_wick = ind["lower_wick"].to_numpy(dtype=float)

    signals = np.zeros(len(ind), dtype=int)
    for i in range(205, len(ind) - 1):
        if c[i] > sma200[i] and k_pos[i] <= 0.05 and lower_wick[i] >= 0.25:
            signals[i] = 1

    session = SESSION_UTC.get(sym, (7, 17)) if sym != "[SP500]" and sym != "US100" else SESSION_UTC.get(sym, (13, 21))
    res = simulate_backtest(
        df=ind,
        symbol=sym,
        signals=signals,
        stop_atr=2.5,
        tp_atr=None,
        dynamic_exit_ema=9,
        use_breakeven=True,
        be_trigger_atr=0.50,
        be_lock_atr=0.05,
        session_start_h=session[0],
        session_end_h=session[1],
    )
    res["strategy_name"] = "QuantDinger_Keltner_Reversion_Opt"
    res["symbol"] = sym
    res["timeframe"] = "M15"

    status = "APROBADA" if (res["wr"] >= 70.0 and res["max_dd_pct"] <= 5.0 and res["pf"] >= 1.25) else (
        "CANDIDATA" if (res["wr"] >= 70.0 and res["max_dd_pct"] <= 5.5) else "DESCARTADA"
    )
    print(f"{sym:<12} | {res['n']:<5} | {res['wr']:<8.1f}% | {res['pf']:<6.2f} | {res['max_dd_pct']:<6.2f}% | {res['mean_r']:+7.4f} | {status}")
    update_dashboard_markdown(res)

print("=" * 85)
mt5.shutdown()
