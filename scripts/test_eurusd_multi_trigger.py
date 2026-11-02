"""Test de combinación multi-gatillo (Sweep 12b + BB Reversion) en EURUSD M15 para hoy y Octubre 2026."""
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
        
    rates = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_M15, 0, 4000)
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
    
    # Bollinger e indicadores
    sma20 = pd.Series(c).rolling(20, min_periods=10).mean().values
    std20 = pd.Series(c).rolling(20, min_periods=10).std(ddof=0).values
    bb_hi = sma20 + 2.0 * std20
    bb_lo = sma20 - 2.0 * std20
    
    delta = pd.Series(c).diff()
    up = delta.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    rsi2 = (100 - 100 / (1 + up / dn.replace(0, np.nan))).values
    
    pip = 0.00010
    spr_d = 0.8 * pip
    tgt_d = 3.5 * pip
    sl_d = 5.5 * pip
    be_trig_d = 2.0 * pip
    be_lock_d = 0.5 * pip
    
    for lookback in [8, 12]:
        rec_hi = pd.Series(h).shift(1).rolling(lookback, min_periods=3).max().values
        rec_lo = pd.Series(l).shift(1).rolling(lookback, min_periods=3).min().values
        
        sigs = np.zeros(n, dtype=int)
        sig_type = {}
        for i in range(25, n):
            if dows[i] >= 5: continue
            if not (6 <= hrs[i] <= 19): continue
            
            # 1. Sweep Reclaim
            sweep_l = (l[i] <= rec_lo[i]) and (c[i] > rec_lo[i]) and (c[i] > o[i]) and (lower_wick[i] >= 0.35) and (clv[i] >= 0.65)
            sweep_s = (h[i] >= rec_hi[i]) and (c[i] < rec_hi[i]) and (c[i] < o[i]) and (upper_wick[i] >= 0.35) and (clv[i] <= 0.35)
            
            # 2. Bollinger Band Exhaustion
            bb_l = (l[i] <= bb_lo[i]) and (c[i] > o[i]) and (lower_wick[i] >= 0.30) and (rsi2[i] < 20.0)
            bb_s = (h[i] >= bb_hi[i]) and (c[i] < o[i]) and (upper_wick[i] >= 0.30) and (rsi2[i] > 80.0)
            
            if sweep_l or bb_l:
                sigs[i] = 1
                sig_type[i] = "SWEEP_L" if sweep_l else "BB_L"
            elif sweep_s or bb_s:
                sigs[i] = -1
                sig_type[i] = "SWEEP_S" if sweep_s else "BB_S"
                
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
            t_type = sig_type.get(i, "UNKNOWN")
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
                trades.append({"entry_time": entry_t, "type": t_type, "dir": "BUY", "pnl": pnl_p, "r": pnl_p / 5.5, "win": 1 if pnl_p > 0 else 0})
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
                trades.append({"entry_time": entry_t, "type": t_type, "dir": "SELL", "pnl": pnl_p, "r": pnl_p / 5.5, "win": 1 if pnl_p > 0 else 0})
                i = j + 1
                
        tdf = pd.DataFrame(trades)
        tdf_oct = tdf[tdf["entry_time"] >= "2026-10-01"]
        tdf_today = tdf[tdf["entry_time"] >= "2026-11-02 00:00:00"]
        m_oct = metrics(tdf_oct["r"].to_numpy())
        print(f"\n=======================================================")
        print(f"COMBINADO SWEEP_{lookback}b + BB_REVERSION | OCTUBRE 2026:")
        print(f"Trades en Octubre: {len(tdf_oct)} | Win Rate: {m_oct['win_rate']:.1f}% | PF: {m_oct['profit_factor']:.2f} | Pips: {tdf_oct['pnl'].sum():+.1f}p")
        print(f"Trades HOY (2026-11-02): {len(tdf_today)}")
        for _, r in tdf_today.iterrows():
            print(f"  [{r['dir']} {r['type']}] {r['entry_time'].strftime('%H:%M')} UTC | PnL: {r['pnl']:+.1f} pips | {'WIN' if r['win'] else 'LOSS'}")

    mt5.shutdown()

if __name__ == "__main__":
    main()
