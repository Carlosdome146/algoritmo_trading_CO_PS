#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Investigacion Cuantitativa: Diversificacion de Cartera con Nuevos Pares FX.

Evalua candidatos: GBPUSD, USDJPY, AUDUSD frente a EURUSD bajo el modelo Micro-Sweep Reclaim M15.
Analiza:
1. Win Rate y Profit Factor sobre 50,000 velas M15.
2. Correlacion con EURUSD e Indices (desacoplamiento).
3. Viabilidad operativa con el broker Admirals.
"""
from __future__ import annotations

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trading_v2.strategies.micro_scalping import SniperScalpConfig, generate_sniper_signals


def simulate_fx_pair(symbol: str, tgt_pips: float, sl_pips: float, spread_pips: float, s_start: int = 7, s_end: int = 17, min_wick: float = 0.35) -> dict:
    r = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 50000)
    if r is None or len(r) == 0:
        return {}

    df = pd.DataFrame(r)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "tick_volume": "Volume"}, inplace=True)

    is_jpy = "JPY" in symbol
    pip_mult = 0.01 if is_jpy else 0.00010
    tgt_dist = tgt_pips * pip_mult
    sl_dist = sl_pips * pip_mult
    spread_dist = spread_pips * pip_mult
    risk_eur = 45.0

    cfg = SniperScalpConfig(
        symbol=symbol,
        target_units=tgt_pips,
        stop_units=sl_pips,
        session_start_h=s_start,
        session_end_h=s_end,
        min_rejection_wick=min_wick,
        cooldown_bars=2,
        use_h1_filter=True,
        use_ker_filter=True,
        max_ker_trend=0.45,
        allow_short=True,
    )
    sig_df = generate_sniper_signals(df, cfg)
    signals = sig_df["signal"].to_numpy()

    times = df.index
    opens = df["Open"].to_numpy()
    highs = df["High"].to_numpy()
    lows = df["Low"].to_numpy()
    closes = df["Close"].to_numpy()
    n = len(df)

    trades = []
    i = 0
    while i < n - 1:
        sig = signals[i]
        if sig != 0:
            entry_time = times[i + 1]
            if sig == 1:
                entry_price = opens[i + 1] + spread_dist
                sl_price = entry_price - sl_dist
                tp_price = entry_price + tgt_dist
            else:
                entry_price = opens[i + 1]
                sl_price = entry_price + sl_dist
                tp_price = entry_price - tgt_dist

            exit_price = None
            exit_reason = None
            exit_time = None

            for j in range(i + 1, min(i + 1 + 8, n)):
                bar_h = highs[j]
                bar_l = lows[j]
                bar_c = closes[j]
                bar_o = opens[j]

                if sig == 1:
                    if bar_l <= sl_price and bar_h >= tp_price:
                        exit_price = tp_price if bar_c > bar_o else sl_price
                        exit_reason = "TP" if bar_c > bar_o else "SL"
                        exit_time = times[j]
                        break
                    elif bar_h >= tp_price:
                        exit_price = tp_price
                        exit_reason = "TP"
                        exit_time = times[j]
                        break
                    elif bar_l <= sl_price:
                        exit_price = sl_price
                        exit_reason = "SL"
                        exit_time = times[j]
                        break
                else:
                    ask_l = bar_l + spread_dist
                    ask_h = bar_h + spread_dist
                    if ask_h >= sl_price and ask_l <= tp_price:
                        exit_price = tp_price if bar_c < bar_o else sl_price
                        exit_reason = "TP" if bar_c < bar_o else "SL"
                        exit_time = times[j]
                        break
                    elif ask_l <= tp_price:
                        exit_price = tp_price
                        exit_reason = "TP"
                        exit_time = times[j]
                        break
                    elif ask_h >= sl_price:
                        exit_price = sl_price
                        exit_reason = "SL"
                        exit_time = times[j]
                        break

            if exit_price is None:
                j_end = min(i + 1 + 7, n - 1)
                exit_price = closes[j_end] if sig == 1 else (closes[j_end] + spread_dist)
                exit_reason = "TIME"
                exit_time = times[j_end]

            p_delta = (exit_price - entry_price) if sig == 1 else (entry_price - exit_price)
            pnl_eur = (p_delta / sl_dist) * risk_eur

            trades.append({
                "entry_time": entry_time,
                "exit_time": exit_time,
                "date": entry_time.date(),
                "pnl_eur": pnl_eur,
                "win": 1 if pnl_eur > 0 else 0,
            })
            i = j + 2
        else:
            i += 1

    df_t = pd.DataFrame(trades)
    if df_t.empty:
        return {}

    wins = df_t[df_t["win"] == 1]
    losses = df_t[df_t["win"] == 0]
    n_t = len(df_t)
    wr = (len(wins) / n_t) * 100
    gp = wins["pnl_eur"].sum()
    gl = abs(losses["pnl_eur"].sum()) if len(losses) > 0 else 1e-6
    pf = gp / gl
    pnl = df_t["pnl_eur"].sum()
    cum = df_t["pnl_eur"].cumsum()
    max_dd = (cum.cummax() - cum).max()

    return {
        "symbol": symbol,
        "trades": n_t,
        "wr": wr,
        "pf": pf,
        "pnl": pnl,
        "max_dd": max_dd,
        "bars": len(df),
        "from": df.index[0].strftime("%Y-%m-%d"),
        "to": df.index[-1].strftime("%Y-%m-%d"),
        "df_t": df_t,
    }


def main():
    mt5.initialize()
    print("=" * 90)
    print("AUDITORIA FORENSE DE DIVERSIFICACION: CANDIDATOS FOREX (M15)")
    print("Evaluando sobre 50,000 velas M15 (2024 - 2026)")
    print("=" * 90)

    # Parametros por par adaptados a su volatilidad ATR y spread
    PAIRS = {
        "EURUSD": {"tgt": 3.5, "sl": 5.5, "spr": 0.8, "start": 6, "end": 20, "wick": 0.35},
        "GBPUSD": {"tgt": 4.5, "sl": 7.5, "spr": 1.4, "start": 7, "end": 17, "wick": 0.40},
        "USDJPY": {"tgt": 5.5, "sl": 9.5, "spr": 1.2, "start": 6, "end": 20, "wick": 0.35},
        "AUDUSD": {"tgt": 3.0, "sl": 5.0, "spr": 1.0, "start": 6, "end": 20, "wick": 0.35},
    }

    print(f"{'Par FX':<10s} | {'Barras':<8s} | {'Periodo':<23s} | {'Trades':<8s} | {'Win Rate':<10s} | {'PF':<8s} | {'PnL (EUR)':<15s} | {'Max DD':<12s}")
    print("-" * 90)

    results = {}
    for sym, p in PAIRS.items():
        res = simulate_fx_pair(sym, p["tgt"], p["sl"], p["spr"], p["start"], p["end"], p["wick"])
        results[sym] = res
        period = f"{res.get('from', '')} -> {res.get('to', '')}"
        print(f"{sym:<10s} | {res.get('bars', 0):<8d} | {period:<23s} | {res.get('trades', 0):<8d} | {res.get('wr', 0):<9.1f}% | {res.get('pf', 0):<8.2f} | {res.get('pnl', 0):<+15.2f} | {res.get('max_dd', 0):<12.2f}")


if __name__ == "__main__":
    main()
