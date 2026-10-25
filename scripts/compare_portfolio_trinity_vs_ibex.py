"""Comparativa de Cartera: Trinidad de 3 Activos vs Cartera de 4 Activos (+ IBEX 35)."""
from __future__ import annotations

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from trading_v2.research.regime_lab_v3 import metrics, wilson_lb


def get_trades_d1(sym: str, sigma: float, rsi_th: int, stop_m: float, is_ker: bool = False) -> pd.DataFrame:
    r = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 3000)
    if r is None or len(r) == 0:
        return pd.DataFrame()
    df = pd.DataFrame(r)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    c, h, l, o = df["close"].values, df["high"].values, df["low"].values, df["open"].values
    n = len(df)
    
    tr = pd.concat([df["high"] - df["low"], (df["high"] - df["close"].shift(1)).abs(), (df["low"] - df["close"].shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(20, min_periods=10).mean().values
    
    delta = df["close"].diff()
    up = delta.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    rsi2 = (100 - 100 / (1 + up / dn.replace(0, np.nan))).values
    
    sma200 = df["close"].rolling(200, min_periods=50).mean().values
    sma20 = df["close"].rolling(20, min_periods=10).mean().values
    std20 = df["close"].rolling(20, min_periods=10).std(ddof=0).values
    sma5 = df["close"].rolling(5, min_periods=3).mean().values
    bb_lo = sma20 - sigma * std20
    bb_up = sma20 + sigma * std20
    
    pt = 0.00001 if sym == "EURUSD" else 0.01
    spr = df["spread"].values * pt
    
    ker10 = (df["close"] - df["close"].shift(10)).abs() / df["close"].diff().abs().rolling(10).sum().replace(0, np.nan)
    ker10_arr = ker10.values
    
    trades = []
    i = 250
    while i < n - 1:
        if is_ker:
            is_rng = ker10_arr[i] < 0.40
            long_sig = is_rng and (rsi2[i] < rsi_th) and (c[i] <= bb_lo[i])
            short_sig = is_rng and (rsi2[i] > (100 - rsi_th)) and (c[i] >= bb_up[i])
            side = 1 if long_sig else (-1 if short_sig else 0)
        else:
            if sigma > 0:
                cond = (c[i] > sma200[i]) and (rsi2[i] < rsi_th) and (c[i] <= bb_lo[i])
            else:
                cond = (c[i] > sma200[i]) and (rsi2[i] < rsi_th)
            side = 1 if cond else 0
            
        cur_atr = atr[i]
        if side == 0 or not np.isfinite(cur_atr) or cur_atr <= 0:
            i += 1
            continue
            
        k = i + 1
        entry = o[k] + side * spr[k] * 1.5
        stop = entry - side * stop_m * cur_atr
        exit_px = None
        for j in range(k, min(n, k + 10)):
            if (side == 1 and l[j] <= stop) or (side == -1 and h[j] >= stop):
                exit_px = stop - side * spr[j] * 0.5
                break
            if side == 1 and c[j] > sma5[j] and j + 1 < n:
                exit_px = o[j+1] - side * spr[j+1] * 0.5
                j = j + 1
                break
            elif side == -1 and c[j] < sma5[j] and j + 1 < n:
                exit_px = o[j+1] + side * spr[j+1] * 0.5
                j = j + 1
                break
        if exit_px is None:
            j = min(n - 1, k + 9)
            exit_px = c[j]
        r = side * (exit_px - entry) / (stop_m * cur_atr)
        trades.append({"date": df.index[k], "sym": sym, "r": r})
        i = j
    return pd.DataFrame(trades)


def main():
    if not mt5.initialize():
        print("MT5 no disponible")
        return
        
    tr_dax = get_trades_d1("GERMANY40", 1.8, 15, 2.5)
    tr_sp = get_trades_d1("[SP500]", 0.0, 8, 2.5)
    tr_eu = get_trades_d1("EURUSD", 2.0, 8, 2.0, is_ker=True)
    tr_ibx = get_trades_d1("[IBEX35]", 1.8, 10, 2.5)
    tr_ibx_strict = get_trades_d1("[IBEX35]", 2.0, 10, 2.5)

    print("=========================================================================================")
    print("AUDITORÍA DE ACTIVOS INDIVIDUALES EN ESTRATEGIAS D1 DE ALTA TASA (>= 75%)")
    print("=========================================================================================")
    for name, tdf in [("GERMANY40", tr_dax), ("[SP500]", tr_sp), ("EURUSD", tr_eu), ("[IBEX35] (1.8s)", tr_ibx), ("[IBEX35] (2.0s)", tr_ibx_strict)]:
        m = metrics(tdf["r"].to_numpy())
        wlb = wilson_lb(int(round(m["win_rate"] * m["n"] / 100)), m["n"])
        wlb_pct = wlb if wlb <= 1.0 else (wlb / 100.0)
        print(f"{name:<18s}: N={m['n']:<3d} | WinRate={m['win_rate']:5.1f}% | W-LB={wlb_pct*100:4.1f}% | PF={m['profit_factor']:5.2f} | E[R]={m['mean_r']:+7.4f} | R Total={tdf['r'].sum():+6.2f} R")

    # Comparativa de carteras
    p3 = pd.concat([tr_dax, tr_sp, tr_eu]).sort_values("date")
    m3 = metrics(p3["r"].to_numpy())
    wlb3 = wilson_lb(int(round(m3["win_rate"] * m3["n"] / 100)), m3["n"])
    wlb3_pct = (wlb3 if wlb3 <= 1.0 else wlb3 / 100.0) * 100

    p4 = pd.concat([tr_dax, tr_sp, tr_eu, tr_ibx]).sort_values("date")
    m4 = metrics(p4["r"].to_numpy())
    wlb4 = wilson_lb(int(round(m4["win_rate"] * m4["n"] / 100)), m4["n"])
    wlb4_pct = (wlb4 if wlb4 <= 1.0 else wlb4 / 100.0) * 100

    p4_strict = pd.concat([tr_dax, tr_sp, tr_eu, tr_ibx_strict]).sort_values("date")
    m4_s = metrics(p4_strict["r"].to_numpy())
    wlb4_s = wilson_lb(int(round(m4_s["win_rate"] * m4_s["n"] / 100)), m4_s["n"])
    wlb4_s_pct = (wlb4_s if wlb4_s <= 1.0 else wlb4_s / 100.0) * 100

    print("\n=========================================================================================")
    print("BENCHMARK DE CARTERA: TRINIDAD (3 ACTIVOS) VS CARTERA AMPLIADA (4 ACTIVOS)")
    print("=========================================================================================")
    print(f"1. TRINIDAD ACTUAL (DAX40 + SP500 + EURUSD):")
    print(f"   * Total Operaciones: {m3['n']}")
    print(f"   * Win Rate:          {m3['win_rate']:.1f}% (Wilson LB 95%: {wlb3_pct:.1f}%)")
    print(f"   * Profit Factor:     {m3['profit_factor']:.2f}")
    print(f"   * Retorno Medio E[R]: {m3['mean_r']:+.4f} R por trade")
    print(f"   * Retorno Total:     {p3['r'].sum():+.2f} R")
    print(f"   * Max Drawdown:      {m3['max_dd_r']:.2f} R")

    print(f"\n2. CARTERA AMPLIADA (+ [IBEX35] 1.8 sigma):")
    print(f"   * Total Operaciones: {m4['n']} (+{m4['n'] - m3['n']} operaciones adicionales, +{((m4['n'] - m3['n'])/m3['n'])*100:.1f}% de actividad)")
    print(f"   * Win Rate:          {m4['win_rate']:.1f}% (Wilson LB 95%: {wlb4_pct:.1f}%)")
    print(f"   * Profit Factor:     {m4['profit_factor']:.2f}")
    print(f"   * Retorno Medio E[R]: {m4['mean_r']:+.4f} R por trade")
    print(f"   * Retorno Total:     {p4['r'].sum():+.2f} R (+{p4['r'].sum() - p3['r'].sum():+.2f} R)")
    print(f"   * Max Drawdown:      {m4['max_dd_r']:.2f} R")

    print(f"\n3. CARTERA AMPLIADA (+ [IBEX35] 2.0 sigma Alta Convicción):")
    print(f"   * Total Operaciones: {m4_s['n']} (+{m4_s['n'] - m3['n']} operaciones)")
    print(f"   * Win Rate:          {m4_s['win_rate']:.1f}% (Wilson LB 95%: {wlb4_s_pct:.1f}%)")
    print(f"   * Profit Factor:     {m4_s['profit_factor']:.2f}")
    print(f"   * Retorno Medio E[R]: {m4_s['mean_r']:+.4f} R por trade")
    print(f"   * Retorno Total:     {p4_strict['r'].sum():+.2f} R (+{p4_strict['r'].sum() - p3['r'].sum():+.2f} R)")
    print(f"   * Max Drawdown:      {m4_s['max_dd_r']:.2f} R")
    print("=========================================================================================")

    mt5.shutdown()


if __name__ == "__main__":
    main()
