"""Auditoría de EURUSD M15 con filtro H1 Trend causal a 1 año y en Octubre 2026."""
from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from trading_v2.research.regime_lab_v3 import metrics

def main():
    if not mt5.initialize():
        return
        
    r_m15 = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_M15, 0, 35000)
    r_h1 = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_H1, 0, 9000)
    
    df = pd.DataFrame(r_m15)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    
    df_h1 = pd.DataFrame(r_h1)
    df_h1["time"] = pd.to_datetime(df_h1["time"], unit="s", utc=True)
    df_h1.set_index("time", inplace=True)
    df_h1["h1_ema20"] = df_h1["close"].ewm(span=20, adjust=False).mean()
    df_h1["h1_ema50"] = df_h1["close"].ewm(span=50, adjust=False).mean()
    df_h1["h1_trend"] = np.where(df_h1["h1_ema20"] > df_h1["h1_ema50"], 1, -1)
    
    # Mapear de forma estrictamente causal el H1 trend cerrado al M15
    df_h1["h1_close_time"] = df_h1.index + pd.to_timedelta(1, unit="h")
    # merge asof
    df = pd.merge_asof(
        df.sort_index(),
        df_h1[["h1_close_time", "h1_trend"]].rename(columns={"h1_trend": "h1_dir"}),
        left_index=True,
        right_on="h1_close_time",
        direction="backward"
    )
    df.set_index(df_m15_time := pd.to_datetime(r_m15["time"], unit="s", utc=True), inplace=True)
    df["h1_dir"] = df["h1_dir"].fillna(0).astype(int)
    
    c = df["close"].values
    h = df["high"].values
    l = df["low"].values
    o = df["open"].values
    h1_dir = df["h1_dir"].values
    hrs = df.index.hour.values
    dows = df.index.dayofweek.values
    n = len(df)
    
    rng = np.maximum(h - l, 1e-9)
    lower_wick = (np.minimum(o, c) - l) / rng
    upper_wick = (h - np.maximum(o, c)) / rng
    clv = (c - l) / rng
    
    pip = 0.00010
    spr_d = 0.8 * pip
    tgt_d = 3.5 * pip
    sl_d = 5.5 * pip
    be_trig_d = 2.0 * pip
    be_lock_d = 0.5 * pip
    
    for lookback in [12, 16, 20]:
        rec_hi = pd.Series(h).shift(1).rolling(lookback, min_periods=4).max().values
        rec_lo = pd.Series(l).shift(1).rolling(lookback, min_periods=4).min().values
        
        for use_h1 in [True, False]:
            sigs = np.zeros(n, dtype=int)
            for i in range(lookback + 5, n):
                if dows[i] >= 5: continue
                # Horas de Londres + NY: 06:00 a 19:00 UTC
                if not (6 <= hrs[i] <= 19): continue
                
                h1_ok_l = (h1_dir[i] >= 0) if use_h1 else True
                h1_ok_s = (h1_dir[i] <= 0) if use_h1 else True
                
                # BUY: Sweep de minimo reciente + rechazo verde
                if (l[i] <= rec_lo[i]) and (c[i] > rec_lo[i]) and (c[i] > o[i]) and (lower_wick[i] >= 0.35) and (clv[i] >= 0.70) and h1_ok_l:
                    sigs[i] = 1
                # SELL: Sweep de maximo reciente + rechazo rojo
                elif (h[i] >= rec_hi[i]) and (c[i] < rec_hi[i]) and (c[i] < o[i]) and (upper_wick[i] >= 0.35) and (clv[i] <= 0.30) and h1_ok_s:
                    sigs[i] = -1
                    
            trades = []
            i = 0
            while i < n - 1:
                s = sigs[i]
                if s == 0:
                    i += 1
                    continue
                k = i + 1
                if k >= n: break
                
                entry_t = df.index[k]
                if s == 1:
                    entry_px = o[k] + spr_d * 0.5
                    tp_px = entry_px + tgt_d
                    sl_px = entry_px - sl_d
                    cur_sl = sl_px
                    be_trig_px = entry_px + be_trig_d
                    be_lock_px = entry_px + be_lock_d
                    exit_px = None
                    for j in range(k, min(n, k + 8)):
                        if l[j] <= cur_sl and h[j] >= tp_px:
                            exit_px = cur_sl if c[j] < o[j] else tp_px
                            break
                        elif l[j] <= cur_sl:
                            exit_px = cur_sl
                            break
                        elif h[j] >= tp_px:
                            exit_px = tp_px
                            break
                        if h[j] >= be_trig_px and cur_sl < be_lock_px:
                            cur_sl = be_lock_px
                    if exit_px is None:
                        j = min(n - 1, k + 7)
                        exit_px = c[j] - spr_d * 0.5
                    pnl_p = (exit_px - entry_px - spr_d * 0.5) / pip
                    trades.append({"time": entry_t, "pnl": pnl_p, "r": pnl_p / 5.5, "win": 1 if pnl_p > 0 else 0})
                    i = j + 1
                elif s == -1:
                    entry_px = o[k] - spr_d * 0.5
                    tp_px = entry_px - tgt_d
                    sl_px = entry_px + sl_d
                    cur_sl = sl_px
                    be_trig_px = entry_px - be_trig_d
                    be_lock_px = entry_px - be_lock_d
                    exit_px = None
                    for j in range(k, min(n, k + 8)):
                        if h[j] >= cur_sl and l[j] <= tp_px:
                            exit_px = cur_sl if c[j] > o[j] else tp_px
                            break
                        elif h[j] >= cur_sl:
                            exit_px = cur_sl
                            break
                        elif l[j] <= tp_px:
                            exit_px = tp_px
                            break
                        if l[j] <= be_trig_px and cur_sl > be_lock_px:
                            cur_sl = be_lock_px
                    if exit_px is None:
                        j = min(n - 1, k + 7)
                        exit_px = c[j] + spr_d * 0.5
                    pnl_p = (entry_px - exit_px - spr_d * 0.5) / pip
                    trades.append({"time": entry_t, "pnl": pnl_p, "r": pnl_p / 5.5, "win": 1 if pnl_p > 0 else 0})
                    i = j + 1
                    
            tdf = pd.DataFrame(trades)
            m = metrics(tdf["r"].to_numpy())
            tdf_oct = tdf[tdf["time"] >= "2026-10-01"]
            m_oct = metrics(tdf_oct["r"].to_numpy()) if len(tdf_oct) > 0 else {"n": 0, "win_rate": 0, "profit_factor": 0}
            pf_full = f"{m['profit_factor']:.2f}" if m['profit_factor'] is not None else "N/A"
            pf_oct = f"{m_oct['profit_factor']:.2f}" if m_oct['profit_factor'] is not None else "N/A"
            print(
                f"LB={lookback:2d} H1={str(use_h1):5s} -> "
                f"FULL (1Y): N={len(tdf):3d} WR={m['win_rate']:5.1f}% PF={pf_full} Pips={tdf['pnl'].sum():+5.1f}p | "
                f"OCT-26: N={len(tdf_oct):2d} WR={m_oct['win_rate']:5.1f}% PF={pf_oct} Pips={tdf_oct['pnl'].sum():+5.1f}p"
            )

    mt5.shutdown()

if __name__ == "__main__":
    main()
