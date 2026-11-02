"""Auditoría de EURUSD M5 con filtros de precisión para alta frecuencia intradía."""
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
        
    rates = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_M5, 0, 15000)
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    df_oct = df[df.index >= "2026-10-01"].copy()
    
    c = df_oct["close"].values
    h = df_oct["high"].values
    l = df_oct["low"].values
    o = df_oct["open"].values
    n = len(df_oct)
    
    rng = np.maximum(h - l, 1e-9)
    lower_wick = (np.minimum(o, c) - l) / rng
    upper_wick = (h - np.maximum(o, c)) / rng
    clv = (c - l) / rng
    hrs = df_oct.index.hour.values
    dows = df_oct.index.dayofweek.values
    
    ema20 = pd.Series(c).ewm(span=20, adjust=False).mean().values
    ema50 = pd.Series(c).ewm(span=50, adjust=False).mean().values
    
    pip = 0.00010
    spr_d = 0.8 * pip
    
    print(f"Barras M5 en Octubre 2026: {n}")
    
    for lookback in [12, 18, 24, 36]:
        rec_hi = pd.Series(h).shift(1).rolling(lookback, min_periods=4).max().values
        rec_lo = pd.Series(l).shift(1).rolling(lookback, min_periods=4).min().values
        
        for min_w in [0.40, 0.45, 0.50]:
            for clv_t in [0.70, 0.75]:
                for trend_req in ["none", "ema_cross"]:
                    sigs = np.zeros(n, dtype=int)
                    for i in range(lookback + 5, n):
                        if dows[i] >= 5: continue
                        if not (6 <= hrs[i] <= 19): continue
                        
                        trend_l = (ema20[i] > ema50[i]) if trend_req == "ema_cross" else True
                        trend_s = (ema20[i] < ema50[i]) if trend_req == "ema_cross" else True
                        
                        # BUY
                        if (l[i] <= rec_lo[i]) and (c[i] > rec_lo[i]) and (c[i] > o[i]) and (lower_wick[i] >= min_w) and (clv[i] >= clv_t) and trend_l:
                            sigs[i] = 1
                        # SELL
                        elif (h[i] >= rec_hi[i]) and (c[i] < rec_hi[i]) and (c[i] < o[i]) and (upper_wick[i] >= min_w) and (clv[i] <= (1.0 - clv_t)) and trend_s:
                            sigs[i] = -1
                            
                    for tgt_p, sl_p, be_p in [(2.5, 4.0, 1.5), (3.0, 4.5, 1.8), (3.5, 5.0, 2.0)]:
                        tgt_d = tgt_p * pip
                        sl_d = sl_p * pip
                        be_trig_d = be_p * pip
                        be_lock_d = 0.5 * pip
                        
                        trades = []
                        i = 0
                        while i < n - 1:
                            s = sigs[i]
                            if s == 0:
                                i += 1
                                continue
                            k = i + 1
                            if k >= n: break
                            
                            entry_t = df_oct.index[k]
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
                                trades.append({"time": entry_t, "pnl": pnl_p, "r": pnl_p / sl_p, "win": 1 if pnl_p > 0 else 0})
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
                                trades.append({"time": entry_t, "pnl": pnl_p, "r": pnl_p / sl_p, "win": 1 if pnl_p > 0 else 0})
                                i = j + 1
                                
                        tdf = pd.DataFrame(trades)
                        if len(tdf) >= 20:
                            m = metrics(tdf["r"].to_numpy())
                            if m["win_rate"] >= 75.0 and m["profit_factor"] >= 1.30:
                                print(
                                    f"M5 LB={lookback:2d} W>={min_w:.2f} CLV>={clv_t:.2f} {trend_req:9s} | Tgt={tgt_p} SL={sl_p} BE={be_p} -> "
                                    f"OCT: N={len(tdf):2d} WR={m['win_rate']:5.1f}% PF={m['profit_factor']:4.2f} Pips={tdf['pnl'].sum():+5.1f}p"
                                )
                                
    mt5.shutdown()

if __name__ == "__main__":
    main()
