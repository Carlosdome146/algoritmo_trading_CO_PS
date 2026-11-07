#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Investigacion Forense: Diversificacion en Divisas (GBPUSD, USDJPY, EURUSD).

Evalua sobre 4 anos (2022 - 2026) diferentes estrategias y timeframes en Forex:
1. Modelo M15 Micro-Scalp (Baseline actual: target 3.5 - 5.5 pips).
2. Modelo M30 Swing Intradia (target 12.0 - 18.0 pips).
3. Modelo H1 London Breakout / Sweep (target 25.0 - 35.0 pips).
4. Modelo H1 Reversion de Agotamiento Extremo (Keltner/Bollinger 2.5 sigma + RSI2).

Analiza:
- Win Rate (%)
- Profit Factor (PF)
- Beneficio Neto (EUR)
- Ratio Spread/Target (% friccion de costes)
- Correlacion con el DAX / Indices
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


def load_bars_safe(symbol: str, tf: int, n_bars: int = 30000) -> pd.DataFrame:
    mt5.symbol_select(symbol, True)
    r = mt5.copy_rates_from_pos(symbol, tf, 0, n_bars)
    if r is None or len(r) == 0:
        return pd.DataFrame()
    df = pd.DataFrame(r)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "tick_volume": "Volume"}, inplace=True)
    return df


def backtest_h1_london_sweep(df: pd.DataFrame, symbol: str, tgt_pips: float, sl_pips: float, spread_pips: float) -> dict:
    """Estrategia H1: London Session Sweep Reclaim (07:00 a 16:00 UTC)."""
    if df.empty or len(df) < 200:
        return {}

    is_jpy = "JPY" in symbol
    pip = 0.01 if is_jpy else 0.00010
    tgt_dist = tgt_pips * pip
    sl_dist = sl_pips * pip
    spread_dist = spread_pips * pip
    risk_eur = 45.0

    c = df["Close"].to_numpy()
    h = df["High"].to_numpy()
    l = df["Low"].to_numpy()
    o = df["Open"].to_numpy()
    times = df.index
    hrs = times.hour.to_numpy()
    dows = times.dayofweek.to_numpy()
    n = len(df)

    sma200 = pd.Series(c).rolling(200, min_periods=50).mean().to_numpy()
    ema20 = pd.Series(c).ewm(span=20, adjust=False).mean().to_numpy()
    rec_lo = pd.Series(l).shift(1).rolling(8, min_periods=3).min().to_numpy()
    rec_hi = pd.Series(h).shift(1).rolling(8, min_periods=3).max().to_numpy()

    rng = np.maximum(h - l, 1e-9)
    lower_wick = (np.minimum(o, c) - l) / rng
    upper_wick = (h - np.maximum(o, c)) / rng
    clv = (c - l) / rng

    trades = []
    i = 200
    while i < n - 1:
        if dows[i] >= 5 or not (7 <= hrs[i] <= 16):
            i += 1
            continue

        sig = 0
        # LONG: Tendencia alcista H1 + barrido de minimo 8 velas + mecha rechazo >= 35% + CLV >= 0.60
        if (c[i] > sma200[i]) and (l[i] <= rec_lo[i]) and (c[i] > rec_lo[i]) and (lower_wick[i] >= 0.35) and (clv[i] >= 0.60):
            sig = 1
        # SHORT: Tendencia bajista H1 + barrido de maximo 8 velas + mecha rechazo >= 35% + CLV <= 0.40
        elif (c[i] < sma200[i]) and (h[i] >= rec_hi[i]) and (c[i] < rec_hi[i]) and (upper_wick[i] >= 0.35) and (clv[i] <= 0.40):
            sig = -1

        if sig != 0:
            k = i + 1
            entry_time = times[k]
            if sig == 1:
                entry_px = o[k] + spread_dist
                sl_px = entry_px - sl_dist
                tp_px = entry_px + tgt_dist
            else:
                entry_px = o[k]
                sl_px = entry_px + sl_dist
                tp_px = entry_px - tgt_dist

            exit_px = None
            exit_reason = None
            exit_time = None

            for j in range(k, min(k + 12, n)): # Hasta 12 barras H1 (12 horas)
                bar_h = h[j]
                bar_l = l[j]
                bar_c = c[j]
                bar_o = o[j]

                if sig == 1:
                    if bar_l <= sl_px and bar_h >= tp_px:
                        exit_px = tp_px if bar_c > bar_o else sl_px
                        exit_reason = "TP" if bar_c > bar_o else "SL"
                        exit_time = times[j]
                        break
                    elif bar_h >= tp_px:
                        exit_px = tp_px
                        exit_reason = "TP"
                        exit_time = times[j]
                        break
                    elif bar_l <= sl_px:
                        exit_px = sl_px
                        exit_reason = "SL"
                        exit_time = times[j]
                        break
                else:
                    ask_l = bar_l + spread_dist
                    ask_h = bar_h + spread_dist
                    if ask_h >= sl_px and ask_l <= tp_px:
                        exit_px = tp_px if bar_c < bar_o else sl_px
                        exit_reason = "TP" if bar_c < bar_o else "SL"
                        exit_time = times[j]
                        break
                    elif ask_l <= tp_px:
                        exit_px = tp_px
                        exit_reason = "TP"
                        exit_time = times[j]
                        break
                    elif ask_h >= sl_px:
                        exit_px = sl_px
                        exit_reason = "SL"
                        exit_time = times[j]
                        break

            if exit_px is None:
                j_end = min(k + 11, n - 1)
                exit_px = c[j_end] if sig == 1 else (c[j_end] + spread_dist)
                exit_reason = "TIME"
                exit_time = times[j_end]

            p_delta = (exit_px - entry_px) if sig == 1 else (entry_px - exit_px)
            pnl_eur = (p_delta / sl_dist) * risk_eur

            trades.append({
                "entry_time": entry_time,
                "exit_time": exit_time,
                "direction": "BUY" if sig == 1 else "SELL",
                "pnl_eur": pnl_eur,
                "win": 1 if pnl_eur > 0 else 0,
                "exit_reason": exit_reason,
            })
            i = j + 2 # Cooldown de 2 barras H1 (2 horas)
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
    friction_pct = (spread_pips / tgt_pips) * 100

    return {
        "trades": n_t,
        "wr": wr,
        "pf": pf,
        "pnl": pnl,
        "max_dd": max_dd,
        "friction": friction_pct,
        "from": df.index[0].strftime("%Y-%m-%d"),
        "to": df.index[-1].strftime("%Y-%m-%d"),
    }


def backtest_h1_exhaustion_reversion(df: pd.DataFrame, symbol: str, spread_pips: float) -> dict:
    """Estrategia H1: Mean-Reversion de Agotamiento Extremo (Bollinger 2.5 sigma + RSI(2) extremo)."""
    if df.empty or len(df) < 200:
        return {}

    is_jpy = "JPY" in symbol
    pip = 0.01 if is_jpy else 0.00010
    spread_dist = spread_pips * pip
    risk_eur = 45.0

    c = df["Close"].to_numpy()
    h = df["High"].to_numpy()
    l = df["Low"].to_numpy()
    o = df["Open"].to_numpy()
    times = df.index
    dows = times.dayofweek.to_numpy()
    n = len(df)

    # Indicadores
    sma20 = pd.Series(c).rolling(20, min_periods=20).mean().to_numpy()
    std20 = pd.Series(c).rolling(20, min_periods=20).std().to_numpy()
    bb_hi = sma20 + 2.5 * std20
    bb_lo = sma20 - 2.5 * std20

    # RSI(2)
    delta = pd.Series(c).diff()
    gain = (delta.where(delta > 0, 0)).rolling(2).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(2).mean()
    rs = gain / loss.replace(0, 1e-9)
    rsi2 = (100 - (100 / (1 + rs))).to_numpy()

    # ATR 14 para SL dinamico
    tr = np.maximum(h - l, np.abs(h - pd.Series(c).shift(1).fillna(c[0]).to_numpy()))
    atr14 = pd.Series(tr).rolling(14, min_periods=5).mean().to_numpy()

    trades = []
    i = 50
    while i < n - 1:
        if dows[i] >= 5:
            i += 1
            continue

        sig = 0
        cur_atr = atr14[i]
        if not np.isfinite(cur_atr) or cur_atr <= 0:
            i += 1
            continue

        # COMPRA en agotamiento extremo inferior: Vela perfora BB_lo + RSI(2) < 10
        if (l[i] <= bb_lo[i]) and (rsi2[i] < 10.0) and (c[i] > o[i]):
            sig = 1
        # VENTA en agotamiento extremo superior: Vela perfora BB_hi + RSI(2) > 90
        elif (h[i] >= bb_hi[i]) and (rsi2[i] > 90.0) and (c[i] < o[i]):
            sig = -1

        if sig != 0:
            k = i + 1
            entry_time = times[k]
            tgt_dist = abs(c[i] - sma20[i]) # Retorno a la media móvil de 20
            sl_dist = 1.5 * cur_atr

            if tgt_dist < 10 * pip or sl_dist < 15 * pip:
                i += 1
                continue

            if sig == 1:
                entry_px = o[k] + spread_dist
                sl_px = entry_px - sl_dist
                tp_px = entry_px + tgt_dist
            else:
                entry_px = o[k]
                sl_px = entry_px + sl_dist
                tp_px = entry_px - tgt_dist

            exit_px = None
            exit_reason = None
            exit_time = None

            for j in range(k, min(k + 16, n)): # Hasta 16 barras H1 (16 horas)
                bar_h = h[j]
                bar_l = l[j]
                bar_c = c[j]
                bar_o = o[j]

                if sig == 1:
                    if bar_l <= sl_px and bar_h >= tp_px:
                        exit_px = tp_px if bar_c > bar_o else sl_px
                        exit_reason = "TP" if bar_c > bar_o else "SL"
                        exit_time = times[j]
                        break
                    elif bar_h >= tp_px:
                        exit_px = tp_px
                        exit_reason = "TP"
                        exit_time = times[j]
                        break
                    elif bar_l <= sl_px:
                        exit_px = sl_px
                        exit_reason = "SL"
                        exit_time = times[j]
                        break
                else:
                    ask_l = bar_l + spread_dist
                    ask_h = bar_h + spread_dist
                    if ask_h >= sl_px and ask_l <= tp_px:
                        exit_px = tp_px if bar_c < bar_o else sl_px
                        exit_reason = "TP" if bar_c < bar_o else "SL"
                        exit_time = times[j]
                        break
                    elif ask_l <= tp_px:
                        exit_px = tp_px
                        exit_reason = "TP"
                        exit_time = times[j]
                        break
                    elif ask_h >= sl_px:
                        exit_px = sl_px
                        exit_reason = "SL"
                        exit_time = times[j]
                        break

            if exit_px is None:
                j_end = min(k + 15, n - 1)
                exit_px = c[j_end] if sig == 1 else (c[j_end] + spread_dist)
                exit_reason = "TIME"
                exit_time = times[j_end]

            p_delta = (exit_px - entry_px) if sig == 1 else (entry_px - exit_px)
            pnl_eur = (p_delta / sl_dist) * risk_eur

            trades.append({
                "entry_time": entry_time,
                "exit_time": exit_time,
                "direction": "BUY" if sig == 1 else "SELL",
                "pnl_eur": pnl_eur,
                "win": 1 if pnl_eur > 0 else 0,
                "exit_reason": exit_reason,
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
        "trades": n_t,
        "wr": wr,
        "pf": pf,
        "pnl": pnl,
        "max_dd": max_dd,
        "from": df.index[0].strftime("%Y-%m-%d"),
        "to": df.index[-1].strftime("%Y-%m-%d"),
    }


def main():
    mt5.initialize()
    print("=" * 95)
    print("AUDITORIA FORENSE MULTI-ESTRATEGIA EN DIVISAS A 4 ANOS (2022 - 2026)")
    print("Investigacion Cuantitativa para Diversificacion sin Friccion")
    print("=" * 95)

    PAIRS_CONFIG = {
        "EURUSD": {"spread": 0.8, "tgt": 25.0, "sl": 20.0},
        "GBPUSD": {"spread": 1.4, "tgt": 32.0, "sl": 24.0},
        "USDJPY": {"spread": 1.2, "tgt": 45.0, "sl": 32.0},
        "AUDUSD": {"spread": 1.0, "tgt": 22.0, "sl": 18.0},
        "USDCAD": {"spread": 1.8, "tgt": 28.0, "sl": 22.0},
    }

    # 1. ESTRATEGIA 1: H1 LONDON SESSION SWEEP RECLAIM
    print("\n--- MODELO 1: H1 LONDON SESSION SWEEP RECLAIM (Target 22 - 45 pips) ---")
    print(f"{'Par FX':<10s} | {'Periodo':<23s} | {'Trades':<8s} | {'Win Rate':<10s} | {'PF':<8s} | {'PnL (EUR)':<15s} | {'Max DD':<12s} | {'Friccion':<10s}")
    print("-" * 95)

    for sym, cfg in PAIRS_CONFIG.items():
        df_h1 = load_bars_safe(sym, mt5.TIMEFRAME_H1, n_bars=25000)
        res1 = backtest_h1_london_sweep(df_h1, sym, cfg["tgt"], cfg["sl"], cfg["spread"])
        if res1:
            period = f"{res1['from']} -> {res1['to']}"
            fric = f"{res1['friction']:.1f}%"
            print(f"{sym:<10s} | {period:<23s} | {res1['trades']:<8d} | {res1['wr']:<9.1f}% | {res1['pf']:<8.2f} | {res1['pnl']:<+15.2f} | {res1['max_dd']:<12.2f} | {fric:<10s}")

    # 2. ESTRATEGIA 2: H1 REVERSION DE AGOTAMIENTO EXTREMO (BOLLINGER 2.5s + RSI2)
    print("\n--- MODELO 2: H1 MEAN REVERSION AGOTAMIENTO EXTREMO (Bollinger 2.5s + RSI2 < 10/> 90) ---")
    print(f"{'Par FX':<10s} | {'Periodo':<23s} | {'Trades':<8s} | {'Win Rate':<10s} | {'PF':<8s} | {'PnL (EUR)':<15s} | {'Max DD':<12s}")
    print("-" * 95)

    for sym, cfg in PAIRS_CONFIG.items():
        df_h1 = load_bars_safe(sym, mt5.TIMEFRAME_H1, n_bars=25000)
        res2 = backtest_h1_exhaustion_reversion(df_h1, sym, cfg["spread"])
        if res2:
            period = f"{res2['from']} -> {res2['to']}"
            print(f"{sym:<10s} | {period:<23s} | {res2['trades']:<8d} | {res2['wr']:<9.1f}% | {res2['pf']:<8.2f} | {res2['pnl']:<+15.2f} | {res2['max_dd']:<12.2f}")


if __name__ == "__main__":
    main()
