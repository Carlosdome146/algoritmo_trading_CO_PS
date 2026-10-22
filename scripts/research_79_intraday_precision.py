"""Laboratorio Cuantitativo de Alta Precisión Intradía (Meta >= 75-80% Win Rate)."""
from __future__ import annotations

import math
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

from trading_v2.research.regime_lab_v3 import wilson_lb, metrics


def fetch_symbol_data(symbol: str, count: int = 25000) -> pd.DataFrame:
    r_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, count)
    df15 = pd.DataFrame(r_m15)
    df15["time"] = pd.to_datetime(df15["time"], unit="s", utc=True)
    df15.set_index("time", inplace=True)
    df15.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "spread": "Spread"}, inplace=True)
    
    c = df15["Close"]
    h = df15["High"]
    l = df15["Low"]
    o = df15["Open"]
    
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    df15["atr14"] = tr.rolling(14, min_periods=5).mean()
    
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    df15["rsi2"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    
    df15["ema20"] = c.ewm(span=20, adjust=False).mean()
    df15["ema50"] = c.ewm(span=50, adjust=False).mean()
    df15["sma200"] = c.rolling(200, min_periods=40).mean()
    
    sma20 = c.rolling(20, min_periods=10).mean()
    std20 = c.rolling(20, min_periods=10).std(ddof=0)
    df15["bb_lo"] = sma20 - 2.0 * std20
    df15["bb_up"] = sma20 + 2.0 * std20
    
    rng = (h - l).replace(0, np.nan)
    df15["lower_wick"] = ((np.minimum(o, c) - l) / rng).fillna(0.0)
    df15["upper_wick"] = ((h - np.maximum(o, c)) / rng).fillna(0.0)
    df15["clv"] = ((c - l) / rng).fillna(0.5)
    
    df15["hour_utc"] = df15.index.hour
    return df15


def scan_asset(symbol: str):
    df = fetch_symbol_data(symbol, 25000)
    c = df["Close"].to_numpy(dtype=float)
    o = df["Open"].to_numpy(dtype=float)
    h = df["High"].to_numpy(dtype=float)
    l = df["Low"].to_numpy(dtype=float)
    spread = df["Spread"].to_numpy(dtype=float)
    atr = df["atr14"].to_numpy(dtype=float)
    rsi2 = df["rsi2"].to_numpy()
    bb_lo = df["bb_lo"].to_numpy()
    bb_up = df["bb_up"].to_numpy()
    lower_wick = df["lower_wick"].to_numpy()
    upper_wick = df["upper_wick"].to_numpy()
    sma200 = df["sma200"].to_numpy()
    ema20 = df["ema20"].to_numpy()
    ema50 = df["ema50"].to_numpy()
    hours = df["hour_utc"].to_numpy()
    n = len(df)
    
    if symbol == "EURUSD":
        unit = 0.00010
        point = 0.00001
        comm = 0.000065
        s_start, s_end = 7, 16
        eur_val = 17.8
        lot = 0.50
    elif "GERMANY40" in symbol or "DAX" in symbol:
        unit = 1.0
        point = 0.01
        comm = 0.0
        s_start, s_end = 7, 15
        eur_val = 1.0
        lot = 0.10
    else:  # [SP500]
        unit = 1.0
        point = 0.01
        comm = 0.0
        s_start, s_end = 13, 19
        eur_val = 0.89
        lot = 0.20
        
    print(f"\n==================== ACTIVO: {symbol} (M15 GRID SEARCH TASA >= 75%) ====================")
    print(f"{'MODO':<12s} | {'TP':<6s} | {'SL':<6s} | {'BE':<6s} | {'N':<5s} | {'WIN RATE':<9s} | {'PF':<6s} | {'R MEDIO':<8s} | {'PnL (EUR)':<12s}")
    print("-" * 85)
    
    # Probar diferentes combinaciones
    for rsi_cut in [10.0, 15.0]:
        for tp_m in [0.40, 0.50, 0.60]:
            for sl_m in [1.00, 1.20, 1.50]:
                for be_m in [0.25, 0.35, None]:
                    trades = []
                    i = 50
                    while i < n - 1:
                        hr = hours[i]
                        if not (s_start <= hr <= s_end):
                            i += 1
                            continue
                        cur_atr = atr[i]
                        if not math.isfinite(cur_atr) or cur_atr <= 0 or not math.isfinite(sma200[i]):
                            i += 1
                            continue
                            
                        # Pullback a favor de tendencia macro (c > sma200)
                        buy = (c[i] > sma200[i]) and (rsi2[i] < rsi_cut) and (c[i] <= bb_lo[i] or lower_wick[i] >= 0.30)
                        sell = (c[i] < sma200[i]) and (rsi2[i] > (100 - rsi_cut)) and (c[i] >= bb_up[i] or upper_wick[i] >= 0.30)
                        
                        side = 1 if buy else (-1 if sell else 0)
                        if side == 0:
                            i += 1
                            continue
                            
                        k = i + 1
                        spr_k = spread[k] * point
                        entry = o[k] + side * (spr_k / 2.0)
                        tp = entry + side * (tp_m * cur_atr)
                        sl = entry - side * (sl_m * cur_atr)
                        
                        be_active = False
                        exit_px = None
                        
                        for j in range(k, min(n, k + 8)):
                            spr_j = spread[j] * point
                            eval_lo = l[j] - side * (spr_j / 2.0)
                            eval_hi = h[j] - side * (spr_j / 2.0)
                            
                            hit_sl = (eval_lo <= sl) if side == 1 else (eval_hi >= sl)
                            hit_tp = (eval_hi >= tp) if side == 1 else (eval_lo <= tp)
                            
                            if hit_sl and hit_tp:
                                exit_px = sl
                                break
                            elif hit_sl:
                                exit_px = sl
                                break
                            elif hit_tp:
                                exit_px = tp
                                break
                                
                            if be_m is not None:
                                unrealized = side * (c[j] - entry)
                                if not be_active and unrealized >= (be_m * cur_atr):
                                    be_active = True
                                    sl = entry + side * (0.05 * cur_atr)
                                    
                        if exit_px is None:
                            j = min(n - 1, k + 7)
                            exit_px = c[j] - side * (spread[j] * point / 2.0)
                            
                        net_px = side * (exit_px - entry) - comm
                        r = net_px / (sl_m * cur_atr)
                        pnl_eur = (net_px / unit) * eur_val * lot
                        trades.append({"r": r, "pnl_eur": pnl_eur, "won": net_px > 0})
                        i = j + 1
                        
                    if len(trades) >= 20:
                        tdf = pd.DataFrame(trades)
                        r_arr = tdf["r"].to_numpy()
                        m = metrics(r_arr)
                        wr = m["win_rate"]
                        n_tr = m["n"]
                        pf = m.get("profit_factor", 0.0)
                        rm = m["mean_r"]
                        pnl_tot = tdf["pnl_eur"].sum()
                        sign = "+" if pnl_tot > 0 else ""
                        be_str = f"{be_m:.2f}" if be_m else "None"
                        if wr >= 72.0:
                            star = "⭐" if wr >= 75.0 and pf >= 1.2 else ("✨" if wr >= 75.0 else "")
                            print(f"RSI<{rsi_cut:<4.0f} | {tp_m:<6.2f} | {sl_m:<6.2f} | {be_str:<6s} | {n_tr:<5d} | {wr:<8.1f}% | {pf:<6.2f} | {rm:+7.4f} | {sign}{pnl_tot:8.2f} € {star}")


def main():
    if not mt5.initialize():
        print("MT5 no conectado")
        return
    for sym in ["GERMANY40", "[SP500]", "EURUSD"]:
        scan_asset(sym)
    mt5.shutdown()


if __name__ == "__main__":
    main()
