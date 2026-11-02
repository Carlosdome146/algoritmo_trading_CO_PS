"""Inspecciona todas las barras de EURUSD de hoy (2026-11-02) en M5 y M15.
Analiza la estructura, swings, mechas, y qué oportunidades claras de compra y venta se dieron.
"""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timezone

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

import MetaTrader5 as mt5
import pandas as pd
import numpy as np

def main():
    if not mt5.initialize():
        print("ERROR: Fallo MT5")
        return

    # Obtener barras de hoy
    rates = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_M15, 0, 150)
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    
    # Filtrar solo hoy 2 de Noviembre 2026
    df_today = df[df.index >= "2026-11-02 00:00:00"].copy()
    print(f"Total barras EURUSD M15 hoy: {len(df_today)}")
    print(f"Rango del día: Mínimo={df_today['low'].min():.5f} | Máximo={df_today['high'].max():.5f} | Rango={((df_today['high'].max() - df_today['low'].min())*10000):.1f} pips")
    
    # Mostrar cada vela con sus métricas
    c = df_today["close"].values
    h = df_today["high"].values
    l = df_today["low"].values
    o = df_today["open"].values
    rng = np.maximum(h - l, 1e-9)
    lower_wick = (np.minimum(o, c) - l) / rng
    upper_wick = (h - np.maximum(o, c)) / rng
    clv = (c - l) / rng
    
    # Medias
    ema20 = pd.Series(c).ewm(span=20, adjust=False).mean().values
    
    print("\nVELAS M15 HOY CON MECHAS SIGNIFICATIVAS O SWINGS:")
    for idx, (t, row) in enumerate(df_today.iterrows()):
        lw = lower_wick[idx]
        uw = upper_wick[idx]
        p_rng = rng[idx] * 10000 # pips
        color = "VERDE" if c[idx] >= o[idx] else "ROJA "
        
        # Destacar velas con rechazo claro (mecha >= 35%)
        flag = ""
        if lw >= 0.40 and color == "VERDE":
            flag = ">>> CANDIDATO BUY (Rechazo inferior)"
        elif uw >= 0.40 and color == "ROJA ":
            flag = ">>> CANDIDATO SELL (Rechazo superior)"
            
        print(f"[{t.strftime('%H:%M')} UTC] O={o[idx]:.5f} H={h[idx]:.5f} L={l[idx]:.5f} C={c[idx]:.5f} | Rng={p_rng:4.1f}p {color} | L_Wick={lw:4.1%} U_Wick={uw:4.1%} CLV={clv[idx]:.2f} {flag}")

    mt5.shutdown()

if __name__ == "__main__":
    main()
