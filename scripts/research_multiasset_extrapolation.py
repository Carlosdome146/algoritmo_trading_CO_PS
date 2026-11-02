"""Auditoría y extrapolación cuantitativa del modelo Micro-Sweep Reclaim a todos los activos.

Activos analizados:
- GERMANY40 (DAX 40)
- [IBEX35] (IBEX 35)
- [SP500] (S&P 500)
- US100 (Nasdaq 100)
- [DJI30] (Dow Jones 30)
- GOLD (Oro Spot)

Evalúa:
1. Impacto de eliminar el límite artificial de trades al día (max_trades_per_day = None).
2. Impacto de ampliar las sesiones continuas europeas y americanas.
3. Posibilidad de operar en ambas direcciones (LONG + SHORT) con el filtro estricto de Reclaim.
4. Ajuste asimétrico de Take Profit, Stop Loss y Breakeven Causal.
5. Win Rate, Profit Factor, número de operaciones y PnL neto proyectado al 1.5% de riesgo.
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

ASSET_SPECS = {
    "GERMANY40": {
        "point": 0.01,
        "spread_std": 1.2, # puntos
        "s_start": 7,
        "s_end": 17,
        "tgt_candidates": [10.0, 12.0, 15.0, 18.0],
        "sl_candidates": [20.0, 25.0, 30.0],
        "be_ratio": 0.40,
        "be_lock": 1.5,
        "sweep_lookback": [12, 16, 20],
        "timeframes": [(mt5.TIMEFRAME_M15, "M15"), (mt5.TIMEFRAME_M30, "M30")],
    },
    "[IBEX35]": {
        "point": 0.01,
        "spread_std": 5.0, # puntos
        "s_start": 7,
        "s_end": 17,
        "tgt_candidates": [12.0, 15.0, 20.0],
        "sl_candidates": [20.0, 25.0, 35.0],
        "be_ratio": 0.40,
        "be_lock": 6.0,
        "sweep_lookback": [12, 16, 20],
        "timeframes": [(mt5.TIMEFRAME_M15, "M15"), (mt5.TIMEFRAME_M30, "M30")],
    },
    "[SP500]": {
        "point": 0.01,
        "spread_std": 0.50, # puntos
        "s_start": 12,
        "s_end": 21,
        "tgt_candidates": [3.5, 4.0, 5.0, 6.0],
        "sl_candidates": [6.0, 7.5, 9.0],
        "be_ratio": 0.45,
        "be_lock": 0.6,
        "sweep_lookback": [12, 16, 20],
        "timeframes": [(mt5.TIMEFRAME_M15, "M15"), (mt5.TIMEFRAME_M30, "M30")],
    },
    "US100": {
        "point": 0.01,
        "spread_std": 1.8, # puntos
        "s_start": 12,
        "s_end": 21,
        "tgt_candidates": [20.0, 25.0, 30.0, 35.0],
        "sl_candidates": [40.0, 50.0, 60.0],
        "be_ratio": 0.40,
        "be_lock": 2.5,
        "sweep_lookback": [12, 16, 20],
        "timeframes": [(mt5.TIMEFRAME_M15, "M15"), (mt5.TIMEFRAME_M30, "M30")],
    },
    "[DJI30]": {
        "point": 0.01,
        "spread_std": 3.0, # puntos
        "s_start": 12,
        "s_end": 21,
        "tgt_candidates": [45.0, 55.0, 65.0],
        "sl_candidates": [90.0, 110.0, 130.0],
        "be_ratio": 0.40,
        "be_lock": 4.0,
        "sweep_lookback": [12, 16, 20],
        "timeframes": [(mt5.TIMEFRAME_M15, "M15"), (mt5.TIMEFRAME_M30, "M30")],
    },
    "GOLD": {
        "point": 0.01,
        "spread_std": 0.30, # USD
        "s_start": 6,
        "s_end": 21,
        "tgt_candidates": [3.5, 4.0, 5.0, 6.0],
        "sl_candidates": [8.0, 10.0, 12.0],
        "be_ratio": 0.40,
        "be_lock": 0.40,
        "sweep_lookback": [12, 16, 20],
        "timeframes": [(mt5.TIMEFRAME_M15, "M15"), (mt5.TIMEFRAME_M30, "M30")],
    },
}

def simulate_engine(df, sigs, tgt_pts, sl_pts, be_ratio, be_lock_pts, spread_pts, max_hold=8):
    c = df["close"].values
    h = df["high"].values
    l = df["low"].values
    o = df["open"].values
    n = len(df)
    
    be_trig_pts = tgt_pts * be_ratio
    
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
            entry_px = o[k] + spread_pts * 0.5
            tp_px = entry_px + tgt_pts
            sl_px = entry_px - sl_pts
            cur_sl = sl_px
            be_trig_px = entry_px + be_trig_pts
            be_lock_px = entry_px + be_lock_pts
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
                if h[j] >= be_trig_px and cur_sl < be_lock_px:
                    cur_sl = be_lock_px
            if exit_px is None:
                j = min(n - 1, k + max_hold - 1)
                exit_px = c[j] - spread_pts * 0.5
            pnl_pts = exit_px - entry_px - spread_pts * 0.5
            trades.append({"time": entry_t, "pnl": pnl_pts, "r": pnl_pts / sl_pts, "win": 1 if pnl_pts > 0 else 0, "dir": "BUY"})
            i = j + 1
        elif s == -1:
            entry_px = o[k] - spread_pts * 0.5
            tp_px = entry_px - tgt_pts
            sl_px = entry_px + sl_pts
            cur_sl = sl_px
            be_trig_px = entry_px - be_trig_pts
            be_lock_px = entry_px - be_lock_pts
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
                if l[j] <= be_trig_px and cur_sl > be_lock_px:
                    cur_sl = be_lock_px
            if exit_px is None:
                j = min(n - 1, k + max_hold - 1)
                exit_px = c[j] + spread_pts * 0.5
            pnl_pts = entry_px - exit_px - spread_pts * 0.5
            trades.append({"time": entry_t, "pnl": pnl_pts, "r": pnl_pts / sl_pts, "win": 1 if pnl_pts > 0 else 0, "dir": "SELL"})
            i = j + 1
            
    return pd.DataFrame(trades)

def audit_symbol(symbol: str, config: dict):
    print(f"\n==========================================================================")
    print(f"AUDITORIA CUANTITATIVA MULTI-ACTIVO: {symbol}")
    print(f"==========================================================================")
    
    best_results = []
    
    for tf_code, tf_name in config["timeframes"]:
        rates = mt5.copy_rates_from_pos(symbol, tf_code, 0, 15000)
        if rates is None or len(rates) < 1000:
            print(f"No hay suficientes datos para {symbol} en {tf_name}")
            continue
            
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.set_index("time", inplace=True)
        
        c = df["close"].values
        h = df["high"].values
        l = df["low"].values
        o = df["open"].values
        hrs = df.index.hour.values
        dows = df.index.dayofweek.values
        n = len(df)
        
        rng = np.maximum(h - l, 1e-9)
        lower_wick = (np.minimum(o, c) - l) / rng
        upper_wick = (h - np.maximum(o, c)) / rng
        clv = (c - l) / rng
        
        # Medias e indicadores para filtros
        ema20 = pd.Series(c).ewm(span=20, adjust=False).mean().values
        sma200 = pd.Series(c).rolling(200, min_periods=40).mean().values
        
        # Keltner
        prev_c = pd.Series(c).shift(1).fillna(c[0]).values
        tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
        atr10 = pd.Series(tr).rolling(10, min_periods=3).mean().values
        k_lb = ema20 - 1.5 * atr10
        k_ub = ema20 + 1.5 * atr10
        k_rng = np.maximum(k_ub - k_lb, 1e-9)
        k_pos_lo = (l - k_lb) / k_rng
        k_pos_hi = (h - k_lb) / k_rng
        
        for lb in config["sweep_lookback"]:
            rec_hi = pd.Series(h).shift(1).rolling(lb, min_periods=4).max().values
            rec_lo = pd.Series(l).shift(1).rolling(lb, min_periods=4).min().values
            
            # Probar Modos: Long-Only vs Bidireccional (Long + Short)
            for mode in ["LONG_ONLY", "BIDIRECTIONAL"]:
                allow_short = (mode == "BIDIRECTIONAL")
                
                # Probar con y sin filtro macro SMA200
                for macro_filter in ["NONE", "SMA200"]:
                    sigs = np.zeros(n, dtype=int)
                    for i in range(lb + 5, n):
                        if dows[i] >= 5: continue
                        if not (config["s_start"] <= hrs[i] <= config["s_end"]): continue
                        
                        macro_l = (c[i] > sma200[i] and ema20[i] > sma200[i]) if macro_filter == "SMA200" else True
                        macro_s = (c[i] < sma200[i] and ema20[i] < sma200[i]) if macro_filter == "SMA200" else True
                        
                        # Filtro Keltner específico para GERMANY40 y US100
                        k_ok_l = (k_pos_lo[i] <= 0.38) if symbol in ["GERMANY40", "US100"] else True
                        k_ok_s = (k_pos_hi[i] >= 0.62) if symbol in ["GERMANY40", "US100"] else True
                        
                        # BUY: Sweep de minimo + rechazo verde
                        if (l[i] <= rec_lo[i]) and (c[i] > rec_lo[i]) and (c[i] > o[i]) and (lower_wick[i] >= 0.35) and (clv[i] >= 0.65) and macro_l and k_ok_l:
                            sigs[i] = 1
                        # SELL: Sweep de maximo + rechazo rojo (si permitido)
                        elif allow_short and (h[i] >= rec_hi[i]) and (c[i] < rec_hi[i]) and (c[i] < o[i]) and (upper_wick[i] >= 0.35) and (clv[i] <= 0.35) and macro_s and k_ok_s:
                            sigs[i] = -1
                            
                    for tgt in config["tgt_candidates"]:
                        for sl in config["sl_candidates"]:
                            tdf = simulate_engine(
                                df, sigs,
                                tgt_pts=tgt,
                                sl_pts=sl,
                                be_ratio=config["be_ratio"],
                                be_lock_pts=config["be_lock"],
                                spread_pts=config["spread_std"],
                                max_hold=8
                            )
                            if len(tdf) >= 10:
                                m = metrics(tdf["r"].to_numpy())
                                tdf_oct = tdf[tdf["time"] >= "2026-10-01"]
                                if len(tdf_oct) >= 4:
                                    m_oct = metrics(tdf_oct["r"].to_numpy())
                                    if m["win_rate"] >= 75.0 and m["profit_factor"] >= 1.25 and m_oct["win_rate"] >= 75.0:
                                        best_results.append({
                                            "symbol": symbol,
                                            "tf": tf_name,
                                            "mode": mode,
                                            "macro": macro_filter,
                                            "lb": lb,
                                            "tgt": tgt,
                                            "sl": sl,
                                            "full_trades": len(tdf),
                                            "full_wr": round(m["win_rate"], 1),
                                            "full_pf": round(m["profit_factor"], 2),
                                            "oct_trades": len(tdf_oct),
                                            "oct_wr": round(m_oct["win_rate"], 1),
                                            "oct_pf": round(m_oct["profit_factor"], 2),
                                            "oct_sum_r": round(float(tdf_oct["r"].sum()), 2),
                                            "oct_pts": round(float(tdf_oct["pnl"].sum()), 1),
                                        })
                                        
    res_df = pd.DataFrame(best_results)
    if not res_df.empty:
        res_df = res_df.sort_values(by=["oct_wr", "oct_pf", "full_wr"], ascending=[False, False, False])
        print(f"\nTOP CONFIGURACIONES ROBUSTAS PARA {symbol}:")
        print(res_df.head(10)[["tf", "mode", "macro", "lb", "tgt", "sl", "oct_trades", "oct_wr", "oct_pf", "oct_sum_r", "full_trades", "full_wr", "full_pf"]].to_string(index=False))
        return res_df.iloc[0].to_dict()
    else:
        print(f"No se encontraron combinaciones que cumplan el estandar >=75% en {symbol}.")
        return None

def main():
    if not mt5.initialize():
        print("ERROR: MT5 no inicializado")
        return
        
    master_summary = []
    for sym, cfg in ASSET_SPECS.items():
        res = audit_symbol(sym, cfg)
        if res:
            master_summary.append(res)
            
    print("\n\n" + "="*80)
    print("RESUMEN MAESTRO: EXTRAPOLACIÓN CUANTITATIVA A TODA LA CARTERA")
    print("="*80)
    sm_df = pd.DataFrame(master_summary)
    if not sm_df.empty:
        print(sm_df[["symbol", "tf", "mode", "macro", "lb", "tgt", "sl", "oct_trades", "oct_wr", "oct_pf", "oct_sum_r"]].to_string(index=False))
    mt5.shutdown()

if __name__ == "__main__":
    main()
