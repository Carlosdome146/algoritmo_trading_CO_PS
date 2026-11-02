"""Simulación de Cartera Completa (7 Activos) con Micro-Sweep Reclaim en Octubre 2026.
Evalúa capital compuesto, curva de equity, drawdown máximo y concurrencia.
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

PORTFOLIO_CONFIGS = {
    "EURUSD": {
        "tf": mt5.TIMEFRAME_M15, "tf_name": "M15", "spread": 0.00008, "pip": 0.00010,
        "tgt": 0.00035, "sl": 0.00055, "be_r": 0.57, "be_l": 0.00005,
        "s_start": 6, "s_end": 20, "allow_short": True, "ccy": "EUR"
    },
    "GERMANY40": {
        "tf": mt5.TIMEFRAME_M30, "tf_name": "M30", "spread": 1.2, "pip": 1.0,
        "tgt": 22.0, "sl": 35.0, "be_r": 0.35, "be_l": 1.5,
        "s_start": 7, "s_end": 17, "allow_short": True, "ccy": "EUR"
    },
    "US100": {
        "tf": mt5.TIMEFRAME_M30, "tf_name": "M30", "spread": 1.8, "pip": 1.0,
        "tgt": 25.0, "sl": 70.0, "be_r": 0.35, "be_l": 2.5,
        "s_start": 12, "s_end": 21, "allow_short": True, "ccy": "USD"
    },
    "[IBEX35]": {
        "tf": mt5.TIMEFRAME_M15, "tf_name": "M15", "spread": 5.0, "pip": 1.0,
        "tgt": 20.0, "sl": 45.0, "be_r": 0.45, "be_l": 6.0,
        "s_start": 7, "s_end": 17, "allow_short": False, "ccy": "EUR"
    },
    "GOLD": {
        "tf": mt5.TIMEFRAME_M30, "tf_name": "M30", "spread": 0.30, "pip": 1.0,
        "tgt": 4.0, "sl": 15.0, "be_r": 0.35, "be_l": 0.40,
        "s_start": 6, "s_end": 21, "allow_short": False, "ccy": "USD"
    },
    "[SP500]": {
        "tf": mt5.TIMEFRAME_M30, "tf_name": "M30", "spread": 0.50, "pip": 1.0,
        "tgt": 4.0, "sl": 12.0, "be_r": 0.40, "be_l": 0.60,
        "s_start": 12, "s_end": 21, "allow_short": False, "ccy": "USD"
    },
    "[DJI30]": {
        "tf": mt5.TIMEFRAME_M30, "tf_name": "M30", "spread": 3.0, "pip": 1.0,
        "tgt": 40.0, "sl": 80.0, "be_r": 0.35, "be_l": 4.0,
        "s_start": 12, "s_end": 21, "allow_short": False, "ccy": "USD"
    },
}

def generate_signals_for_asset(symbol, cfg):
    rates = mt5.copy_rates_from_pos(symbol, cfg["tf"], 0, 5000)
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
    
    rec_hi16 = pd.Series(h).shift(1).rolling(16, min_periods=4).max().values
    rec_lo16 = pd.Series(l).shift(1).rolling(16, min_periods=4).min().values
    
    sigs = np.zeros(n, dtype=int)
    for i in range(25, n):
        if dows[i] >= 5: continue
        if not (cfg["s_start"] <= hrs[i] <= cfg["s_end"]): continue
        
        # BUY
        if (l[i] <= rec_lo16[i]) and (c[i] > rec_lo16[i]) and (c[i] > o[i]) and (lower_wick[i] >= 0.35) and (clv[i] >= 0.65):
            sigs[i] = 1
        # SELL
        elif cfg["allow_short"] and (h[i] >= rec_hi16[i]) and (c[i] < rec_hi16[i]) and (c[i] < o[i]) and (upper_wick[i] >= 0.35) and (clv[i] <= 0.35):
            sigs[i] = -1
            
    df_oct["signal"] = sigs
    return df_oct

def main():
    if not mt5.initialize():
        return
        
    print("Extrayendo senales de los 7 activos en Octubre 2026...")
    dfs = {}
    for sym, cfg in PORTFOLIO_CONFIGS.items():
        dfs[sym] = generate_signals_for_asset(sym, cfg)
        
    # Recorrer cronológicamente todas las operaciones
    all_trades = []
    for sym, cfg in PORTFOLIO_CONFIGS.items():
        df = dfs[sym]
        c = df["close"].values
        h = df["high"].values
        l = df["low"].values
        o = df["open"].values
        sigs = df["signal"].values
        n = len(df)
        
        spread = cfg["spread"]
        tgt = cfg["tgt"]
        sl = cfg["sl"]
        be_trig = tgt * cfg["be_r"]
        be_lock = cfg["be_l"]
        
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
                entry_px = o[k] + spread * 0.5
                tp_px = entry_px + tgt
                sl_px = entry_px - sl
                cur_sl = sl_px
                be_trig_px = entry_px + be_trig
                be_lock_px = entry_px + be_lock
                exit_px = None
                exit_t = None
                reason = None
                for j in range(k, min(n, k + 8)):
                    if l[j] <= cur_sl and h[j] >= tp_px:
                        exit_px = cur_sl if c[j] < o[j] else tp_px
                        exit_t = df.index[j]
                        reason = "SL" if c[j] < o[j] else "TP"
                        break
                    elif l[j] <= cur_sl:
                        exit_px = cur_sl
                        exit_t = df.index[j]
                        reason = "SL"
                        break
                    elif h[j] >= tp_px:
                        exit_px = tp_px
                        exit_t = df.index[j]
                        reason = "TP"
                        break
                    if h[j] >= be_trig_px and cur_sl < be_lock_px:
                        cur_sl = be_lock_px
                if exit_px is None:
                    j = min(n - 1, k + 7)
                    exit_px = c[j] - spread * 0.5
                    exit_t = df.index[j]
                    reason = "TIME"
                pnl = exit_px - entry_px - spread * 0.5
                r_mult = pnl / sl
                all_trades.append({
                    "symbol": sym, "entry_t": entry_t, "exit_t": exit_t,
                    "dir": "BUY", "pnl": pnl, "r": r_mult, "win": 1 if pnl > 0 else 0, "reason": reason
                })
                i = j + 1
            elif s == -1:
                entry_px = o[k] - spread * 0.5
                tp_px = entry_px - tgt
                sl_px = entry_px + sl
                cur_sl = sl_px
                be_trig_px = entry_px - be_trig
                be_lock_px = entry_px - be_lock
                exit_px = None
                exit_t = None
                reason = None
                for j in range(k, min(n, k + 8)):
                    if h[j] >= cur_sl and l[j] <= tp_px:
                        exit_px = cur_sl if c[j] > o[j] else tp_px
                        exit_t = df.index[j]
                        reason = "SL" if c[j] > o[j] else "TP"
                        break
                    elif h[j] >= cur_sl:
                        exit_px = cur_sl
                        exit_t = df.index[j]
                        reason = "SL"
                        break
                    elif l[j] <= tp_px:
                        exit_px = tp_px
                        exit_t = df.index[j]
                        reason = "TP"
                        break
                    if l[j] <= be_trig_px and cur_sl > be_lock_px:
                        cur_sl = be_lock_px
                if exit_px is None:
                    j = min(n - 1, k + 7)
                    exit_px = c[j] + spread * 0.5
                    exit_t = df.index[j]
                    reason = "TIME"
                pnl = entry_px - exit_px - spread * 0.5
                r_mult = pnl / sl
                all_trades.append({
                    "symbol": sym, "entry_t": entry_t, "exit_t": exit_t,
                    "dir": "SELL", "pnl": pnl, "r": r_mult, "win": 1 if pnl > 0 else 0, "reason": reason
                })
                i = j + 1
                
    tdf = pd.DataFrame(all_trades).sort_values(by="entry_t").reset_index(drop=True)
    
    # Simulación de Cuenta de 3,000 EUR con Riesgo del 1.5%
    initial_balance = 3000.0
    balance = initial_balance
    risk_fraction = 0.0150
    equity_curve = [balance]
    
    print("\n" + "="*80)
    print("SIMULACION EXACTA DE CARTERA COMPLETA 7 ACTIVOS (OCTUBRE 2026)")
    print("="*80)
    
    for idx, row in tdf.iterrows():
        risk_budget = balance * risk_fraction
        pnl_eur = row["r"] * risk_budget
        balance += pnl_eur
        equity_curve.append(balance)
        tdf.loc[idx, "balance"] = balance
        tdf.loc[idx, "pnl_eur"] = pnl_eur
        
    m = metrics(tdf["r"].to_numpy())
    peak = np.maximum.accumulate(equity_curve)
    drawdowns = (peak - equity_curve) / peak
    max_dd = np.max(drawdowns) * 100.0
    
    print(f"Capital Inicial:      {initial_balance:.2f} EUR")
    print(f"Capital Final:        {balance:.2f} EUR")
    print(f"Beneficio Neto:       +{balance - initial_balance:.2f} EUR (+{(balance/initial_balance - 1)*100:.2f}%)")
    print(f"Operaciones Totales:  {len(tdf)} trades")
    print(f"Operaciones Ganadas:  {(tdf['win'] == 1).sum()} ({(tdf['win'] == 1).mean()*100:.2f}%)")
    print(f"Operaciones Perdidas: {(tdf['win'] == 0).sum()} ({(tdf['win'] == 0).mean()*100:.2f}%)")
    print(f"Profit Factor Global: {m['profit_factor']:.2f}")
    print(f"Retorno Total en R:   +{tdf['r'].sum():.2f} R")
    print(f"Drawdown Maximo:      {max_dd:.2f}%")
    
    # Desglose por activo
    print("\nDESGLOSE POR ACTIVO:")
    print(f"{'Activo':11s} | {'Trades':6s} | {'WinRate':7s} | {'Profit Factor':13s} | {'Ganancia EUR':12s} | {'Retorno R':9s}")
    print("-" * 75)
    for sym, grp in tdf.groupby("symbol"):
        mg = metrics(grp["r"].to_numpy())
        pf_g = f"{mg['profit_factor']:.2f}" if mg['profit_factor'] is not None else "INF"
        pnl_sum = grp["pnl_eur"].sum()
        r_sum = grp["r"].sum()
        print(f"{sym:11s} | {len(grp):6d} | {mg['win_rate']:6.1f}% | {pf_g:13s} | {pnl_sum:+10.2f} EUR | {r_sum:+8.2f}R")

    mt5.shutdown()

if __name__ == "__main__":
    main()
