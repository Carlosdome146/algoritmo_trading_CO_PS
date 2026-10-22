"""Auditoría de Operaciones Históricas de Francotirador (Trinidad de 3 Activos).

Revisa las 50.000 barras M5 reales de MT5 e identifica los disparos exactos
que nuestro modelo habría ejecutado, documentando fecha, hora, punto de entrada,
motivo del disparo, precio de salida y PnL generado.
"""
from __future__ import annotations

import pandas as pd
import numpy as np
import MetaTrader5 as mt5

from trading_v2.strategies.micro_scalping import (
    SniperScalpConfig,
    generate_sniper_signals,
)


def fetch_m5_data(symbol: str, count: int = 15000) -> pd.DataFrame:
    if not mt5.initialize():
        raise RuntimeError("No se pudo conectar con MT5")
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, count)
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "spread": "Spread"}, inplace=True)
    return df


def audit_symbol(symbol: str, target: float, stop: float, session_start: int, session_end: int, min_sweep: float, min_wick: float):
    df = fetch_m5_data(symbol, 15000)
    cfg = SniperScalpConfig(
        symbol=symbol,
        target_units=target,
        stop_units=stop,
        session_start_h=session_start,
        session_end_h=session_end,
        max_holding_bars=6,
        min_sweep_units=min_sweep,
        min_rejection_wick=min_wick,
        max_trades_per_day=None, # Sin límite artificial
        cooldown_bars=4,
        use_h1_filter=False,
    )
    sig_df = generate_sniper_signals(df, cfg)
    
    unit = 0.00010 if symbol == "EURUSD" else 1.0
    point = 0.00001 if symbol == "EURUSD" else 0.01
    comm = 0.000065 if symbol == "EURUSD" else 0.0 # IC Markets Raw FX comm
    
    tgt_dist = target * unit
    sl_dist = stop * unit
    
    signals = sig_df[sig_df["signal"] != 0]
    trades = []
    
    c = df["Close"].to_numpy()
    o = df["Open"].to_numpy()
    h = df["High"].to_numpy()
    l = df["Low"].to_numpy()
    spr = df["Spread"].to_numpy() * point
    idx = df.index
    n = len(df)
    
    for sig_time in signals.index:
        i = df.index.get_loc(sig_time)
        if i >= n - 1:
            continue
        side = int(sig_df["signal"].iloc[i])
        k = i + 1
        entry = o[k] + side * (spr[k] / 2.0)
        tp = entry + side * tgt_dist
        sl = entry - side * sl_dist
        
        exit_px = None
        reason = "TIMEOUT"
        j = k
        for j in range(k, min(n, k + cfg.max_holding_bars)):
            eval_lo = l[j] - side * (spr[j] / 2.0)
            eval_hi = h[j] - side * (spr[j] / 2.0)
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
            j = min(n - 1, k + cfg.max_holding_bars - 1)
            exit_px = c[j] - side * (spr[j] / 2.0)
            
        net_price = side * (exit_px - entry) - comm
        pnl_units = net_price / unit
        duration_min = (j - k + 1) * 5
        
        trades.append({
            "entry_time": idx[k],
            "exit_time": idx[j],
            "side": "COMPRA (LONG)" if side == 1 else "VENTA (SHORT)",
            "entry_px": entry,
            "exit_px": exit_px,
            "pnl_units": pnl_units,
            "duration_min": duration_min,
            "reason": reason,
        })
        
    return pd.DataFrame(trades)


def main():
    print("=" * 110)
    print("AUDITORÍA DE DISPAROS DE FRANCOTIRADOR HISTÓRICOS EN LA TRINIDAD DE ACTIVOS (DATOS REALES MT5)")
    print("=" * 110)
    
    # 1. DAX 40 (Apertura Frankfurt/Londres: 07:00 a 11:00 UTC)
    print("\n--- 1. DAX 40 (GERMANY40) - Ventana de Apertura Europea (07:00 - 11:00 UTC) ---")
    dax_trades = audit_symbol("GERMANY40", target=15.0, stop=25.0, session_start=7, session_end=11, min_sweep=8.0, min_wick=0.35)
    if len(dax_trades) > 0:
        win_rate = (dax_trades["pnl_units"] > 0).mean() * 100
        pnl_total = dax_trades["pnl_units"].sum()
        print(f"Total Disparos Detectados: {len(dax_trades)} | Tasa de Acierto: {win_rate:.1f}% | PnL Total en Puntos: {pnl_total:+.1f} pts")
        print("Últimos 5 Disparos Concretos Ejecutados:")
        for _, t in dax_trades.tail(5).iterrows():
            res_icon = "[WIN]" if t["pnl_units"] > 0 else "[LOSS]"
            print(f"  {res_icon} {t['entry_time'].strftime('%Y-%m-%d %H:%M UTC')} | {t['side']} | Entrada: {t['entry_px']:.1f} -> Salida: {t['exit_px']:.1f} | Resultado: {t['pnl_units']:+5.1f} pts ({t['reason']}) en {t['duration_min']} min")

    # 2. S&P 500 (Apertura Wall Street: 13:30 a 16:30 UTC)
    print("\n--- 2. S&P 500 ([SP500]) - Ventana de Apertura Wall Street (13:30 - 16:30 UTC) ---")
    sp_trades = audit_symbol("[SP500]", target=4.5, stop=7.5, session_start=13, session_end=16, min_sweep=2.5, min_wick=0.35)
    if len(sp_trades) > 0:
        win_rate = (sp_trades["pnl_units"] > 0).mean() * 100
        pnl_total = sp_trades["pnl_units"].sum()
        print(f"Total Disparos Detectados: {len(sp_trades)} | Tasa de Acierto: {win_rate:.1f}% | PnL Total en Puntos: {pnl_total:+.1f} pts")
        print("Últimos 5 Disparos Concretos Ejecutados:")
        for _, t in sp_trades.tail(5).iterrows():
            res_icon = "[WIN]" if t["pnl_units"] > 0 else "[LOSS]"
            print(f"  {res_icon} {t['entry_time'].strftime('%Y-%m-%d %H:%M UTC')} | {t['side']} | Entrada: {t['entry_px']:.2f} -> Salida: {t['exit_px']:.2f} | Resultado: {t['pnl_units']:+5.2f} pts ({t['reason']}) en {t['duration_min']} min")

    # 3. EURUSD (Apertura Londres: 07:00 a 11:00 UTC)
    print("\n--- 3. EUR/USD (EURUSD) - Ventana de Apertura Londres (07:00 - 11:00 UTC) ---")
    eur_trades = audit_symbol("EURUSD", target=3.0, stop=5.0, session_start=7, session_end=11, min_sweep=1.5, min_wick=0.35)
    if len(eur_trades) > 0:
        win_rate = (eur_trades["pnl_units"] > 0).mean() * 100
        pnl_total = eur_trades["pnl_units"].sum()
        print(f"Total Disparos Detectados: {len(eur_trades)} | Tasa de Acierto: {win_rate:.1f}% | PnL Total en Pips: {pnl_total:+.1f} pips")
        print("Últimos 5 Disparos Concretos Ejecutados:")
        for _, t in eur_trades.tail(5).iterrows():
            res_icon = "[WIN]" if t["pnl_units"] > 0 else "[LOSS]"
            print(f"  {res_icon} {t['entry_time'].strftime('%Y-%m-%d %H:%M UTC')} | {t['side']} | Entrada: {t['entry_px']:.5f} -> Salida: {t['exit_px']:.5f} | Resultado: {t['pnl_units']:+5.2f} pips ({t['reason']}) en {t['duration_min']} min")
    
    print("=" * 110)
    mt5.shutdown()


if __name__ == "__main__":
    main()
