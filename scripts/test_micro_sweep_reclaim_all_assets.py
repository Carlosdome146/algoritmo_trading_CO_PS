"""Prueba de extrapolación directa del modelo EURUSD Micro-Sweep Reclaim a TODOS los activos.

Mecanismo idéntico a EURUSD:
1. Barrido de extremo de 16 velas (High o Low).
2. Cierre de vuelta dentro del rango (Reclaim).
3. Vela direccional confirmada (Verde para BUY, Roja para SELL).
4. Mecha de rechazo >= 35%.
5. CLV >= 0.65 para BUY, <= 0.35 para SELL.
6. Breakeven Causal rápido al alcanzar el 40-50% del TP.
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

def test_asset(symbol, tf_code, tf_name, spread_pts, tgt_candidates, sl_candidates, be_ratios, s_start, s_end, allow_shorts=True):
    rates = mt5.copy_rates_from_pos(symbol, tf_code, 0, 8000)
    if rates is None or len(rates) < 1000:
        return []
        
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    df_oct = df[df.index >= "2026-10-01"].copy()
    
    c = df_oct["close"].values
    h = df_oct["high"].values
    l = df_oct["low"].values
    o = df_oct["open"].values
    hrs = df_oct.index.hour.values
    dows = df_oct.index.dayofweek.values
    n = len(df_oct)
    
    rng = np.maximum(h - l, 1e-9)
    lower_wick = (np.minimum(o, c) - l) / rng
    upper_wick = (h - np.maximum(o, c)) / rng
    clv = (c - l) / rng
    
    # Sweep de 16 velas
    rec_hi16 = pd.Series(h).shift(1).rolling(16, min_periods=4).max().values
    rec_lo16 = pd.Series(l).shift(1).rolling(16, min_periods=4).min().values
    
    # Señales idénticas a EURUSD
    sigs = np.zeros(n, dtype=int)
    for i in range(25, n):
        if dows[i] >= 5: continue
        if not (s_start <= hrs[i] <= s_end): continue
        
        # BUY
        if (l[i] <= rec_lo16[i]) and (c[i] > rec_lo16[i]) and (c[i] > o[i]) and (lower_wick[i] >= 0.35) and (clv[i] >= 0.65):
            sigs[i] = 1
        # SELL
        elif allow_shorts and (h[i] >= rec_hi16[i]) and (c[i] < rec_hi16[i]) and (c[i] < o[i]) and (upper_wick[i] >= 0.35) and (clv[i] <= 0.35):
            sigs[i] = -1
            
    results = []
    for tgt in tgt_candidates:
        for sl in sl_candidates:
            for be_r in be_ratios:
                be_trig = tgt * be_r
                be_lock = spread_pts * 1.2
                
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
                        entry_px = o[k] + spread_pts * 0.5
                        tp_px = entry_px + tgt
                        sl_px = entry_px - sl
                        cur_sl = sl_px
                        be_trig_px = entry_px + be_trig
                        be_lock_px = entry_px + be_lock
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
                            exit_px = c[j] - spread_pts * 0.5
                        pnl = exit_px - entry_px - spread_pts * 0.5
                        trades.append({"time": entry_t, "pnl": pnl, "r": pnl / sl, "win": 1 if pnl > 0 else 0})
                        i = j + 1
                    elif s == -1:
                        entry_px = o[k] - spread_pts * 0.5
                        tp_px = entry_px - tgt
                        sl_px = entry_px + sl
                        cur_sl = sl_px
                        be_trig_px = entry_px - be_trig
                        be_lock_px = entry_px - be_lock
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
                            exit_px = c[j] + spread_pts * 0.5
                        pnl = entry_px - exit_px - spread_pts * 0.5
                        trades.append({"time": entry_t, "pnl": pnl, "r": pnl / sl, "win": 1 if pnl > 0 else 0})
                        i = j + 1
                        
                tdf = pd.DataFrame(trades)
                if len(tdf) >= 8:
                    m = metrics(tdf["r"].to_numpy())
                    pf_val = m["profit_factor"] if m["profit_factor"] is not None else 99.0
                    if m["win_rate"] >= 75.0 and pf_val >= 1.20:
                        results.append({
                            "symbol": symbol,
                            "tf": tf_name,
                            "dir": "BOTH" if allow_shorts else "LONG",
                            "tgt": tgt,
                            "sl": sl,
                            "be_r": be_r,
                            "trades": len(tdf),
                            "wr": round(m["win_rate"], 1),
                            "pf": round(pf_val, 2),
                            "sum_r": round(float(tdf["r"].sum()), 2),
                            "pnl": round(float(tdf["pnl"].sum()), 1),
                        })
    return results

def main():
    if not mt5.initialize():
        return
        
    print("Iniciando escaneo de extrapolación Micro-Sweep Reclaim a toda la cartera (Octubre 2026)...")
    
    asset_tests = [
        # (symbol, spread_pts, tgts, sls, be_ratios, s_start, s_end)
        ("GERMANY40", 1.2, [10.0, 12.0, 15.0, 18.0, 22.0], [18.0, 25.0, 35.0], [0.35, 0.40, 0.45], 7, 17),
        ("[IBEX35]", 5.0, [15.0, 20.0, 25.0, 30.0], [25.0, 35.0, 45.0], [0.35, 0.40, 0.45], 7, 17),
        ("[SP500]", 0.50, [3.0, 4.0, 5.0, 6.0, 7.5], [6.0, 7.5, 10.0, 12.0], [0.40, 0.45, 0.50], 12, 21),
        ("US100", 1.8, [20.0, 25.0, 30.0, 35.0, 45.0], [40.0, 50.0, 70.0], [0.35, 0.40, 0.45], 12, 21),
        ("[DJI30]", 3.0, [40.0, 55.0, 70.0, 85.0], [80.0, 110.0, 140.0], [0.35, 0.40, 0.45], 12, 21),
        ("GOLD", 0.30, [3.0, 4.0, 5.0, 6.0, 8.0], [6.0, 8.0, 12.0, 15.0], [0.35, 0.40, 0.45], 6, 21),
    ]
    
    all_winners = []
    for sym, spr, tgts, sls, bes, ss, se in asset_tests:
        for tf_code, tf_name in [(mt5.TIMEFRAME_M15, "M15"), (mt5.TIMEFRAME_M30, "M30")]:
            for allow_s in [True, False]:
                res = test_asset(sym, tf_code, tf_name, spr, tgts, sls, bes, ss, se, allow_shorts=allow_s)
                all_winners.extend(res)
                
    wdf = pd.DataFrame(all_winners)
    if not wdf.empty:
        wdf = wdf.sort_values(by=["wr", "pf", "trades"], ascending=[False, False, False])
        print("\nTOP CONFIGURACIONES GANADORAS CON MICRO-SWEEP RECLAIM EN LA CARTERA:")
        # Mostrar el mejor resultado por activo
        top_by_asset = wdf.groupby(["symbol"]).first().reset_index()
        print(top_by_asset[["symbol", "tf", "dir", "tgt", "sl", "be_r", "trades", "wr", "pf", "sum_r", "pnl"]].to_string(index=False))
        
        print("\nTODOS LOS RESULTADOS DESTACADOS:")
        print(wdf.head(20)[["symbol", "tf", "dir", "tgt", "sl", "be_r", "trades", "wr", "pf", "sum_r", "pnl"]].to_string(index=False))
    else:
        print("No se encontraron configuraciones.")
        
    mt5.shutdown()

if __name__ == "__main__":
    main()
