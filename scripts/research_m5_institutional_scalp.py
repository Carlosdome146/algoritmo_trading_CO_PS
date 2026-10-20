"""Laboratorio Cuantitativo de Micro-Scalping Institucional en M5 (Datos Directos de MT5).

Prueba de la hipótesis de Ismael:
- Entradas de francotirador en ventanas institucionales de alta liquidez.
- Captura de micro-reversiones rápidas tras barridos de liquidez (Liquidity Sweeps).
- Objetivos cortos (2-4 pips FX, 10-15 pts DAX) con time-stop estricto.
- Datos: 50.000 barras M5 reales descargadas directamente desde MetaTrader 5.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

from trading_v2.research.regime_lab_v3 import wilson_lb, metrics


def fetch_mt5_m5_bars(symbol: str, count: int = 50000) -> pd.DataFrame:
    """Descarga barras M5 reales directamente de MT5 con spreads reales."""
    if not mt5.initialize():
        raise RuntimeError(f"No se pudo conectar a MT5: {mt5.last_error()}")
    
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, count)
    if rates is None or len(rates) == 0:
        raise ValueError(f"No se pudieron descargar datos para {symbol}")
        
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    df.sort_index(inplace=True)
    df = df[~df.index.duplicated(keep="first")]
    
    # Renombrar a columnas estándar
    df.rename(columns={
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "tick_volume": "TickVolume",
        "spread": "Spread"
    }, inplace=True)
    
    return df


def calculate_m5_microstructure(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Calcula indicadores de microestructura causal para M5."""
    out = df.copy()
    c, h, l, o = out["Close"], out["High"], out["Low"], out["Open"]
    
    # ATR 14
    prev_c = c.shift(1)
    tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    out["atr14"] = tr.rolling(14, min_periods=5).mean()
    
    # RSI rápido de 2 periodos
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / 2, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / 2, adjust=False).mean()
    out["rsi2"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    
    # Bandas de Bollinger M5 (20 periodos, 2.0 y 2.5 sigma)
    sma20 = c.rolling(20, min_periods=10).mean()
    std20 = c.rolling(20, min_periods=10).std(ddof=0)
    out["sma20"] = sma20
    out["bb_up_20"] = sma20 + 2.0 * std20
    out["bb_lo_20"] = sma20 - 2.0 * std20
    out["bb_up_25"] = sma20 + 2.5 * std20
    out["bb_lo_25"] = sma20 - 2.5 * std20
    
    # Mechas de rechazo y Close Location Value
    rng = (h - l).replace(0, np.nan)
    out["clv"] = ((c - l) / rng).fillna(0.5)
    out["lower_wick"] = ((np.minimum(o, c) - l) / rng).fillna(0.0)
    out["upper_wick"] = ((h - np.maximum(o, c)) / rng).fillna(0.0)
    
    # Barrido de liquidez: máximo y mínimo móvil de las últimas N barras (ej. 12 barras = 1 hora)
    out["recent_high"] = h.shift(1).rolling(12, min_periods=6).max()
    out["recent_low"] = l.shift(1).rolling(12, min_periods=6).min()
    
    # Volumen relativo RVOL
    vol = out["TickVolume"].astype(float)
    vol_sma = vol.rolling(20, min_periods=5).mean()
    out["rvol"] = vol / vol_sma.replace(0, np.nan)
    
    # Horas UTC
    out["hour_utc"] = out.index.hour
    out["minute_utc"] = out.index.minute
    
    return out


@dataclass
class MicroScalpSetup:
    symbol: str
    target_units: float       # Pips en FX, Puntos en Índices, $ en Oro
    stop_units: float         # Stop loss en las mismas unidades
    session_start_h: int      # Hora UTC de inicio
    session_end_h: int        # Hora UTC de fin
    max_holding_bars: int     # Time-stop (en barras M5, ej 3 barras = 15 min)
    use_sweep: bool           # Exigir barrido de High/Low previo
    sweep_pips: float         # Magnitud mínima del barrido
    rsi_th: float             # Umbral de RSI2 (< th para long, > 100-th para short)
    min_wick: float           # Mecha de rechazo mínima (0.30 = 30%)
    min_rvol: float           # Volumen relativo mínimo (1.0 = normal)


def simulate_setup(df: pd.DataFrame, cfg: MicroScalpSetup) -> pd.DataFrame:
    c = df["Close"].to_numpy(dtype=float)
    o = df["Open"].to_numpy(dtype=float)
    h = df["High"].to_numpy(dtype=float)
    l = df["Low"].to_numpy(dtype=float)
    spread = df["Spread"].to_numpy(dtype=float)
    hours = df["hour_utc"].to_numpy()
    rsi2 = df["rsi2"].to_numpy()
    bb_lo = df["bb_lo_20"].to_numpy()
    bb_up = df["bb_up_20"].to_numpy()
    recent_hi = df["recent_high"].to_numpy()
    recent_lo = df["recent_low"].to_numpy()
    lower_wick = df["lower_wick"].to_numpy()
    upper_wick = df["upper_wick"].to_numpy()
    clv = df["clv"].to_numpy()
    rvol = df["rvol"].to_numpy()
    idx = df.index
    n = len(df)
    
    # Unidades a precio
    if cfg.symbol == "EURUSD":
        unit_val = 0.00010  # 1 pip = 0.00010
        point = 0.00001
    elif "GERMANY40" in cfg.symbol or "DAX" in cfg.symbol:
        unit_val = 1.0      # 1 punto = 1.0 EUR
        point = 0.01
    elif "SP500" in cfg.symbol or "US500" in cfg.symbol:
        unit_val = 1.0      # 1 punto SP500
        point = 0.01
    elif "US100" in cfg.symbol or "NAS" in cfg.symbol:
        unit_val = 1.0      # 1 punto Nasdaq
        point = 0.01
    elif "GOLD" in cfg.symbol:
        unit_val = 1.0      # $1 en Oro
        point = 0.01
    else:
        unit_val = 1.0
        point = 0.01
        
    target_dist = cfg.target_units * unit_val
    stop_dist = cfg.stop_units * unit_val
    sweep_dist = cfg.sweep_pips * unit_val
    
    trades = []
    i = 30
    while i < n - 1:
        hr = hours[i]
        if not (cfg.session_start_h <= hr <= cfg.session_end_h):
            i += 1
            continue
            
        spr_price = spread[i] * point
        # Si el spread está anormalmente ensanchado (> 2.5x normal), vetar
        if cfg.symbol == "EURUSD" and spread[i] > 15:  # > 1.5 pips
            i += 1
            continue
        elif "GERMANY40" in cfg.symbol and spread[i] > 250: # > 2.5 pts
            i += 1
            continue
            
        # Condición LONG (Barrido de suelo + absorción / RSI2 extremo)
        long_cond = False
        if cfg.use_sweep:
            # La vela barrió el mínimo reciente de la última hora pero cerró por encima del mínimo o con mecha
            swept_low = (l[i] <= (recent_lo[i] - sweep_dist))
            long_cond = swept_low and (lower_wick[i] >= cfg.min_wick) and (clv[i] >= 0.45)
        else:
            long_cond = (rsi2[i] < cfg.rsi_th) and (c[i] <= bb_lo[i]) and (lower_wick[i] >= cfg.min_wick)
            
        if cfg.min_rvol > 0:
            long_cond = long_cond and (rvol[i] >= cfg.min_rvol)
            
        # Condición SHORT (Barrido de techo + absorción / RSI2 extremo)
        short_cond = False
        if cfg.use_sweep:
            swept_high = (h[i] >= (recent_hi[i] + sweep_dist))
            short_cond = swept_high and (upper_wick[i] >= cfg.min_wick) and (clv[i] <= 0.55)
        else:
            short_cond = (rsi2[i] > (100 - cfg.rsi_th)) and (c[i] >= bb_up[i]) and (upper_wick[i] >= cfg.min_wick)
            
        if cfg.min_rvol > 0:
            short_cond = short_cond and (rvol[i] >= cfg.min_rvol)
            
        side = 1 if long_cond else (-1 if short_cond else 0)
        if side == 0:
            i += 1
            continue
            
        # Entrada en apertura de la siguiente barra i+1
        k = i + 1
        entry_mid = o[k]
        # LONG compra al Ask (+ spr/2), SHORT vende al Bid (- spr/2)
        exec_spr = spread[k] * point
        entry = entry_mid + side * (exec_spr / 2.0)
        
        tp = entry + side * target_dist
        sl = entry - side * stop_dist
        
        exit_px = None
        reason = "TIMEOUT"
        j = k
        for j in range(k, min(n, k + cfg.max_holding_bars)):
            bar_spr = spread[j] * point
            # LONG sale al Bid (mid - spr/2), SHORT cubre al Ask (mid + spr/2)
            eval_lo = l[j] - side * (bar_spr / 2.0)
            eval_hi = h[j] - side * (bar_spr / 2.0)
            
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
            # Salida por tiempo en el Close de la barra límite
            j = min(n - 1, k + cfg.max_holding_bars - 1)
            exit_px = c[j] - side * (spread[j] * point / 2.0)
            
        net_price_pnl = side * (exit_px - entry)
        # Descontar comisión IC Markets Raw si es Forex ($7 / round-trip = ~0.65 pips)
        comm_price = 0.000065 if cfg.symbol == "EURUSD" else 0.0
        net_price_pnl -= comm_price
        
        r = net_price_pnl / stop_dist
        units_won = net_price_pnl / unit_val
        
        trades.append({
            "entry_time": idx[k],
            "exit_time": idx[j],
            "side": "LONG" if side == 1 else "SHORT",
            "entry": entry,
            "exit": exit_px,
            "units_won": units_won,
            "r": r,
            "reason": reason,
            "bars_held": j - k + 1,
        })
        i = j + 1  # No solapar
        
    return pd.DataFrame(trades)


def run_comprehensive_study():
    symbols = ["EURUSD", "GERMANY40", "[SP500]", "US100", "GOLD"]
    print("=" * 105)
    print("LABORATORIO FORENSE M5: MICRO-SCALPING INSTITUCIONAL (50.000 BARRAS REALES MT5)")
    print("=" * 105)
    print(f"{'ACTIVO':<10s} | {'MODO':<12s} | {'TARGET':<10s} | {'STOP':<10s} | {'N':<5s} | {'WIN RATE':<10s} | {'W-LB':<8s} | {'PF':<6s} | {'R MEDIO':<8s} | {'PnL (2 lotes)':<14s}")
    print("-" * 105)
    
    for sym in symbols:
        df_raw = fetch_mt5_m5_bars(sym, 50000)
        df = calculate_m5_microstructure(df_raw, sym)
        
        # Probar parámetros adaptados al activo
        if sym == "EURUSD":
            # Ventana Londres/NY (07:00 - 15:00 UTC)
            test_configs = [
                # Modo A: Liquidity Sweep puro (tipo Ismael)
                MicroScalpSetup(sym, target_units=2.3, stop_units=4.0, session_start_h=7, session_end_h=15, max_holding_bars=3, use_sweep=True, sweep_pips=1.5, rsi_th=15, min_wick=0.35, min_rvol=1.1),
                MicroScalpSetup(sym, target_units=2.5, stop_units=5.0, session_start_h=7, session_end_h=15, max_holding_bars=4, use_sweep=True, sweep_pips=2.0, rsi_th=15, min_wick=0.40, min_rvol=1.2),
                MicroScalpSetup(sym, target_units=3.0, stop_units=6.0, session_start_h=7, session_end_h=15, max_holding_bars=4, use_sweep=True, sweep_pips=2.0, rsi_th=15, min_wick=0.35, min_rvol=1.0),
                # Modo B: Reversión estadística pura
                MicroScalpSetup(sym, target_units=2.5, stop_units=6.0, session_start_h=7, session_end_h=15, max_holding_bars=3, use_sweep=False, sweep_pips=0, rsi_th=8, min_wick=0.35, min_rvol=0.0),
                MicroScalpSetup(sym, target_units=3.5, stop_units=7.0, session_start_h=7, session_end_h=15, max_holding_bars=4, use_sweep=False, sweep_pips=0, rsi_th=10, min_wick=0.30, min_rvol=0.0),
            ]
        elif "GERMANY40" in sym:
            # Ventana Frankfurt / Londres (07:00 - 11:30 UTC)
            test_configs = [
                MicroScalpSetup(sym, target_units=12.0, stop_units=20.0, session_start_h=7, session_end_h=11, max_holding_bars=4, use_sweep=True, sweep_pips=8.0, rsi_th=15, min_wick=0.35, min_rvol=1.1),
                MicroScalpSetup(sym, target_units=15.0, stop_units=25.0, session_start_h=7, session_end_h=11, max_holding_bars=5, use_sweep=True, sweep_pips=10.0, rsi_th=15, min_wick=0.35, min_rvol=1.2),
                MicroScalpSetup(sym, target_units=10.0, stop_units=18.0, session_start_h=7, session_end_h=11, max_holding_bars=3, use_sweep=False, sweep_pips=0, rsi_th=10, min_wick=0.35, min_rvol=0.0),
            ]
        elif "[SP500]" in sym:
            # Ventana New York (13:30 - 16:30 UTC)
            test_configs = [
                MicroScalpSetup(sym, target_units=3.5, stop_units=6.0, session_start_h=13, session_end_h=16, max_holding_bars=4, use_sweep=True, sweep_pips=2.5, rsi_th=15, min_wick=0.35, min_rvol=1.1),
                MicroScalpSetup(sym, target_units=4.0, stop_units=7.0, session_start_h=13, session_end_h=16, max_holding_bars=5, use_sweep=True, sweep_pips=3.0, rsi_th=15, min_wick=0.35, min_rvol=1.2),
                MicroScalpSetup(sym, target_units=3.0, stop_units=5.0, session_start_h=13, session_end_h=16, max_holding_bars=3, use_sweep=False, sweep_pips=0, rsi_th=10, min_wick=0.35, min_rvol=0.0),
            ]
        elif "US100" in sym:
            # Ventana New York (13:30 - 16:30 UTC)
            test_configs = [
                MicroScalpSetup(sym, target_units=18.0, stop_units=30.0, session_start_h=13, session_end_h=16, max_holding_bars=4, use_sweep=True, sweep_pips=15.0, rsi_th=15, min_wick=0.35, min_rvol=1.1),
                MicroScalpSetup(sym, target_units=25.0, stop_units=40.0, session_start_h=13, session_end_h=16, max_holding_bars=5, use_sweep=True, sweep_pips=20.0, rsi_th=15, min_wick=0.35, min_rvol=1.2),
            ]
        else: # GOLD
            # Ventana Londres + NY (07:00 - 16:00 UTC)
            test_configs = [
                MicroScalpSetup(sym, target_units=2.0, stop_units=3.5, session_start_h=7, session_end_h=16, max_holding_bars=4, use_sweep=True, sweep_pips=1.5, rsi_th=15, min_wick=0.35, min_rvol=1.1),
                MicroScalpSetup(sym, target_units=2.5, stop_units=4.5, session_start_h=7, session_end_h=16, max_holding_bars=4, use_sweep=False, sweep_pips=0, rsi_th=10, min_wick=0.35, min_rvol=0.0),
            ]
            
        for cfg in test_configs:
            tdf = simulate_setup(df, cfg)
            if len(tdf) >= 5:
                r_arr = tdf["r"].to_numpy()
                m = metrics(r_arr)
                n_tr = m["n"]
                wr = m["win_rate"]
                wlb = wilson_lb(int(round(wr * n_tr / 100)), n_tr) * 100
                pf = m.get("profit_factor", 0.0)
                mean_r = m["mean_r"]
                
                # Cálculo de PnL en EUR aproximado con 2.0 lotes
                if sym == "EURUSD":
                    # 2 lotes = $20/pip -> a EUR (1.12) = 17.8 EUR/pip
                    total_pips = tdf["units_won"].sum()
                    eur_pnl = total_pips * 17.8
                    mode_str = "SWEEP" if cfg.use_sweep else "BOLL_RSI"
                    tgt_str = f"{cfg.target_units:.1f}p"
                    stp_str = f"{cfg.stop_units:.1f}p"
                elif "GERMANY40" in sym:
                    # 2 lotes DAX = 2 EUR / punto
                    total_pts = tdf["units_won"].sum()
                    eur_pnl = total_pts * 2.0
                    mode_str = "SWEEP" if cfg.use_sweep else "BOLL_RSI"
                    tgt_str = f"{cfg.target_units:.1f}pt"
                    stp_str = f"{cfg.stop_units:.1f}pt"
                elif "[SP500]" in sym:
                    # 2 lotes SP500 = 2 USD / punto (~1.78 EUR)
                    total_pts = tdf["units_won"].sum()
                    eur_pnl = total_pts * 1.78
                    mode_str = "SWEEP" if cfg.use_sweep else "BOLL_RSI"
                    tgt_str = f"{cfg.target_units:.1f}pt"
                    stp_str = f"{cfg.stop_units:.1f}pt"
                elif "US100" in sym:
                    total_pts = tdf["units_won"].sum()
                    eur_pnl = total_pts * 1.78
                    mode_str = "SWEEP" if cfg.use_sweep else "BOLL_RSI"
                    tgt_str = f"{cfg.target_units:.1f}pt"
                    stp_str = f"{cfg.stop_units:.1f}pt"
                else:
                    total_pts = tdf["units_won"].sum()
                    eur_pnl = total_pts * 17.8
                    mode_str = "SWEEP" if cfg.use_sweep else "BOLL_RSI"
                    tgt_str = f"{cfg.target_units:.1f}$"
                    stp_str = f"{cfg.stop_units:.1f}$"
                    
                print(f"{sym:<10s} | {mode_str:<12s} | {tgt_str:<10s} | {stp_str:<10s} | {n_tr:<5d} | {wr:<9.1f}% | {wlb:<7.1f}% | {pf:<6.2f} | {mean_r:+7.4f}  | {eur_pnl:+11.2f} €")
        print("-" * 105)
    print("=" * 105)


if __name__ == "__main__":
    run_comprehensive_study()
    mt5.shutdown()
