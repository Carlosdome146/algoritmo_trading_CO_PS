"""Verifica qué operaciones habría ejecutado la nueva estrategia EURUSD M15 hoy (2026-11-02)."""
from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

def main():
    if not mt5.initialize():
        return
        
    rates = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_M15, 0, 500)
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    
    c = df["close"].values
    h = df["high"].values
    l = df["low"].values
    o = df["open"].values
    n = len(df)
    
    rng = np.maximum(h - l, 1e-9)
    lower_wick = (np.minimum(o, c) - l) / rng
    upper_wick = (h - np.maximum(o, c)) / rng
    clv = (c - l) / rng
    hrs = df.index.hour.values
    dows = df.index.dayofweek.values
    
    pip = 0.00010
    spr_d = 0.8 * pip
    tgt_d = 3.5 * pip
    sl_d = 5.5 * pip
    be_trig_d = 2.0 * pip
    be_lock_d = 0.5 * pip
    
    lookback = 16
    rec_hi = pd.Series(h).shift(1).rolling(lookback, min_periods=4).max().values
    rec_lo = pd.Series(l).shift(1).rolling(lookback, min_periods=4).min().values
    
    sigs = np.zeros(n, dtype=int)
    for i in range(lookback + 5, n):
        if dows[i] >= 5: continue
        if not (6 <= hrs[i] <= 19): continue
        
        # BUY
        if (l[i] <= rec_lo[i]) and (c[i] > rec_lo[i]) and (c[i] > o[i]) and (lower_wick[i] >= 0.35) and (clv[i] >= 0.70):
            sigs[i] = 1
        # SELL
        elif (h[i] >= rec_hi[i]) and (c[i] < rec_hi[i]) and (c[i] < o[i]) and (upper_wick[i] >= 0.35) and (clv[i] <= 0.30):
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
            exit_reason = None
            for j in range(k, min(n, k + 8)):
                if l[j] <= cur_sl and h[j] >= tp_px:
                    exit_px = cur_sl if c[j] < o[j] else tp_px
                    exit_reason = "SL" if c[j] < o[j] else "TP"
                    break
                elif l[j] <= cur_sl:
                    exit_px = cur_sl
                    exit_reason = "SL"
                    break
                elif h[j] >= tp_px:
                    exit_px = tp_px
                    exit_reason = "TP"
                    break
                if h[j] >= be_trig_px and cur_sl < be_lock_px:
                    cur_sl = be_lock_px
            if exit_px is None:
                j = min(n - 1, k + 7)
                exit_px = c[j] - spr_d * 0.5
                exit_reason = "TIME"
            pnl_p = (exit_px - entry_px - spr_d * 0.5) / pip
            trades.append({"signal_time": df.index[i], "entry_time": entry_t, "exit_time": df.index[j], "dir": "BUY", "entry": entry_px, "exit": exit_px, "pnl_pips": pnl_p, "reason": exit_reason, "win": pnl_p > 0})
            i = j + 1
        elif s == -1:
            entry_px = o[k] - spr_d * 0.5
            tp_px = entry_px - tgt_d
            sl_px = entry_px + sl_d
            cur_sl = sl_px
            be_trig_px = entry_px - be_trig_d
            be_lock_px = entry_px - be_lock_d
            exit_px = None
            exit_reason = None
            for j in range(k, min(n, k + 8)):
                if h[j] >= cur_sl and l[j] <= tp_px:
                    exit_px = cur_sl if c[j] > o[j] else tp_px
                    exit_reason = "SL" if c[j] > o[j] else "TP"
                    break
                elif h[j] >= cur_sl:
                    exit_px = cur_sl
                    exit_reason = "SL"
                    break
                elif l[j] <= tp_px:
                    exit_px = tp_px
                    exit_reason = "TP"
                    break
                if l[j] <= be_trig_px and cur_sl > be_lock_px:
                    cur_sl = be_lock_px
            if exit_px is None:
                j = min(n - 1, k + 7)
                exit_px = c[j] + spr_d * 0.5
                exit_reason = "TIME"
            pnl_p = (entry_px - exit_px - spr_d * 0.5) / pip
            trades.append({"signal_time": df.index[i], "entry_time": entry_t, "exit_time": df.index[j], "dir": "SELL", "entry": entry_px, "exit": exit_px, "pnl_pips": pnl_p, "reason": exit_reason, "win": pnl_p > 0})
            i = j + 1
            
    tdf = pd.DataFrame(trades)
    tdf_today = tdf[tdf["entry_time"] >= "2026-11-02 00:00:00"]
    print("OPERACIONES EURUSD HOY (2026-11-02):")
    if not tdf_today.empty:
        for _, r in tdf_today.iterrows():
            print(f"[{r['dir']}] Entrada: {r['entry_time'].strftime('%H:%M')} UTC a {r['entry']:.5f} | Salida: {r['exit_time'].strftime('%H:%M')} UTC a {r['exit']:.5f} | PnL: {r['pnl_pips']:+.1f} pips ({r['reason']}) | {'WIN' if r['win'] else 'LOSS'}")
    else:
        print("No hubo operaciones registradas hoy.")

    mt5.shutdown()

if __name__ == "__main__":
    main()
