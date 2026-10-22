"""Laboratorio Cuantitativo Intradía M15 / M30 para la Trinidad de Activos.
Prueba de Reversión Dinámica a la Media (RSI2 + Bollinger + Salida por Media Móvil).
"""
from __future__ import annotations

import math
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

from trading_v2.research.regime_lab_v3 import metrics


def test_intraday_reversion(symbol: str, tf_str: str, mt5_tf: int, rsi_th: int, stop_atr: float, exit_ema: int, max_bars: int, use_be: bool = True):
    r = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, 30000)
    if r is None or len(r) == 0:
        return None
    df = pd.DataFrame(r)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    c, h, l, o = df["close"], df["high"], df["low"], df["open"]
    
    # ATR14
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=5).mean().to_numpy()
    
    # RSI2
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    rsi2 = (100 - 100 / (1 + up / dn.replace(0, np.nan))).to_numpy()
    
    sma200 = c.rolling(200, min_periods=50).mean().to_numpy()
    ema_exit = c.ewm(span=exit_ema, adjust=False).mean().to_numpy()
    
    sma20 = c.rolling(20, min_periods=10).mean()
    std20 = c.rolling(20, min_periods=10).std(ddof=0)
    bb_lo = (sma20 - 2.0 * std20).to_numpy()
    bb_up = (sma20 + 2.0 * std20).to_numpy()
    
    c_arr = c.to_numpy()
    o_arr = o.to_numpy()
    h_arr = h.to_numpy()
    l_arr = l.to_numpy()
    spr_arr = df["spread"].to_numpy()
    hours = df.index.hour.to_numpy()
    
    point = 0.01 if ("GERMANY" in symbol or "SP500" in symbol) else 0.00001
    comm = 0.00007 if symbol == "EURUSD" else 0.0
    
    trades = []
    n = len(df)
    i = 200
    while i < n - 1:
        hr = hours[i]
        if "GERMANY" in symbol and not (7 <= hr <= 16):
            i += 1
            continue
        if "SP500" in symbol and not (13 <= hr <= 20):
            i += 1
            continue
        if "EURUSD" in symbol and not (7 <= hr <= 16):
            i += 1
            continue
            
        cur_atr = atr[i]
        if not math.isfinite(cur_atr) or cur_atr <= 0 or not math.isfinite(sma200[i]):
            i += 1
            continue
            
        # Señal Pullback
        buy = (c_arr[i] > sma200[i]) and (rsi2[i] < rsi_th) and (c_arr[i] <= bb_lo[i])
        sell = (c_arr[i] < sma200[i]) and (rsi2[i] > (100 - rsi_th)) and (c_arr[i] >= bb_up[i])
        
        side = 1 if buy else (-1 if sell else 0)
        if side == 0:
            i += 1
            continue
            
        k = i + 1
        entry = o_arr[k] + side * (spr_arr[k] * point / 2.0)
        stop_dist = stop_atr * cur_atr
        sl = entry - side * stop_dist
        
        be_active = False
        exit_px = None
        for j in range(k, min(n, k + max_bars)):
            hit_sl = (l_arr[j] <= sl) if side == 1 else (h_arr[j] >= sl)
            if hit_sl:
                exit_px = sl
                break
                
            # Break-even dinámico si el trade avanza +0.5 ATR
            if use_be and not be_active:
                unrealized = side * (c_arr[j] - entry)
                if unrealized >= 0.5 * cur_atr:
                    be_active = True
                    sl = entry + side * (0.05 * cur_atr)
            
            # Salida dinámica por cruce de EMA
            rule_exit = (c_arr[j] > ema_exit[j]) if side == 1 else (c_arr[j] < ema_exit[j])
            if rule_exit and j + 1 < n:
                exit_px = o_arr[j+1] - side * (spr_arr[j+1] * point / 2.0)
                j = j + 1
                break
                
        if exit_px is None:
            j = min(n - 1, k + max_bars - 1)
            exit_px = c_arr[j] - side * (spr_arr[j] * point / 2.0)
            
        net_px = side * (exit_px - entry) - comm
        r_val = net_px / stop_dist
        trades.append(r_val)
        i = j + 1
        
    if len(trades) < 15:
        return None
    m = metrics(np.array(trades))
    return {
        "symbol": symbol,
        "tf": tf_str,
        "rsi": rsi_th,
        "stop": stop_atr,
        "ema": exit_ema,
        "bars": max_bars,
        "be": use_be,
        "n": m["n"],
        "win_rate": m["win_rate"],
        "pf": m["profit_factor"],
        "mean_r": m["mean_r"],
        "max_dd_r": m["max_dd_r"],
    }


def main():
    if not mt5.initialize():
        print("Error inicializando MT5")
        return
        
    print(f"{'Activo':<10s} | {'TF':<4s} | {'RSI':<4s} | {'Stop':<7s} | {'ExitEMA':<7s} | {'BE':<5s} | {'N':<4s} | {'WinRate':<8s} | {'PF':<6s} | {'MeanR':<8s}")
    print("-" * 80)
    
    results = []
    for sym in ["GERMANY40", "[SP500]", "EURUSD"]:
        for tf_s, tf_mt5 in [("M15", mt5.TIMEFRAME_M15), ("M30", mt5.TIMEFRAME_M30)]:
            for rsi in [5, 10, 15]:
                for st in [1.5, 2.0, 2.5]:
                    for ema in [3, 5, 8]:
                        for be in [True, False]:
                            res = test_intraday_reversion(sym, tf_s, tf_mt5, rsi, st, ema, 16, use_be=be)
                            if res and res["win_rate"] >= 70.0 and res["pf"] >= 1.05:
                                results.append(res)
                                star = " ⭐⭐⭐" if res["win_rate"] >= 80.0 else (" ⭐" if res["win_rate"] >= 75.0 else "")
                                print(f"{res['symbol']:<10s} | {res['tf']:<4s} | <{res['rsi']:<3d} | {res['stop']:<4.1f}ATR | EMA{res['ema']:<3d}   | {str(res['be']):<5s} | {res['n']:<4d} | {res['win_rate']:6.1f}%  | {res['pf']:<6.2f} | {res['mean_r']:+7.4f}{star}")
                                
    mt5.shutdown()


if __name__ == "__main__":
    main()
