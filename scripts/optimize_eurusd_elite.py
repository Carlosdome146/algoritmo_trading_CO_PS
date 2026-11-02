"""Optimizador Sistemático Élite para EURUSD en MT5 (Octubre 2026 completo).

Busca las mejores combinaciones de alta tasa de acierto (>= 75%) y alta frecuencia
para EURUSD sin bloqueos artificiales:
- Horas ampliadas (06:00 a 20:00 UTC o 24h).
- Sin límite de trades al día.
- Ambos sentidos (LONG y SHORT).
- M5 y M15.
- Simulación exacta con Spread real (0.8 pips) y Breakeven.
"""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timezone

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from trading_v2.research.regime_lab_v3 import metrics

def get_eurusd_data(tf_code, n_bars=12000):
    if not mt5.initialize():
        print("ERROR: MT5 no inicializado")
        sys.exit(1)
    rates = mt5.copy_rates_from_pos("EURUSD", tf_code, 0, n_bars)
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    # Filtrar desde 2026-10-01
    return df[df.index >= "2026-10-01"].copy()

def backtest_vectorized(df, sigs, tgt_pips, sl_pips, be_trig_pips=None, be_lock_pips=0.5, spread_pips=0.8, max_hold=8):
    c = df["close"].values
    h = df["high"].values
    l = df["low"].values
    o = df["open"].values
    n = len(df)
    
    pip = 0.00010
    tgt_d = tgt_pips * pip
    sl_d = sl_pips * pip
    spr_d = spread_pips * pip
    be_trig_d = (be_trig_pips * pip) if be_trig_pips else None
    be_lock_d = (be_lock_pips * pip) if be_lock_pips else None
    
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
            be_trig_px = entry_px + be_trig_d if be_trig_d else None
            be_lock_px = entry_px + be_lock_d if be_lock_d else None
            exit_px = None
            
            for j in range(k, min(n, k + max_hold)):
                if l[j] <= cur_sl and h[j] >= tp_px:
                    exit_px = cur_sl if c[j] < o[j] else tp_px
                    break
                elif l[j] <= cur_sl:
                    exit_px = cur_sl
                    break
                elif h[j] >= tp_px:
                    exit_px = tp_px
                    break
                if be_trig_px and h[j] >= be_trig_px and cur_sl < be_lock_px:
                    cur_sl = be_lock_px
                    
            if exit_px is None:
                j = min(n - 1, k + max_hold - 1)
                exit_px = c[j] - spr_d * 0.5
                
            pnl_pips = (exit_px - entry_px - spr_d * 0.5) / pip
            r = pnl_pips / sl_pips
            trades.append({"time": entry_t, "pnl": pnl_pips, "r": r, "win": 1 if pnl_pips > 0 else 0, "dir": "BUY"})
            i = j + 1
            
        elif s == -1:
            entry_px = o[k] - spr_d * 0.5
            tp_px = entry_px - tgt_d
            sl_px = entry_px + sl_d
            cur_sl = sl_px
            be_trig_px = entry_px - be_trig_d if be_trig_d else None
            be_lock_px = entry_px - be_lock_d if be_lock_d else None
            exit_px = None
            
            for j in range(k, min(n, k + max_hold)):
                if h[j] >= cur_sl and l[j] <= tp_px:
                    exit_px = cur_sl if c[j] > o[j] else tp_px
                    break
                elif h[j] >= cur_sl:
                    exit_px = cur_sl
                    break
                elif l[j] <= tp_px:
                    exit_px = tp_px
                    break
                if be_trig_px and l[j] <= be_trig_px and cur_sl > be_lock_px:
                    cur_sl = be_lock_px
                    
            if exit_px is None:
                j = min(n - 1, k + max_hold - 1)
                exit_px = c[j] + spr_d * 0.5
                
            pnl_pips = (entry_px - exit_px - spr_d * 0.5) / pip
            r = pnl_pips / sl_pips
            trades.append({"time": entry_t, "pnl": pnl_pips, "r": r, "win": 1 if pnl_pips > 0 else 0, "dir": "SELL"})
            i = j + 1
            
    return pd.DataFrame(trades)

def main():
    print("Iniciando busqueda de configuraciones ganadoras en EURUSD (Octubre 2026)...")
    
    # 1. Probar en M15
    df_m15 = get_eurusd_data(mt5.TIMEFRAME_M15, 5000)
    c = df_m15["close"].values
    h = df_m15["high"].values
    l = df_m15["low"].values
    o = df_m15["open"].values
    hrs = df_m15.index.hour.values
    dows = df_m15.index.dayofweek.values
    n = len(df_m15)
    
    rng = np.maximum(h - l, 1e-9)
    lower_wick = (np.minimum(o, c) - l) / rng
    upper_wick = (h - np.maximum(o, c)) / rng
    clv = (c - l) / rng
    
    ema20 = pd.Series(c).ewm(span=20, adjust=False).mean().values
    ema50 = pd.Series(c).ewm(span=50, adjust=False).mean().values
    sma20 = pd.Series(c).rolling(20, min_periods=10).mean().values
    std20 = pd.Series(c).rolling(20, min_periods=10).std(ddof=0).values
    bb_hi = sma20 + 2.0 * std20
    bb_lo = sma20 - 2.0 * std20
    
    delta = pd.Series(c).diff()
    up = delta.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    rsi2 = (100 - 100 / (1 + up / dn.replace(0, np.nan))).values
    
    # Grid de pruebas
    results = []
    
    # Modelo 1: Intraday Micro Liquidity Sweep con Reclaim Fino
    for lookback in [8, 12, 16, 20]:
        rec_hi = pd.Series(h).shift(1).rolling(lookback, min_periods=4).max().values
        rec_lo = pd.Series(l).shift(1).rolling(lookback, min_periods=4).min().values
        
        for min_w in [0.35, 0.40, 0.45]:
            for clv_thresh in [0.60, 0.65, 0.70]:
                for h_filter in ["none", "ema20_dir", "ema50_dir"]:
                    sigs = np.zeros(n, dtype=int)
                    for i in range(lookback + 5, n):
                        if dows[i] >= 5: continue
                        # Horas ampliadas: 06:00 a 20:00 UTC (Londres + NY completo)
                        if not (6 <= hrs[i] <= 19): continue
                        
                        trend_l = True
                        trend_s = True
                        if h_filter == "ema20_dir":
                            trend_l = c[i] > ema20[i]
                            trend_s = c[i] < ema20[i]
                        elif h_filter == "ema50_dir":
                            trend_l = c[i] > ema50[i]
                            trend_s = c[i] < ema50[i]
                            
                        # BUY: Barrido de minimo previo + vela verde/rechazo
                        if (l[i] <= rec_lo[i]) and (c[i] > rec_lo[i]) and (c[i] > o[i]) and (lower_wick[i] >= min_w) and (clv[i] >= clv_thresh) and trend_l:
                            sigs[i] = 1
                        # SELL: Barrido de maximo previo + vela roja/rechazo
                        elif (h[i] >= rec_hi[i]) and (c[i] < rec_hi[i]) and (c[i] < o[i]) and (upper_wick[i] >= min_w) and (clv[i] <= (1.0 - clv_thresh)) and trend_s:
                            sigs[i] = -1
                            
                    for tgt, sl, be_t in [(3.0, 5.0, 2.0), (3.5, 5.5, 2.0), (4.0, 6.0, 2.5), (4.5, 7.0, 2.5), (5.0, 7.5, 3.0)]:
                        tdf = backtest_vectorized(df_m15, sigs, tgt_pips=tgt, sl_pips=sl, be_trig_pips=be_t, max_hold=8)
                        if len(tdf) >= 15:
                            m = metrics(tdf["r"].to_numpy())
                            if m["win_rate"] >= 75.0 and m["profit_factor"] >= 1.30:
                                results.append({
                                    "modelo": f"Sweep_{lookback}b",
                                    "wick": min_w,
                                    "clv": clv_thresh,
                                    "filtro": h_filter,
                                    "tgt": tgt,
                                    "sl": sl,
                                    "be": be_t,
                                    "trades": len(tdf),
                                    "wr": round(m["win_rate"], 1),
                                    "pf": round(m["profit_factor"], 2),
                                    "sum_r": round(float(tdf["r"].sum()), 2),
                                    "pips": round(float(tdf["pnl"].sum()), 1),
                                })

    # Modelo 2: Mean Reversion Bollinger Band Exhaustion (Band Touch + RSI2 Extreme + Wick)
    for bb_mult in [2.0, 2.2]:
        bb_hi_c = sma20 + bb_mult * std20
        bb_lo_c = sma20 - bb_mult * std20
        for rsi_buy, rsi_sell in [(15, 85), (20, 80), (25, 75)]:
            for min_w in [0.30, 0.35, 0.40]:
                sigs = np.zeros(n, dtype=int)
                for i in range(25, n):
                    if dows[i] >= 5: continue
                    if not (6 <= hrs[i] <= 19): continue
                    
                    if (l[i] <= bb_lo_c[i]) and (c[i] > o[i]) and (lower_wick[i] >= min_w) and (rsi2[i] <= rsi_buy):
                        sigs[i] = 1
                    elif (h[i] >= bb_hi_c[i]) and (c[i] < o[i]) and (upper_wick[i] >= min_w) and (rsi2[i] >= rsi_sell):
                        sigs[i] = -1
                        
                for tgt, sl, be_t in [(3.0, 5.0, 2.0), (3.5, 5.5, 2.0), (4.0, 6.0, 2.5), (4.5, 7.0, 2.5)]:
                    tdf = backtest_vectorized(df_m15, sigs, tgt_pips=tgt, sl_pips=sl, be_trig_pips=be_t, max_hold=8)
                    if len(tdf) >= 12:
                        m = metrics(tdf["r"].to_numpy())
                        if m["win_rate"] >= 75.0 and m["profit_factor"] >= 1.30:
                            results.append({
                                "modelo": f"BB_{bb_mult}std",
                                "wick": min_w,
                                "clv": rsi_buy,
                                "filtro": "RSI2_Extreme",
                                "tgt": tgt,
                                "sl": sl,
                                "be": be_t,
                                "trades": len(tdf),
                                "wr": round(m["win_rate"], 1),
                                "pf": round(m["profit_factor"], 2),
                                "sum_r": round(float(tdf["r"].sum()), 2),
                                "pips": round(float(tdf["pnl"].sum()), 1),
                            })

    rdf = pd.DataFrame(results)
    if not rdf.empty:
        rdf = rdf.sort_values(by=["wr", "pf", "trades"], ascending=[False, False, False])
        print("\nTOP CONFIGURACIONES GANADORAS EN EURUSD M15 (OCTUBRE 2026):")
        print(rdf.head(25).to_string(index=False))
    else:
        print("No se encontraron configuraciones que cumplan el filtro estricto.")

    mt5.shutdown()

if __name__ == "__main__":
    main()
