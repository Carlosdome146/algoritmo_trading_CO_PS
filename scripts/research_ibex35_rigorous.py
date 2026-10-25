"""Estudio Cuantitativo Integral del IBEX 35 ([IBEX35]) en Admirals.

Objetivo:
1. Inspeccionar especificaciones contractuales, liquidez, spread y comisiones.
2. Descargar histórico real (D1, H1, M15).
3. Evaluar estrategias de alta probabilidad (Bollinger Dip D1, RSI2 Dip D1, M15 Sniper).
4. Determinar si cumple los requisitos (Win Rate >= 75-80%, Profit Factor > 1.3, E[R] > 0)
   para ser incorporado junto a la Trinidad de Activos.
"""
from __future__ import annotations

import sys
import math
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

from trading_v2.research.regime_lab_v3 import wilson_lb, metrics

sys.stdout.reconfigure(line_buffering=True)


def inspect_contract(sym: str = "[IBEX35]"):
    print(f"=== 1. ESPECIFICACIONES CONTRACTUALES DE {sym} ===", flush=True)
    if not mt5.initialize():
        print("Error inicializando MT5", flush=True)
        return None
        
    mt5.symbol_select(sym, True)
    info = mt5.symbol_info(sym)
    if not info:
        print(f"No se encontró información para {sym}", flush=True)
        return None
        
    tick = mt5.symbol_info_tick(sym)
    spread_pts = (tick.ask - tick.bid) if tick else (info.spread * info.point)
    spread_ticks = spread_pts / info.point if info.point > 0 else 0
    
    spec_data = {
        "symbol": info.name,
        "description": info.description,
        "digits": info.digits,
        "point": info.point,
        "contract_size": info.trade_contract_size,
        "currency_base": info.currency_base,
        "currency_profit": info.currency_profit,
        "currency_margin": info.currency_margin,
        "lot_min": info.volume_min,
        "lot_step": info.volume_step,
        "lot_max": info.volume_max,
        "stops_level": getattr(info, "trade_stops_level", 0),
        "spread_points": spread_pts,
        "spread_ticks": spread_ticks,
        "tick_bid": tick.bid if tick else None,
        "tick_ask": tick.ask if tick else None,
    }
    
    print(f"Nombre: {info.name} ({info.description})")
    print(f"Moneda Base/Profit: {info.currency_base} / {info.currency_profit}")
    print(f"Precio Actual: Bid={spec_data['tick_bid']} | Ask={spec_data['tick_ask']} | Spread={spread_pts:.2f} pts ({spread_ticks:.0f} ticks)")
    print(f"Contrato: {info.trade_contract_size} EUR/punto | Lote Mínimo: {info.volume_min} | Paso: {info.volume_step}")
    print(f"Stops Level: {getattr(info, 'trade_stops_level', 0)} puntos | Digits: {info.digits}")
    return spec_data


def test_ibex_d1_strategies(sym: str = "[IBEX35]"):
    print(f"\n=== 2. AUDITORÍA CUANTITATIVA EN SWING DIARIO (D1) DE {sym} ===", flush=True)
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 3000)
    if rates is None or len(rates) < 300:
        print("Datos D1 insuficientes", flush=True)
        return
        
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    print(f"Total barras D1 descargadas: {len(df)} (Desde {df.index[0].strftime('%Y-%m-%d')} hasta {df.index[-1].strftime('%Y-%m-%d')})", flush=True)
    
    c = df["close"]
    h = df["high"]
    l = df["low"]
    o = df["open"]
    spr = df["spread"] * 0.01  # Spread en puntos
    
    # ATR20
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    df["atr20"] = tr.rolling(20, min_periods=10).mean()
    
    # RSI2
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    df["rsi2"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    
    # Medias y Bollinger
    df["sma5"] = c.rolling(5, min_periods=3).mean()
    df["sma200"] = c.rolling(200, min_periods=50).mean()
    df["sma20"] = c.rolling(20, min_periods=10).mean()
    df["std20"] = c.rolling(20, min_periods=10).std(ddof=0)
    
    # Kaufman Efficiency Ratio
    chg10 = (c - c.shift(10)).abs()
    sum_diffs = c.diff().abs().rolling(10).sum()
    df["ker10"] = chg10 / sum_diffs.replace(0, np.nan)
    
    c_arr = c.to_numpy()
    o_arr = o.to_numpy()
    h_arr = h.to_numpy()
    l_arr = l.to_numpy()
    atr_arr = df["atr20"].to_numpy()
    sma200_arr = df["sma200"].to_numpy()
    sma5_arr = df["sma5"].to_numpy()
    sma20_arr = df["sma20"].to_numpy()
    std20_arr = df["std20"].to_numpy()
    rsi2_arr = df["rsi2"].to_numpy()
    ker10_arr = df["ker10"].to_numpy()
    spr_arr = spr.to_numpy()
    n = len(df)
    
    print("\n--- Test 1: Modelo Bollinger Dip (Tipo DAX 40) en IBEX 35 ---")
    print(f"{'Sigma':<6s} | {'RSI_th':<7s} | {'StopATR':<8s} | {'N':<4s} | {'WinRate':<8s} | {'W-LB':<6s} | {'PF':<6s} | {'E[R]':<8s} | {'R_win':<8s} | {'R_loss':<8s}")
    print("-" * 85)
    
    for sigma in [1.5, 1.8, 2.0]:
        bb_lo_arr = sma20_arr - sigma * std20_arr
        for rsi_th in [8, 10, 15, 20]:
            for stop_m in [2.0, 2.5]:
                trades = []
                i = 250
                while i < n - 1:
                    cond = (c_arr[i] > sma200_arr[i]) and (rsi2_arr[i] < rsi_th) and (c_arr[i] <= bb_lo_arr[i])
                    cur_atr = atr_arr[i]
                    if not cond or not math.isfinite(cur_atr) or cur_atr <= 0:
                        i += 1
                        continue
                    k = i + 1
                    entry = o_arr[k] + spr_arr[k] * 1.5
                    stop = entry - stop_m * cur_atr
                    exit_px = None
                    for j in range(k, min(n, k + 10)):
                        if l_arr[j] <= stop:
                            exit_px = stop - spr_arr[j] * 0.5
                            break
                        if c_arr[j] > sma5_arr[j] and j + 1 < n:
                            exit_px = o_arr[j+1] - spr_arr[j+1] * 0.5
                            j = j + 1
                            break
                    if exit_px is None:
                        j = min(n - 1, k + 9)
                        exit_px = c_arr[j]
                    r_val = (exit_px - entry) / (stop_m * cur_atr)
                    trades.append(r_val)
                    i = j
                if len(trades) >= 15:
                    m = metrics(np.array(trades))
                    wlb = wilson_lb(int(round(m["win_rate"] * m["n"] / 100)), m["n"]) * 100
                    tdf = pd.Series(trades)
                    r_w = tdf[tdf > 0].mean() if len(tdf[tdf > 0]) > 0 else 0
                    r_l = tdf[tdf <= 0].mean() if len(tdf[tdf <= 0]) > 0 else 0
                    star = " [*** TOP ***]" if m["win_rate"] >= 75.0 and m["profit_factor"] >= 1.2 else (" [*]" if m["win_rate"] >= 70.0 else "")
                    print(f"{sigma:<6.1f} | <{rsi_th:<6d} | {stop_m:<8.1f} | {m['n']:<4d} | {m['win_rate']:5.1f}%  | {wlb:4.1f}% | {m['profit_factor']:5.2f} | {m['mean_r']:+7.4f} | {r_w:+7.4f} | {r_l:+7.4f}{star}")

    print("\n--- Test 2: Modelo RSI2 Dip Puro (Tipo S&P 500) en IBEX 35 ---")
    print(f"{'RSI_th':<7s} | {'StopATR':<8s} | {'N':<4s} | {'WinRate':<8s} | {'W-LB':<6s} | {'PF':<6s} | {'E[R]':<8s} | {'R_win':<8s} | {'R_loss':<8s}")
    print("-" * 80)
    for rsi_th in [5, 8, 10, 15]:
        for stop_m in [2.0, 2.5]:
            trades = []
            i = 250
            while i < n - 1:
                cond = (c_arr[i] > sma200_arr[i]) and (rsi2_arr[i] < rsi_th)
                cur_atr = atr_arr[i]
                if not cond or not math.isfinite(cur_atr) or cur_atr <= 0:
                    i += 1
                    continue
                k = i + 1
                entry = o_arr[k] + spr_arr[k] * 1.5
                stop = entry - stop_m * cur_atr
                exit_px = None
                for j in range(k, min(n, k + 10)):
                    if l_arr[j] <= stop:
                        exit_px = stop - spr_arr[j] * 0.5
                        break
                    if c_arr[j] > sma5_arr[j] and j + 1 < n:
                        exit_px = o_arr[j+1] - spr_arr[j+1] * 0.5
                        j = j + 1
                        break
                if exit_px is None:
                    j = min(n - 1, k + 9)
                    exit_px = c_arr[j]
                r_val = (exit_px - entry) / (stop_m * cur_atr)
                trades.append(r_val)
                i = j
            if len(trades) >= 15:
                m = metrics(np.array(trades))
                wlb = wilson_lb(int(round(m["win_rate"] * m["n"] / 100)), m["n"]) * 100
                tdf = pd.Series(trades)
                r_w = tdf[tdf > 0].mean() if len(tdf[tdf > 0]) > 0 else 0
                r_l = tdf[tdf <= 0].mean() if len(tdf[tdf <= 0]) > 0 else 0
                star = " [*** TOP ***]" if m["win_rate"] >= 75.0 and m["profit_factor"] >= 1.2 else (" [*]" if m["win_rate"] >= 70.0 else "")
                print(f"<{rsi_th:<6d} | {stop_m:<8.1f} | {m['n']:<4d} | {m['win_rate']:5.1f}%  | {wlb:4.1f}% | {m['profit_factor']:5.2f} | {m['mean_r']:+7.4f} | {r_w:+7.4f} | {r_l:+7.4f}{star}")


def test_ibex_m15_sniper(sym: str = "[IBEX35]"):
    print(f"\n=== 3. AUDITORÍA INTRADÍA M15 (GATILLO DE APERTURA BOLSA DE MADRID) ===", flush=True)
    rates15 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 20000)
    if rates15 is None or len(rates15) < 1000:
        print("Datos M15 insuficientes", flush=True)
        return
        
    df15 = pd.DataFrame(rates15)
    df15["time"] = pd.to_datetime(df15["time"], unit="s", utc=True)
    df15.set_index("time", inplace=True)
    print(f"Total barras M15 descargadas: {len(df15)} (Desde {df15.index[0].strftime('%Y-%m-%d')} hasta {df15.index[-1].strftime('%Y-%m-%d')})", flush=True)
    
    # H1 trend
    rates_h1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 5000)
    df_h1 = pd.DataFrame(rates_h1)
    df_h1["time"] = pd.to_datetime(df_h1["time"], unit="s", utc=True)
    df_h1.set_index("time", inplace=True)
    df_h1["ema20"] = df_h1["close"].ewm(span=20, adjust=False).mean()
    df_h1["ema50"] = df_h1["close"].ewm(span=50, adjust=False).mean()
    df_h1["sma200"] = df_h1["close"].rolling(200, min_periods=50).mean()
    df_h1["h1_trend"] = np.where(
        (df_h1["close"] > df_h1["sma200"]) & (df_h1["ema20"] > df_h1["ema50"]), 1,
        np.where((df_h1["close"] < df_h1["sma200"]) & (df_h1["ema20"] < df_h1["ema50"]), -1, 0)
    )
    df_h1["close_time"] = df_h1.index + pd.Timedelta(hours=1)
    
    m15_times = pd.DataFrame({"m15_time": df15.index + pd.Timedelta(minutes=15), "idx": np.arange(len(df15))})
    aligned = pd.merge_asof(
        m15_times.sort_values("m15_time"),
        df_h1[["close_time", "h1_trend"]].sort_values("close_time"),
        left_on="m15_time",
        right_on="close_time",
        direction="backward"
    ).sort_values("idx")
    df15["h1_trend"] = aligned["h1_trend"].fillna(0).to_numpy()
    
    c, h, l, o = df15["close"], df15["high"], df15["low"], df15["open"]
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=5).mean().to_numpy()
    
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    rsi2 = (100 - 100 / (1 + up / dn.replace(0, np.nan))).to_numpy()
    
    sma20 = c.rolling(20, min_periods=10).mean()
    std20 = c.rolling(20, min_periods=10).std(ddof=0)
    bb_lo = (sma20 - 2.0 * std20).to_numpy()
    bb_up = (sma20 + 2.0 * std20).to_numpy()
    
    rng = (h - l).replace(0, np.nan)
    lower_wick = ((np.minimum(o, c) - l) / rng).fillna(0.0).to_numpy()
    upper_wick = ((h - np.maximum(o, c)) / rng).fillna(0.0).to_numpy()
    
    hours = df15.index.hour.to_numpy()
    point = 0.01
    spr_arr = df15["spread"].to_numpy() * point
    c_arr, o_arr, h_arr, l_arr = c.to_numpy(), o.to_numpy(), h.to_numpy(), l.to_numpy()
    h1_tr = df15["h1_trend"].to_numpy()
    n = len(df15)
    
    # Sesión Madrid: 07:00 a 16:30 UTC (09:00 a 18:30 CEST)
    print(f"{'RSI_cut':<8s} | {'TP':<6s} | {'SL':<6s} | {'BE':<6s} | {'N':<5s} | {'WinRate':<8s} | {'PF':<6s} | {'MeanR':<8s}")
    print("-" * 70)
    for rsi_cut in [5, 10]:
        for tp_atr in [0.4, 0.5, 0.7]:
            for sl_atr in [1.0, 1.2, 1.5]:
                for be_trigger in [0.30, 0.40, None]:
                    trades = []
                    i = 50
                    while i < n - 1:
                        if not (7 <= hours[i] <= 15):
                            i += 1
                            continue
                        cur_atr = atr[i]
                        if not math.isfinite(cur_atr) or cur_atr <= 0:
                            i += 1
                            continue
                            
                        buy = (h1_tr[i] == 1) and (rsi2[i] < rsi_cut) and (c_arr[i] <= bb_lo[i] or lower_wick[i] >= 0.35)
                        sell = (h1_tr[i] == -1) and (rsi2[i] > (100 - rsi_cut)) and (c_arr[i] >= bb_up[i] or upper_wick[i] >= 0.35)
                        side = 1 if buy else (-1 if sell else 0)
                        if side == 0:
                            i += 1
                            continue
                            
                        k = i + 1
                        entry = o_arr[k] + side * (spr_arr[k] / 2.0)
                        tp = entry + side * (tp_atr * cur_atr)
                        sl = entry - side * (sl_atr * cur_atr)
                        be_active = False
                        exit_px = None
                        
                        for j in range(k, min(n, k + 12)):
                            hit_sl = (l_arr[j] <= sl) if side == 1 else (h_arr[j] >= sl)
                            hit_tp = (h_arr[j] >= tp) if side == 1 else (l_arr[j] <= tp)
                            if hit_sl and hit_tp:
                                exit_px = sl
                                break
                            elif hit_sl:
                                exit_px = sl
                                break
                            elif hit_tp:
                                exit_px = tp
                                break
                                
                            if be_trigger and not be_active:
                                unrl = side * (c_arr[j] - entry)
                                if unrl >= be_trigger * cur_atr:
                                    be_active = True
                                    sl = entry + side * (0.05 * cur_atr)
                                    
                        if exit_px is None:
                            j = min(n - 1, k + 11)
                            exit_px = c_arr[j] - side * (spr_arr[j] / 2.0)
                            
                        net = side * (exit_px - entry)
                        r_val = net / (sl_atr * cur_atr)
                        trades.append(r_val)
                        i = j + 1
                        
                    if len(trades) >= 20:
                        m = metrics(np.array(trades))
                        be_str = f"{be_trigger:.2f}" if be_trigger else "None"
                        if m["win_rate"] >= 68.0:
                            star = " [*** TOP ***]" if m["win_rate"] >= 75.0 and m["profit_factor"] >= 1.15 else (" [*]" if m["win_rate"] >= 70.0 else "")
                            print(f"RSI<{rsi_cut:<4d} | {tp_atr:<6.2f} | {sl_atr:<6.2f} | {be_str:<6s} | {m['n']:<5d} | {m['win_rate']:5.1f}%  | {m['profit_factor']:5.2f} | {m['mean_r']:+7.4f}{star}")


def main():
    sym = "[IBEX35]"
    spec = inspect_contract(sym)
    if spec:
        test_ibex_d1_strategies(sym)
        test_ibex_m15_sniper(sym)
    mt5.shutdown()


if __name__ == "__main__":
    main()
