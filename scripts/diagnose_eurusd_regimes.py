"""Desglose mes a mes de Sweep_16b en EURUSD M15 y test de filtros de régimen cuantitativos."""
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
        
    rates = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_M15, 0, 35000)
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
    
    # ATR y Medias
    prev_c = pd.Series(c).shift(1).fillna(c[0]).values
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    atr14 = pd.Series(tr).rolling(14, min_periods=5).mean().values
    atr_ma = pd.Series(atr14).rolling(50, min_periods=10).mean().values
    vol_ratio = atr14 / np.maximum(atr_ma, 1e-9)
    
    ema20 = pd.Series(c).ewm(span=20, adjust=False).mean().values
    ema50 = pd.Series(c).ewm(span=50, adjust=False).mean().values
    
    pip = 0.00010
    spr_d = 0.8 * pip
    tgt_d = 3.5 * pip
    sl_d = 5.5 * pip
    be_trig_d = 2.0 * pip
    be_lock_d = 0.5 * pip
    
    rec_hi = pd.Series(h).shift(1).rolling(16, min_periods=4).max().values
    rec_lo = pd.Series(l).shift(1).rolling(16, min_periods=4).min().values
    
    for regime_filter in ["none", "vol_expansion", "ema20_slope", "session_selective"]:
        sigs = np.zeros(n, dtype=int)
        for i in range(25, n):
            if dows[i] >= 5: continue
            
            # Filtro de sesion
            if regime_filter == "session_selective":
                # Horas de mayor liquidez: 07:00 a 16:00 UTC (Frankfurt + Londres + Solape NY)
                if not (7 <= hrs[i] <= 16): continue
            else:
                if not (6 <= hrs[i] <= 19): continue
                
            # Filtro de volatilidad
            if regime_filter == "vol_expansion":
                if vol_ratio[i] < 0.85: continue
                
            # Filtro de pendiente
            slope_ok_l = True
            slope_ok_s = True
            if regime_filter == "ema20_slope":
                slope_ok_l = ema20[i] >= ema20[i-4]
                slope_ok_s = ema20[i] <= ema20[i-4]
                
            # BUY
            if (l[i] <= rec_lo[i]) and (c[i] > rec_lo[i]) and (c[i] > o[i]) and (lower_wick[i] >= 0.35) and (clv[i] >= 0.70) and slope_ok_l:
                sigs[i] = 1
            # SELL
            elif (h[i] >= rec_hi[i]) and (c[i] < rec_hi[i]) and (c[i] < o[i]) and (upper_wick[i] >= 0.35) and (clv[i] <= 0.30) and slope_ok_s:
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
        print(f"\n=======================================================")
        print(f"REGIME FILTER: {regime_filter} -> N={len(tdf)} | WR={m['win_rate']:.1f}% | PF={m['profit_factor']:.2f} | Pips={tdf['pnl'].sum():+.1f}p")
        tdf["month"] = tdf["time"].dt.to_period("M")
        for month, grp in tdf.groupby("month"):
            mg = metrics(grp["r"].to_numpy())
            print(f"   {month} -> N={len(grp):2d} | WR={mg['win_rate']:5.1f}% | PF={mg['profit_factor']:4.2f} | Pips={grp['pnl'].sum():+5.1f}p")

    mt5.shutdown()

if __name__ == "__main__":
    main()
