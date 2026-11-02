"""Test bidireccional (LONG + SHORT) del patrón Ismael Sweep Reclaim + BB Rebound en EURUSD M15.
Analiza tanto el último año completo como el último mes de Octubre 2026.
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
    
    tr = np.maximum(h - l, np.abs(h - pd.Series(c).shift(1).fillna(c[0]).values))
    atr = pd.Series(tr).rolling(14, min_periods=5).mean().values
    
    delta = pd.Series(c).diff()
    up = delta.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    rsi2 = (100 - 100 / (1 + up / dn.replace(0, np.nan))).values
    
    sma200 = pd.Series(c).rolling(200, min_periods=50).mean().values
    ema50 = pd.Series(c).ewm(span=50, adjust=False).mean().values
    ema20 = pd.Series(c).ewm(span=20, adjust=False).mean().values
    sma20 = pd.Series(c).rolling(20, min_periods=10).mean().values
    std20 = pd.Series(c).rolling(20, min_periods=10).std(ddof=0).values
    bb_lo = sma20 - 2.0 * std20
    bb_hi = sma20 + 2.0 * std20
    
    rng = np.maximum(h - l, 1e-9)
    lower_wick = (np.minimum(o, c) - l) / rng
    upper_wick = (h - np.maximum(o, c)) / rng
    clv = (c - l) / rng
    
    rec_lo = pd.Series(l).shift(1).rolling(8, min_periods=3).min().values
    rec_hi = pd.Series(h).shift(1).rolling(8, min_periods=3).max().values
    hrs = df.index.hour.values
    dows = df.index.dayofweek.values
    
    spr_cost = 0.00008  # 0.8 pips
    
    # Probar diferentes combinaciones
    for trend_type in ["sma200_trend", "ema50_trend", "ema20_cross", "multi_regime"]:
        for wick_req in [0.40, 0.45, 0.50]:
            for tp_atr_mult, sl_atr_mult in [(0.50, 1.20), (0.60, 1.50), (0.45, 1.00)]:
                trades = []
                i = 210
                while i < n - 1:
                    if dows[i] >= 5:
                        i += 1
                        continue
                    # Horas ampliadas: 06:00 a 20:00 UTC
                    if not (6 <= hrs[i] <= 19):
                        i += 1
                        continue
                    cur_atr = atr[i]
                    if not np.isfinite(cur_atr) or cur_atr <= 0:
                        i += 1
                        continue
                        
                    # Tendencia
                    if trend_type == "sma200_trend":
                        bull = (c[i] > sma200[i]) and (ema20[i] > sma200[i])
                        bear = (c[i] < sma200[i]) and (ema20[i] < sma200[i])
                    elif trend_type == "ema50_trend":
                        bull = (c[i] > ema50[i]) and (ema20[i] > ema50[i])
                        bear = (c[i] < ema50[i]) and (ema20[i] < ema50[i])
                    elif trend_type == "ema20_cross":
                        bull = (ema20[i] > ema50[i])
                        bear = (ema20[i] < ema50[i])
                    else: # multi_regime (EMA20 + Keltner)
                        bull = (c[i] > ema20[i])
                        bear = (c[i] < ema20[i])
                        
                    sig = 0
                    # LONG: Sweep de minimo + rechazo verde
                    if bull and (l[i] <= rec_lo[i]) and (c[i] > rec_lo[i]) and (c[i] > o[i]) and (lower_wick[i] >= wick_req) and (clv[i] >= 0.70):
                        sig = 1
                    # LONG BB dip
                    elif bull and (l[i] <= bb_lo[i]) and (c[i] > o[i]) and (rsi2[i] < 15.0) and (lower_wick[i] >= 0.35):
                        sig = 1
                    # SHORT: Sweep de maximo + rechazo rojo
                    elif bear and (h[i] >= rec_hi[i]) and (c[i] < rec_hi[i]) and (c[i] < o[i]) and (upper_wick[i] >= wick_req) and (clv[i] <= 0.30):
                        sig = -1
                    # SHORT BB top
                    elif bear and (h[i] >= bb_hi[i]) and (c[i] < o[i]) and (rsi2[i] > 85.0) and (upper_wick[i] >= 0.35):
                        sig = -1
                        
                    if sig == 0:
                        i += 1
                        continue
                        
                    k = i + 1
                    if sig == 1:
                        entry = o[k] + spr_cost * 0.5
                        tp_px = entry + tp_atr_mult * cur_atr
                        cur_sl = entry - sl_atr_mult * cur_atr
                        be_trig = entry + 0.35 * cur_atr
                        be_lock = entry + 0.05 * cur_atr
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
                            if c[j] >= be_trig and cur_sl < be_lock:
                                cur_sl = be_lock
                        if exit_px is None:
                            j = min(n - 1, k + 7)
                            exit_px = c[j] - spr_cost * 0.5
                        pnl = exit_px - entry - spr_cost * 0.5
                        r_val = pnl / (sl_atr_mult * cur_atr)
                        trades.append({"time": df.index[k], "pnl": pnl, "r": r_val, "win": 1 if pnl > 0 else 0, "dir": "BUY"})
                        i = j + 1
                    elif sig == -1:
                        entry = o[k] - spr_cost * 0.5
                        tp_px = entry - tp_atr_mult * cur_atr
                        cur_sl = entry + sl_atr_mult * cur_atr
                        be_trig = entry - 0.35 * cur_atr
                        be_lock = entry - 0.05 * cur_atr
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
                            if c[j] <= be_trig and cur_sl > be_lock:
                                cur_sl = be_lock
                        if exit_px is None:
                            j = min(n - 1, k + 7)
                            exit_px = c[j] + spr_cost * 0.5
                        pnl = entry - exit_px - spr_cost * 0.5
                        r_val = pnl / (sl_atr_mult * cur_atr)
                        trades.append({"time": df.index[k], "pnl": pnl, "r": r_val, "win": 1 if pnl > 0 else 0, "dir": "SELL"})
                        i = j + 1
                        
                tdf = pd.DataFrame(trades)
                if len(tdf) >= 15:
                    m = metrics(tdf["r"].to_numpy())
                    tdf_oct = tdf[tdf["time"] >= "2026-10-01"]
                    m_oct = metrics(tdf_oct["r"].to_numpy()) if len(tdf_oct) > 0 else {"n": 0, "win_rate": 0, "profit_factor": 0}
                    print(
                        f"Trend={trend_type:13s} | Wick>={wick_req:.2f} | TP={tp_atr_mult} SL={sl_atr_mult} -> "
                        f"FULL: N={len(tdf):3d} WR={m['win_rate']:5.1f}% PF={m['profit_factor']:4.2f} SumR={tdf['r'].sum():+5.1f}R | "
                        f"OCT: N={len(tdf_oct):2d} WR={m_oct['win_rate']:5.1f}% PF={m_oct['profit_factor']:4.2f}"
                    )
                        
    mt5.shutdown()

if __name__ == "__main__":
    main()
