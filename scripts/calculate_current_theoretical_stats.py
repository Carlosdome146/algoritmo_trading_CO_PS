#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cálculo riguroso de estadísticas teóricas actuales por activo con todos los cambios aplicados."""
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

# Configuración exacta actual con todas las mejoras aplicadas:
# - Riesgo 1.0% (30.58 EUR)
# - Opción A1: Veto Campana 5 min (Eurex 07:00, Xetra/Madrid 08:00, Wall Street 13:30 UTC)
# - Breakeven Dinámico (+0.35 ATR trigger, +0.05 ATR lock)
# - Ventanas horarias institucionales refinadas

CURRENT_ASSETS = {
    "GERMANY40": {
        "tf": mt5.TIMEFRAME_M30,
        "tf_str": "M30",
        "target_u": 22.0,
        "stop_u": 35.0,
        "s_start": 7,
        "s_end": 17,
        "min_wick": 0.35,
        "allow_short": True,
        "unit_mult": 1.0,
        "spread": 1.2,
        "bell_hours": [7, 8],
    },
    "[SP500]": {
        "tf": mt5.TIMEFRAME_M30,
        "tf_str": "M30",
        "target_u": 4.0,
        "stop_u": 12.0,
        "s_start": 13,
        "s_end": 21,
        "min_wick": 0.35,
        "allow_short": False,
        "unit_mult": 1.0,
        "spread": 0.40,
        "bell_hours": [13],
    },
    "US100": {
        "tf": mt5.TIMEFRAME_M30,
        "tf_str": "M30",
        "target_u": 25.0,
        "stop_u": 70.0,
        "s_start": 13,
        "s_end": 21,
        "min_wick": 0.35,
        "allow_short": False,
        "unit_mult": 1.0,
        "spread": 1.5,
        "bell_hours": [13],
    },
    "[DJI30]": {
        "tf": mt5.TIMEFRAME_M30,
        "tf_str": "M30",
        "target_u": 40.0,
        "stop_u": 80.0,
        "s_start": 13,
        "s_end": 21,
        "min_wick": 0.35,
        "allow_short": False,
        "unit_mult": 1.0,
        "spread": 2.0,
        "bell_hours": [13],
    },
    "[IBEX35]": {
        "tf": mt5.TIMEFRAME_M15,
        "tf_str": "M15",
        "target_u": 20.0,
        "stop_u": 45.0,
        "s_start": 7,
        "s_end": 17,
        "min_wick": 0.35,
        "allow_short": False,
        "unit_mult": 1.0,
        "spread": 3.5,
        "bell_hours": [7, 8],
    },
    "GOLD": {
        "tf": mt5.TIMEFRAME_M30,
        "tf_str": "M30",
        "target_u": 4.0,
        "stop_u": 12.0,
        "s_start": 13,
        "s_end": 19,
        "min_wick": 0.45,
        "max_opp_wick": 0.12,
        "allow_short": False,
        "unit_mult": 1.0,
        "spread": 0.35,
        "bell_hours": [13],
    },
    "EURUSD": {
        "tf": mt5.TIMEFRAME_M15,
        "tf_str": "M15",
        "target_u": 3.5,
        "stop_u": 5.5,
        "s_start": 6,
        "s_end": 20,
        "min_wick": 0.35,
        "allow_short": True,
        "unit_mult": 0.00010,
        "spread": 0.00008,
        "bell_hours": [7, 13],
    },
}

summary = []

for sym, info in CURRENT_ASSETS.items():
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
        session_start_h=info["s_start"],
        session_end_h=info["s_end"],
        min_rejection_wick=info["min_wick"],
        max_opposite_wick=info.get("max_opp_wick"),
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
    bes = df_t[df_t["exit_reason"] == "BE"]
    tps = df_t[df_t["exit_reason"] == "TP"]
    sls = df_t[df_t["exit_reason"] == "SL"]

    wr = len(wins) / len(df_t) * 100
    pnl = df_t["pnl_eur"].sum()
    gross_w = wins["pnl_eur"].sum()
    gross_l = abs(losses["pnl_eur"].sum())
    pf = (gross_w / gross_l) if gross_l > 0 else 99.0
    cum = df_t["pnl_eur"].cumsum()
    dd = (cum.cummax() - cum).max()

    avg_win = wins["pnl_eur"].mean() if len(wins) > 0 else 0.0
    avg_loss = abs(losses["pnl_eur"].mean()) if len(losses) > 0 else 0.0
    payoff_r = (avg_win / avg_loss) if avg_loss > 0 else 0.0
    rr_ratio = info["target_u"] / info["stop_u"]

    summary.append({
        "symbol": sym,
        "tf": info["tf_str"],
        "tp_pts": info["target_u"],
        "sl_pts": info["stop_u"],
        "rr_theoretical": rr_ratio,
        "trades": len(df_t),
        "wr": wr,
        "tp_pct": (len(tps) / len(df_t)) * 100,
        "be_pct": (len(bes) / len(df_t)) * 100,
        "sl_pct": (len(sls) / len(df_t)) * 100,
        "pf": pf,
        "pnl_eur": pnl,
        "max_dd_eur": dd,
        "avg_win_eur": avg_win,
        "avg_loss_eur": avg_loss,
        "payoff_r": payoff_r,
    })

df_sum = pd.DataFrame(summary)
print("RESUMEN TEÓRICO COMPLETO POR ACTIVO:")
for _, r in df_sum.iterrows():
    print(f"[{r['symbol']}] ({r['tf']}): TP={r['tp_pts']} / SL={r['sl_pts']} (R={r['rr_theoretical']:.2f}) | Trades={r['trades']} | WR={r['wr']:.1f}% (TP={r['tp_pct']:.1f}%, BE={r['be_pct']:.1f}%, SL={r['sl_pct']:.1f}%) | PF={r['pf']:.2f} | AvgWin=+{r['avg_win_eur']:.2f}€ / AvgLoss=-{r['avg_loss_eur']:.2f}€ (Payoff={r['payoff_r']:.2f}) | PnL={r['pnl_eur']:+.2f}€ | MaxDD={r['max_dd_eur']:.2f}€")
