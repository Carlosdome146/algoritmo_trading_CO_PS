"""Auditoría de robustez histórica de EURUSD Micro-Sweep Reclaim en MT5 (20,000 barras M15).
Evalúa estabilidad mes a mes, drawdown, tasa de acierto y beneficio.
"""
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
        print("ERROR MT5")
        return
        
    rates = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_M15, 0, 25000)
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    
    c = df["close"].values
    h = df["high"].values
    l = df["low"].values
    o = df["open"].values
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
    
    print(f"Rango de datos analizado: {df.index[0]} a {df.index[-1]} ({len(df)} barras M15)")
    
    for lookback in [16, 20]:
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
                trades.append({"time": entry_t, "pnl": pnl_p, "r": pnl_p / 5.5, "win": 1 if pnl_p > 0 else 0, "dir": "BUY"})
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
                trades.append({"time": entry_t, "pnl": pnl_p, "r": pnl_p / 5.5, "win": 1 if pnl_p > 0 else 0, "dir": "SELL"})
                i = j + 1
                
        tdf = pd.DataFrame(trades)
        m = metrics(tdf["r"].to_numpy())
        print(f"\n==================================================")
        print(f"ESTRATEGIA SWEEP_{lookback}b EURUSD M15 (HISTORIAL COMPLETO)")
        print(f"Operaciones totales: {len(tdf)}")
        print(f"Tasa de Acierto (Win Rate): {m['win_rate']:.2f}%")
        print(f"Profit Factor: {m['profit_factor']:.2f}")
        print(f"Retorno acumulado: {tdf['r'].sum():+.2f} R | Pips: {tdf['pnl'].sum():+.1f} pips")
        print(f"Max Drawdown R: {m['max_drawdown_r']:.2f} R")
        
        # Desglose por mes
        tdf["month"] = tdf["time"].dt.to_period("M")
        print("\nDesglose mensual:")
        for month, grp in tdf.groupby("month"):
            m_g = metrics(grp["r"].to_numpy())
            print(f"  {month} -> N={len(grp):2d} | WR={m_g['win_rate']:5.1f}% | PF={m_g['profit_factor']:4.2f} | R={grp['r'].sum():+5.2f}R | Pips={grp['pnl'].sum():+5.1f}p")

    mt5.shutdown()

if __name__ == "__main__":
    main()
