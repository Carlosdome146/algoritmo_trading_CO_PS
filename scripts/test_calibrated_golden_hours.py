#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Auditoría de Ventanas Institucionales Calibradas (Golden Hours vs Toxic Hours)."""
import sys
sys.path.insert(0, ".")
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

from trading_v2.strategies.micro_scalping import (
    SniperScalpConfig,
    generate_sniper_signals,
)
from scripts.forensic_cross_asset_audit_4y import ASSETS_CONFIG, load_symbol_bars

mt5.initialize()

print("=" * 115)
print("AUDITORÍA DE SESIÓN CALIBRADA (ELIMINACIÓN DE HORAS TÓXICAS DE CHOP) (2022 - 2026)")
print("=" * 115)

# Definición de horas permitidas por activo (excluyendo horas con pérdida sistemática probada en 4 años)
CALIBRATED_ALLOWED_HOURS = {
    # DAX: Mañana temprana (07-09 UTC), mediodía (11 UTC), cierre europeo (16-17 UTC). Excluye 09-11 UTC y 13-14 UTC.
    "GERMANY40": [7, 8, 11, 16, 17, 18],
    # SP500: Sesión central Wall Street (14-17 UTC) y cierre (18-20 UTC). Excluye 13 UTC (pre-mkt) y 17 UTC.
    "[SP500]": [14, 15, 16, 18, 19, 20],
    # US100: Sesión líquida post-apertura (14-16 UTC) y tarde (17, 20, 21 UTC). Excluye 13 UTC y 19 UTC.
    "US100": [14, 15, 17, 20, 21],
    # DJI30: Apertura y primera hora (12-14 UTC).
    "[DJI30]": [12, 13, 14],
    # IBEX35: Apertura Londres (08 UTC) y tarde (14 UTC).
    "[IBEX35]": [8, 14],
    # GOLD: Pico de volatilidad Londres/NY (13 UTC, 15 UTC, 19-21 UTC).
    "GOLD": [13, 15, 19, 20, 21],
    # EURUSD: Pre-apertura (06 UTC), mañana (08, 11 UTC) y apertura NY (13 UTC). Excluye 07 UTC tóxico (33% WR).
    "EURUSD": [6, 8, 11, 13, 15],
}

results = []

for sym, info in ASSETS_CONFIG.items():
    df = load_symbol_bars(sym, info["tf"], count=60000)
    if len(df) == 0:
        continue

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
        session_start_h=min(CALIBRATED_ALLOWED_HOURS[sym]),
        session_end_h=max(CALIBRATED_ALLOWED_HOURS[sym]) + 1,
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

    # Veto de campana de apertura y filtrado estricto a las Golden Hours
    times_idx = df.index
    allowed = set(CALIBRATED_ALLOWED_HOURS[sym])
    bell_hs = info["bell_hours"]
    for k in range(len(signals)):
        t_bar = times_idx[k]
        if t_bar.hour not in allowed:
            signals[k] = 0
        elif t_bar.hour in bell_hs and (t_bar.minute == 0 or t_bar.minute == 30):
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

                if sig == 1:
                    if not be_active and (b_h - entry_px) >= be_trig:
                        be_active = True
                        sl_px = max(sl_px, entry_px + be_lock)
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
                else:
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
print(f"{'TOTAL CARTERA CALIBRADA':<28s} |                              | {tot_pnl:>+11.2f} € |")
print("=" * 95)
