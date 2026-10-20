"""Investigación: Francotirador '1 Trade al Día' (Inspirado en el patrón Ismael).

Reglas de Francotirador Institucional:
1. Máximo 1 sola operación al día por activo.
2. Ventana estricta de apertura:
   - EURUSD & DAX: 07:00 a 08:30 UTC (apertura Londres/Frankfurt)
   - SP500 & US100: 13:30 a 15:00 UTC (apertura Wall Street)
3. Confluencia con tendencia H1 (EMA20 > EMA50 para compras, < para ventas).
4. El precio realiza un barrido de liquidez de la primera media hora (Initial Balance)
   y muestra una mecha de rechazo fuerte (absorción de libro de órdenes).
5. Target dinámico vs fijo.
"""
from __future__ import annotations

import math
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

from trading_v2.research.regime_lab_v3 import wilson_lb, metrics


def fetch_m5_and_h1(symbol: str, count: int = 50000):
    if not mt5.initialize():
        raise RuntimeError("MT5 no disponible")
    r_m5 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, count)
    r_h1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, count // 10)
    
    df_m5 = pd.DataFrame(r_m5)
    df_m5["time"] = pd.to_datetime(df_m5["time"], unit="s", utc=True)
    df_m5.set_index("time", inplace=True)
    df_m5.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "tick_volume": "Volume", "spread": "Spread"}, inplace=True)
    
    df_h1 = pd.DataFrame(r_h1)
    df_h1["time"] = pd.to_datetime(df_h1["time"], unit="s", utc=True)
    df_h1.set_index("time", inplace=True)
    df_h1.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close"}, inplace=True)
    
    # Calcular tendencia H1 (EMA20 vs EMA50)
    c_h1 = df_h1["Close"]
    df_h1["ema20"] = c_h1.ewm(span=20, adjust=False).mean()
    df_h1["ema50"] = c_h1.ewm(span=50, adjust=False).mean()
    df_h1["h1_trend"] = np.where(df_h1["ema20"] > df_h1["ema50"], 1, -1)
    
    # Alinear tendencia H1 cerrada con M5 (shift causal de 1 hora)
    df_h1["close_time"] = df_h1.index + pd.Timedelta(hours=1)
    m5_times = pd.DataFrame({"m5_time": df_m5.index + pd.Timedelta(minutes=5), "idx": np.arange(len(df_m5))})
    aligned = pd.merge_asof(
        m5_times.sort_values("m5_time"),
        df_h1[["close_time", "h1_trend"]].sort_values("close_time"),
        left_on="m5_time",
        right_on="close_time",
        direction="backward"
    ).sort_values("idx")
    
    df_m5["h1_trend"] = aligned["h1_trend"].fillna(0).to_numpy()
    
    # Indicadores M5
    c, h, l, o = df_m5["Close"], df_m5["High"], df_m5["Low"], df_m5["Open"]
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    df_m5["atr14"] = tr.rolling(14).mean()
    
    rng = (h - l).replace(0, np.nan)
    df_m5["lower_wick"] = ((np.minimum(o, c) - l) / rng).fillna(0.0)
    df_m5["upper_wick"] = ((h - np.maximum(o, c)) / rng).fillna(0.0)
    df_m5["clv"] = ((c - l) / rng).fillna(0.5)
    
    # Máximo y mínimo de las últimas 12 velas (1 hora previa)
    df_m5["high_1h"] = h.shift(1).rolling(12).max()
    df_m5["low_1h"] = l.shift(1).rolling(12).min()
    
    df_m5["hour_utc"] = df_m5.index.hour
    df_m5["minute_utc"] = df_m5.index.minute
    df_m5["date"] = df_m5.index.date
    
    return df_m5


def simulate_one_trade_per_day(df: pd.DataFrame, symbol: str, target_units: float, stop_units: float, session_start: int, session_end: int):
    c = df["Close"].to_numpy()
    o = df["Open"].to_numpy()
    h = df["High"].to_numpy()
    l = df["Low"].to_numpy()
    spread = df["Spread"].to_numpy()
    h1_trend = df["h1_trend"].to_numpy()
    lower_wick = df["lower_wick"].to_numpy()
    upper_wick = df["upper_wick"].to_numpy()
    high_1h = df["high_1h"].to_numpy()
    low_1h = df["low_1h"].to_numpy()
    hours = df["hour_utc"].to_numpy()
    dates = df["date"].to_numpy()
    idx = df.index
    n = len(df)
    
    if symbol == "EURUSD":
        unit = 0.00010
        point = 0.00001
        comm = 0.000065
    elif "GERMANY40" in symbol:
        unit = 1.0
        point = 0.01
        comm = 0.0
    elif "[SP500]" in symbol:
        unit = 1.0
        point = 0.01
        comm = 0.0
    elif "US100" in symbol:
        unit = 1.0
        point = 0.01
        comm = 0.0
    else:
        unit = 1.0
        point = 0.01
        comm = 0.0
        
    tgt_dist = target_units * unit
    sl_dist = stop_units * unit
    
    trades = []
    traded_dates = set()
    
    i = 30
    while i < n - 1:
        d = dates[i]
        hr = hours[i]
        
        # Solo 1 trade por día y dentro de la ventana de apertura
        if d in traded_dates or not (session_start <= hr <= session_end):
            i += 1
            continue
            
        # Filtro de spread excesivo
        if symbol == "EURUSD" and spread[i] > 12:
            i += 1
            continue
        elif "GERMANY40" in symbol and spread[i] > 200:
            i += 1
            continue
            
        trend = h1_trend[i]
        
        # BUY: tendencia alcista H1 + barrido del mínimo de la última hora + fuerte rechazo (mecha >= 35%)
        buy = (trend == 1) and (l[i] <= low_1h[i]) and (lower_wick[i] >= 0.35)
        
        # SELL: tendencia bajista H1 + barrido del máximo de la última hora + fuerte rechazo (mecha >= 35%)
        sell = (trend == -1) and (h[i] >= high_1h[i]) and (upper_wick[i] >= 0.35)
        
        side = 1 if buy else (-1 if sell else 0)
        if side == 0:
            i += 1
            continue
            
        # Marcar fecha como operada
        traded_dates.add(d)
        
        # Entrada en la siguiente barra
        k = i + 1
        entry_mid = o[k]
        entry = entry_mid + side * (spread[k] * point / 2.0)
        tp = entry + side * tgt_dist
        sl = entry - side * sl_dist
        
        exit_px = None
        reason = "TIMEOUT"
        # Mantener máx 6 barras (30 minutos)
        for j in range(k, min(n, k + 6)):
            spr_j = spread[j] * point
            eval_lo = l[j] - side * (spr_j / 2.0)
            eval_hi = h[j] - side * (spr_j / 2.0)
            
            hit_sl = (eval_lo <= sl) if side == 1 else (eval_hi >= sl)
            hit_tp = (eval_hi >= tp) if side == 1 else (eval_lo <= tp)
            
            if hit_sl and hit_tp:
                exit_px = sl
                reason = "STOP_CONSERVATIVE"
                break
            elif hit_sl:
                exit_px = sl
                reason = "STOP"
                break
            elif hit_tp:
                exit_px = tp
                reason = "TP"
                break
                
        if exit_px is None:
            j = min(n - 1, k + 5)
            exit_px = c[j] - side * (spread[j] * point / 2.0)
            
        net_price = side * (exit_px - entry) - comm
        r = net_price / sl_dist
        
        trades.append({
            "date": d,
            "entry_time": idx[k],
            "side": "LONG" if side == 1 else "SHORT",
            "pnl_units": net_price / unit,
            "r": r,
            "reason": reason
        })
        i = j + 1
        
    return pd.DataFrame(trades)


def run_experiment():
    assets = [
        ("EURUSD", 7, 10, [2.0, 2.5, 3.5], [4.0, 6.0, 8.0]),
        ("GERMANY40", 7, 10, [12.0, 15.0, 20.0], [20.0, 30.0, 40.0]),
        ("[SP500]", 13, 16, [3.0, 4.5, 6.0], [6.0, 8.0, 12.0]),
        ("US100", 13, 16, [15.0, 25.0, 35.0], [25.0, 40.0, 60.0]),
    ]
    print("=" * 95)
    print("ESTUDIO SNIPER '1 TRADE AL DÍA' CON ALINEACIÓN H1 + ABSORCIÓN DE APERTURA")
    print("=" * 95)
    print(f"{'ACTIVO':<10s} | {'TARGET':<8s} | {'STOP':<8s} | {'N DIAS':<8s} | {'WIN RATE':<9s} | {'W-LB':<7s} | {'PF':<6s} | {'R MEDIO':<8s}")
    print("-" * 95)
    
    for sym, s_start, s_end, tgts, stps in assets:
        df = fetch_m5_and_h1(sym, 50000)
        best_wr = 0.0
        best_row = None
        for tgt in tgts:
            for stp in stps:
                tdf = simulate_one_trade_per_day(df, sym, tgt, stp, s_start, s_end)
                if len(tdf) >= 15:
                    m = metrics(tdf["r"].to_numpy())
                    wr = m["win_rate"]
                    n = m["n"]
                    wlb = wilson_lb(int(round(wr * n / 100)), n) * 100
                    pf = m.get("profit_factor", 0.0)
                    r_med = m["mean_r"]
                    if wr >= 65.0 or pf >= 1.2:
                        print(f"{sym:<10s} | {tgt:<6.1f}   | {stp:<6.1f}   | {n:<8d} | {wr:<8.1f}% | {wlb:<6.1f}% | {pf:<6.2f} | {r_med:+7.4f}")
        print("-" * 95)
    print("=" * 95)


if __name__ == "__main__":
    run_experiment()
    mt5.shutdown()
