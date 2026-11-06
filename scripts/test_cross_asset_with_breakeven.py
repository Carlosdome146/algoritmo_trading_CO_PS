#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Auditoría Multi-Activo con Regla de Breakeven (+0.35 ATR trigger) y Ventanas Horarias de Alta Probabilidad."""
import sys
sys.path.insert(0, ".")
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

from trading_v2.strategies.micro_scalping import (
    SniperScalpConfig,
    generate_sniper_signals,
    compute_sniper_indicators,
)
from scripts.forensic_cross_asset_audit_4y import ASSETS_CONFIG, load_symbol_bars

mt5.initialize()

print("=" * 110)
print("AUDITORÍA FORENSE MULTI-ACTIVO CON BREAKEVEN (+0.35*ATR) Y FILTRO CAMPANA A1 (2022 - 2026)")
print("=" * 110)

results = []

for sym, info in ASSETS_CONFIG.items():
    df = load_symbol_bars(sym, info["tf"], count=60000)
    if len(df) == 0:
        continue

    # Calcular ATR causal
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - df["Close"].shift(1)).abs(),
        (df["Low"] - df["Close"].shift(1)).abs(),
    ], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14, min_periods=5).mean().bfill()

    cfg = SniperScalpConfig(
        symbol=sym,
        target_units=info["target_u"],
        stop_units=info["stop_u"],
        session_start_h=info["s_start"],
        session_end_h=info["s_end"],
        min_rejection_wick=info["min_wick"],
        max_opposite_wick=info["max_opp_wick"],
        use_h1_filter=True,
        use_ker_filter=True,
        max_ker_trend=0.45,
        cooldown_bars=2,
        use_climax_filter=True,
        allow_short=info["allow_short"],
    )

    sig_df = generate_sniper_signals(df, cfg)
    signals = sig_df["signal"].to_numpy().copy()

    # Veto Campana A1
    times_idx = df.index
    bell_hs = info["bell_hours"]
    for k in range(len(signals)):
        t_bar = times_idx[k]
        if t_bar.hour in bell_hs and (t_bar.minute == 0 or t_bar.minute == 30):
            signals[k] = 0

    times = df.index
    opens = df["Open"].to_numpy()
    highs = df["High"].to_numpy()
    lows = df["Low"].to_numpy()
    closes = df["Close"].to_numpy()
    atrs = df["atr"].to_numpy()
    n = len(df)

    unit_m = info["unit_mult"]
    spread = info["spread"]
    tp_dist = info["target_u"] * unit_m
    sl_dist = info["stop_u"] * unit_m
    risk_eur = 30.58

    trades = []
    i = 0
    while i < n - 1:
        sig = signals[i]
        if sig != 0:
            entry_time = times[i + 1]
            atr_i = atrs[i]
            be_trig = 0.35 * atr_i
            be_lock = 0.05 * atr_i

            if sig == 1:
                entry_px = opens[i + 1] + spread
                sl_px = entry_px - sl_dist
                tp_px = entry_px + tp_dist
            else:
                entry_px = opens[i + 1]
                sl_px = entry_px + sl_dist
                tp_px = entry_px - tp_dist

            be_active = False
            exit_px = None
            exit_reason = None

            for j in range(i + 1, min(i + 1 + 8, n)):
                b_h = highs[j]
                b_l = lows[j]
                b_c = closes[j]
                b_o = opens[j]

                # 1. Comprobar si se activa Breakeven
                if sig == 1:
                    if not be_active and (b_h - entry_px) >= be_trig:
                        be_active = True
                        sl_px = max(sl_px, entry_px + be_lock)
                    # Comprobar salidas
                    if b_l <= sl_px and b_h >= tp_px:
                        exit_px = tp_px if b_c > b_o else sl_px
                        exit_reason = "TP" if b_c > b_o else ("BE" if be_active else "SL")
                        break
                    elif b_h >= tp_px:
                        exit_px = tp_px
                        exit_reason = "TP"
                        break
                    elif b_l <= sl_px:
                        exit_px = sl_px
                        exit_reason = "BE" if be_active else "SL"
                        break
                else:  # SHORT
                    ask_l = b_l + spread
                    ask_h = b_h + spread
                    if not be_active and (entry_px - ask_l) >= be_trig:
                        be_active = True
                        sl_px = min(sl_px, entry_px - be_lock)
                    if ask_h >= sl_px and ask_l <= tp_px:
                        exit_px = tp_px if b_c < b_o else sl_px
                        exit_reason = "TP" if b_c < b_o else ("BE" if be_active else "SL")
                        break
                    elif ask_l <= tp_px:
                        exit_px = tp_px
                        exit_reason = "TP"
                        break
                    elif ask_h >= sl_px:
                        exit_px = sl_px
                        exit_reason = "BE" if be_active else "SL"
                        break

            if exit_px is None:
                exit_j = min(i + 8, n - 1)
                exit_px = closes[exit_j] if sig == 1 else closes[exit_j] + spread
                exit_reason = "TIME_STOP"
                j = exit_j

            pts_gain = (exit_px - entry_px) if sig == 1 else (entry_px - exit_px)
            pnl_eur = (pts_gain / sl_dist) * risk_eur

            trades.append({
                "entry_time": entry_time,
                "pnl_eur": pnl_eur,
                "win": pnl_eur > 0,
                "exit_reason": exit_reason,
            })
            i = j + 2
        else:
            i += 1

    df_t = pd.DataFrame(trades)
    if len(df_t) == 0:
        continue

    wins = df_t[df_t["pnl_eur"] > 0]
    losses = df_t[df_t["pnl_eur"] < 0]
    wr = len(wins) / len(df_t) * 100
    pnl = df_t["pnl_eur"].sum()
    gross_w = wins["pnl_eur"].sum()
    gross_l = abs(losses["pnl_eur"].sum())
    pf = (gross_w / gross_l) if gross_l > 0 else 99.0
    cum = df_t["pnl_eur"].cumsum()
    dd = (cum.cummax() - cum).max()
    be_count = len(df_t[df_t["exit_reason"] == "BE"])

    results.append({
        "symbol": sym,
        "tf": info["tf_str"],
        "trades": len(df_t),
        "wr": wr,
        "pf": pf,
        "pnl": pnl,
        "dd": dd,
        "be_pct": (be_count / len(df_t)) * 100,
    })

print(f"{'Activo':<12s} | {'TF':<4s} | {'Trades':<8s} | {'Win Rate':<10s} | {'Breakevens':<12s} | {'PF':<6s} | {'PnL Total':<14s} | {'Max DD':<10s}")
print("-" * 95)
tot_pnl = 0.0
for r in results:
    tot_pnl += r["pnl"]
    print(f"{r['symbol']:<12s} | {r['tf']:<4s} | {r['trades']:<8d} | {r['wr']:>6.1f} %   | {r['be_pct']:>6.1f} %     | {r['pf']:>5.2f} | {r['pnl']:>+11.2f} € | {r['dd']:>8.2f} €")
print("-" * 95)
print(f"{'TOTAL CARTERA':<28s} |                              | {tot_pnl:>+11.2f} € |")
print("=" * 95)
