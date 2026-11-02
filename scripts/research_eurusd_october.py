"""Investigación profunda de EURUSD en MT5 para Octubre 2026 y Noviembre 2026.

Explora múltiples arquetipos y gatillos intradía (M5, M15, M30) sin restricciones artificiales:
- Sin límite de trades al día.
- Con cobertura horaria completa (sesión europea y americana: 06:00 a 20:00 UTC).
- Operando tanto LONG como SHORT.
- Evaluando Win Rate, Profit Factor, número de operaciones y rentabilidad en EUR.
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

def load_data(symbol="EURUSD", tf=mt5.TIMEFRAME_M15, n_bars=10000):
    if not mt5.initialize():
        print("ERROR: No se pudo inicializar MT5")
        sys.exit(1)
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, n_bars)
    if rates is None or len(rates) == 0:
        print(f"ERROR: No se obtuvieron datos para {symbol}")
        sys.exit(1)
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    return df

def run_simulation(df, signals, target_pips, stop_pips, be_trigger_pips=None, be_lock_pips=0.5, spread_pips=0.8, max_holding=8):
    """Simula operaciones con costes reales de spread y breakeven."""
    c = df["close"].values
    h = df["high"].values
    l = df["low"].values
    o = df["open"].values
    n = len(df)
    
    pip_val = 0.00010
    tgt_dist = target_pips * pip_val
    stop_dist = stop_pips * pip_val
    spr_cost = spread_pips * pip_val
    be_trig_dist = (be_trigger_pips * pip_val) if be_trigger_pips else None
    be_lock_dist = (be_lock_pips * pip_val) if be_lock_pips else None
    
    trades = []
    i = 0
    while i < n - 1:
        sig = signals[i]
        if sig == 0:
            i += 1
            continue
            
        k = i + 1  # Entrada a la apertura de la siguiente barra
        if k >= n:
            break
            
        entry_time = df.index[k]
        if sig == 1:  # LONG
            entry_px = o[k] + spr_cost * 0.5
            tp_px = entry_px + tgt_dist
            sl_px = entry_px - stop_dist
            cur_sl = sl_px
            be_target = entry_px + be_trig_dist if be_trig_dist else None
            be_new_sl = entry_px + be_lock_dist if be_lock_dist else None
            exit_px = None
            exit_time = None
            exit_reason = None
            
            for j in range(k, min(n, k + max_holding)):
                # Comprobar SL y TP
                hit_sl = l[j] <= cur_sl
                hit_tp = h[j] >= tp_px
                
                if hit_sl and hit_tp:
                    # Conservador: se asume SL primero si la vela es bajista
                    if c[j] < o[j]:
                        exit_px = cur_sl
                        exit_reason = "SL"
                    else:
                        exit_px = tp_px
                        exit_reason = "TP"
                    exit_time = df.index[j]
                    break
                elif hit_sl:
                    exit_px = cur_sl
                    exit_reason = "SL"
                    exit_time = df.index[j]
                    break
                elif hit_tp:
                    exit_px = tp_px
                    exit_reason = "TP"
                    exit_time = df.index[j]
                    break
                    
                # Comprobar Breakeven
                if be_target and h[j] >= be_target and cur_sl < be_new_sl:
                    cur_sl = be_new_sl
                    
            if exit_px is None:
                j = min(n - 1, k + max_holding - 1)
                exit_px = c[j] - spr_cost * 0.5
                exit_time = df.index[j]
                exit_reason = "TIME_EXIT"
                
            pnl_pips = (exit_px - entry_px - spr_cost * 0.5) / pip_val
            r_mult = pnl_pips / stop_pips
            trades.append({
                "entry_time": entry_time,
                "exit_time": exit_time,
                "dir": "BUY",
                "entry_px": entry_px,
                "exit_px": exit_px,
                "pnl_pips": pnl_pips,
                "r": r_mult,
                "win": 1 if pnl_pips > 0 else 0,
                "reason": exit_reason
            })
            i = j + 1
            
        elif sig == -1:  # SHORT
            entry_px = o[k] - spr_cost * 0.5
            tp_px = entry_px - tgt_dist
            sl_px = entry_px + stop_dist
            cur_sl = sl_px
            be_target = entry_px - be_trig_dist if be_trig_dist else None
            be_new_sl = entry_px - be_lock_dist if be_lock_dist else None
            exit_px = None
            exit_time = None
            exit_reason = None
            
            for j in range(k, min(n, k + max_holding)):
                hit_sl = h[j] >= cur_sl
                hit_tp = l[j] <= tp_px
                
                if hit_sl and hit_tp:
                    if c[j] > o[j]:
                        exit_px = cur_sl
                        exit_reason = "SL"
                    else:
                        exit_px = tp_px
                        exit_reason = "TP"
                    exit_time = df.index[j]
                    break
                elif hit_sl:
                    exit_px = cur_sl
                    exit_reason = "SL"
                    exit_time = df.index[j]
                    break
                elif hit_tp:
                    exit_px = tp_px
                    exit_reason = "TP"
                    exit_time = df.index[j]
                    break
                    
                if be_target and l[j] <= be_target and cur_sl > be_new_sl:
                    cur_sl = be_new_sl
                    
            if exit_px is None:
                j = min(n - 1, k + max_holding - 1)
                exit_px = c[j] + spr_cost * 0.5
                exit_time = df.index[j]
                exit_reason = "TIME_EXIT"
                
            pnl_pips = (entry_px - exit_px - spr_cost * 0.5) / pip_val
            r_mult = pnl_pips / stop_pips
            trades.append({
                "entry_time": entry_time,
                "exit_time": exit_time,
                "dir": "SELL",
                "entry_px": entry_px,
                "exit_px": exit_px,
                "pnl_pips": pnl_pips,
                "r": r_mult,
                "win": 1 if pnl_pips > 0 else 0,
                "reason": exit_reason
            })
            i = j + 1
            
    return pd.DataFrame(trades)

def main():
    print("Iniciando auditoria MT5 EURUSD...")
    for tf_code, tf_name in [(mt5.TIMEFRAME_M5, "M5"), (mt5.TIMEFRAME_M15, "M15")]:
        df = load_data("EURUSD", tf=tf_code, n_bars=15000)
        # Filtrar desde 1 de Octubre 2026 hasta hoy
        df_oct = df[df.index >= "2026-10-01"].copy()
        print(f"\n=======================================================")
        print(f"DATOS EURUSD {tf_name} DESDE 2026-10-01: {len(df_oct)} BARRAS ({df_oct.index[0]} a {df_oct.index[-1]})")
        print(f"=======================================================")
        
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
        
        # Medias e indicadores
        ema9 = pd.Series(c).ewm(span=9, adjust=False).mean().values
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
        
        rec_hi_6 = pd.Series(h).shift(1).rolling(6, min_periods=3).max().values
        rec_lo_6 = pd.Series(l).shift(1).rolling(6, min_periods=3).min().values
        rec_hi_12 = pd.Series(h).shift(1).rolling(12, min_periods=4).max().values
        rec_lo_12 = pd.Series(l).shift(1).rolling(12, min_periods=4).min().values
        rec_hi_24 = pd.Series(h).shift(1).rolling(24, min_periods=6).max().values
        rec_lo_24 = pd.Series(l).shift(1).rolling(24, min_periods=6).min().values
        
        # Test 1: Micro Liquidity Sweep & Reclaim (Sin SMA200 estricto, ambos lados BUY/SELL)
        # Horas amplias: 06:00 a 20:00 UTC (todo Londres + Wall Street)
        for sweep_bars, rec_hi, rec_lo in [(6, rec_hi_6, rec_lo_6), (12, rec_hi_12, rec_lo_12), (24, rec_hi_24, rec_lo_24)]:
            sig_sweep = np.zeros(n, dtype=int)
            for i in range(25, n):
                if dows[i] >= 5: continue
                if not (6 <= hrs[i] <= 19): continue
                
                # BUY: barrido de minimo + rechazo alcista
                if l[i] <= rec_lo[i] and c[i] > rec_lo[i] and c[i] > o[i] and lower_wick[i] >= 0.35 and clv[i] >= 0.60:
                    sig_sweep[i] = 1
                # SELL: barrido de maximo + rechazo bajista
                elif h[i] >= rec_hi[i] and c[i] < rec_hi[i] and c[i] < o[i] and upper_wick[i] >= 0.35 and clv[i] <= 0.40:
                    sig_sweep[i] = -1
                    
            for tgt, sl, be_trig in [(3.0, 5.0, 2.0), (4.0, 6.0, 2.5), (5.0, 7.5, 3.0), (6.0, 10.0, 4.0)]:
                res = run_simulation(df_oct, sig_sweep, target_pips=tgt, stop_pips=sl, be_trigger_pips=be_trig, be_lock_pips=0.5, spread_pips=0.8, max_holding=8)
                if len(res) >= 10:
                    m = metrics(res["r"].to_numpy())
                    print(f"Sweep {sweep_bars}b | TF={tf_name} | Tgt={tgt}p SL={sl}p BE={be_trig}p -> N={len(res):2d} | WR={m['win_rate']:5.1f}% | PF={m['profit_factor']:4.2f} | SumR={res['r'].sum():+5.2f}R | Pips={res['pnl_pips'].sum():+6.1f}p")

        # Test 2: Bollinger Reversion Scalp (Sobrecompra / Sobreventa a extremos)
        sig_bb = np.zeros(n, dtype=int)
        for i in range(25, n):
            if dows[i] >= 5: continue
            if not (6 <= hrs[i] <= 19): continue
            
            # BUY: Perfora banda inferior, rechazo verde, RSI2 < 20
            if l[i] <= bb_lo[i] and c[i] > o[i] and lower_wick[i] >= 0.30 and rsi2[i] < 20.0:
                sig_bb[i] = 1
            # SELL: Perfora banda superior, rechazo rojo, RSI2 > 80
            elif h[i] >= bb_hi[i] and c[i] < o[i] and upper_wick[i] >= 0.30 and rsi2[i] > 80.0:
                sig_bb[i] = -1
                
        for tgt, sl, be_trig in [(3.5, 5.0, 2.0), (4.5, 6.5, 2.5), (6.0, 8.0, 3.5)]:
            res_bb = run_simulation(df_oct, sig_bb, target_pips=tgt, stop_pips=sl, be_trigger_pips=be_trig, be_lock_pips=0.5, spread_pips=0.8, max_holding=8)
            if len(res_bb) >= 10:
                m = metrics(res_bb["r"].to_numpy())
                print(f"Bollinger Reversion | TF={tf_name} | Tgt={tgt}p SL={sl}p BE={be_trig}p -> N={len(res_bb):2d} | WR={m['win_rate']:5.1f}% | PF={m['profit_factor']:4.2f} | SumR={res_bb['r'].sum():+5.2f}R | Pips={res_bb['pnl_pips'].sum():+6.1f}p")

    mt5.shutdown()

if __name__ == "__main__":
    main()
