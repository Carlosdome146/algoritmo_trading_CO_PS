#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Auditoría Forense Cuantitativa Multi-Activo a 4+ Años (2022 - 2026).

Evalúa con rigor institucional y retrospectiva sobre hasta 60,000 barras por activo:
1. GERMANY40 (DAX40 M30)
2. [SP500] (S&P 500 M30)
3. US100 (Nasdaq 100 M30)
4. [DJI30] (Dow Jones 30 M30)
5. [IBEX35] (IBEX 35 M15)
6. GOLD (Oro XAUUSD M30)
7. EURUSD (Euro/Dólar M15)

Compara:
- BASELINE ACTUAL vs OPCIÓN A1 (Veto Campana de Apertura 5 min) vs HORARIOS CALIBRADOS.
- Desglose empírico de Tasa de Acierto y Rentabilidad por Hora del Día (UTC).
"""
from __future__ import annotations

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trading_v2.strategies.micro_scalping import (
    SniperScalpConfig,
    generate_sniper_signals,
    compute_sniper_indicators,
)


ASSETS_CONFIG = {
    "GERMANY40": {
        "tf": mt5.TIMEFRAME_M30,
        "tf_str": "M30",
        "target_u": 22.0,
        "stop_u": 35.0,
        "s_start": 7,
        "s_end": 17,
        "min_wick": 0.35,
        "allow_short": True,
        "max_opp_wick": None,
        "unit_mult": 1.0,
        "spread": 1.2,
        "bell_hours": [7, 8],  # 07:00 UTC (08:00 CET) y 08:00 UTC (09:00 CET)
    },
    "[SP500]": {
        "tf": mt5.TIMEFRAME_M30,
        "tf_str": "M30",
        "target_u": 4.0,
        "stop_u": 12.0,
        "s_start": 12,
        "s_end": 21,
        "min_wick": 0.35,
        "allow_short": False,
        "max_opp_wick": None,
        "unit_mult": 1.0,
        "spread": 0.40,
        "bell_hours": [13],  # 13:30 UTC Wall Street
    },
    "US100": {
        "tf": mt5.TIMEFRAME_M30,
        "tf_str": "M30",
        "target_u": 25.0,
        "stop_u": 70.0,
        "s_start": 12,
        "s_end": 21,
        "min_wick": 0.35,
        "allow_short": False,
        "max_opp_wick": None,
        "unit_mult": 1.0,
        "spread": 1.5,
        "bell_hours": [13],  # 13:30 UTC Wall Street
    },
    "[DJI30]": {
        "tf": mt5.TIMEFRAME_M30,
        "tf_str": "M30",
        "target_u": 40.0,
        "stop_u": 80.0,
        "s_start": 12,
        "s_end": 21,
        "min_wick": 0.35,
        "allow_short": False,
        "max_opp_wick": None,
        "unit_mult": 1.0,
        "spread": 2.0,
        "bell_hours": [13],  # 13:30 UTC Wall Street
    },
    "[IBEX35]": {
        "tf": mt5.TIMEFRAME_M15,
        "tf_str": "M15",
        "target_u": 20.0,
        "stop_u": 45.0,
        "s_start": 7,
        "s_end": 17,
        "min_wick": 0.35,
        "allow_short": False,
        "max_opp_wick": None,
        "unit_mult": 1.0,
        "spread": 3.5,
        "bell_hours": [7, 8],  # 07:00 UTC y 08:00 UTC
    },
    "GOLD": {
        "tf": mt5.TIMEFRAME_M30,
        "tf_str": "M30",
        "target_u": 4.0,
        "stop_u": 12.0,
        "s_start": 12,
        "s_end": 19,
        "min_wick": 0.45,
        "allow_short": False,
        "max_opp_wick": 0.12,
        "unit_mult": 1.0,
        "spread": 0.35,
        "bell_hours": [13],  # 13:30 UTC Wall Street
    },
    "EURUSD": {
        "tf": mt5.TIMEFRAME_M15,
        "tf_str": "M15",
        "target_u": 3.5,
        "stop_u": 5.5,
        "s_start": 6,
        "s_end": 20,
        "min_wick": 0.35,
        "allow_short": True,
        "max_opp_wick": None,
        "unit_mult": 0.00010,
        "spread": 0.00008,
        "bell_hours": [7, 13],  # 07:00 UTC Londres y 13:30 UTC NY
    },
}


def load_symbol_bars(symbol: str, tf: int, count: int = 60000) -> pd.DataFrame:
    mt5.symbol_select(symbol, True)
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    if rates is None or len(rates) == 0:
        return pd.DataFrame()
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    df.rename(
        columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "tick_volume": "Volume"},
        inplace=True,
    )
    return df


def simulate_asset(
    df: pd.DataFrame,
    cfg_info: dict,
    symbol: str,
    veto_opening_bell: bool = False,
    risk_eur: float = 30.58,  # 1% de 3058 EUR
) -> dict:
    cfg = SniperScalpConfig(
        symbol=symbol,
        target_units=cfg_info["target_u"],
        stop_units=cfg_info["stop_u"],
        session_start_h=cfg_info["s_start"],
        session_end_h=cfg_info["s_end"],
        min_rejection_wick=cfg_info["min_wick"],
        max_opposite_wick=cfg_info["max_opp_wick"],
        use_h1_filter=True,
        use_ker_filter=True,
        max_ker_trend=0.45,
        cooldown_bars=2,
        use_climax_filter=True,
        allow_short=cfg_info["allow_short"],
    )

    sig_df = generate_sniper_signals(df, cfg)
    signals = sig_df["signal"].to_numpy().copy()

    # Veto de campana de apertura (Opción A1)
    if veto_opening_bell:
        times_idx = df.index
        bell_hs = cfg_info["bell_hours"]
        for k in range(len(signals)):
            t_bar = times_idx[k]
            # Si el cierre de barra cae exactamente en toque de campana (ej: 07:00 o 13:30 UTC)
            if t_bar.hour in bell_hs and (t_bar.minute == 0 or t_bar.minute == 30):
                signals[k] = 0

    times = df.index
    opens = df["Open"].to_numpy()
    highs = df["High"].to_numpy()
    lows = df["Low"].to_numpy()
    closes = df["Close"].to_numpy()
    n = len(df)

    unit_m = cfg_info["unit_mult"]
    spread = cfg_info["spread"]
    tp_dist = cfg_info["target_u"] * unit_m
    sl_dist = cfg_info["stop_u"] * unit_m

    trades = []
    i = 0
    while i < n - 1:
        sig = signals[i]
        if sig != 0:
            entry_time = times[i + 1]
            if sig == 1:
                entry_px = opens[i + 1] + spread
                sl_px = entry_px - sl_dist
                tp_px = entry_px + tp_dist
            else:
                entry_px = opens[i + 1]
                sl_px = entry_px + sl_dist
                tp_px = entry_px - tp_dist

            exit_time = None
            exit_px = None
            exit_reason = None

            for j in range(i + 1, min(i + 1 + 8, n)):
                b_h = highs[j]
                b_l = lows[j]
                b_c = closes[j]
                b_o = opens[j]

                if sig == 1:
                    if b_l <= sl_px and b_h >= tp_px:
                        exit_px = tp_px if b_c > b_o else sl_px
                        exit_reason = "TP" if b_c > b_o else "SL"
                        exit_time = times[j]
                        break
                    elif b_h >= tp_px:
                        exit_px = tp_px
                        exit_reason = "TP"
                        exit_time = times[j]
                        break
                    elif b_l <= sl_px:
                        exit_px = sl_px
                        exit_reason = "SL"
                        exit_time = times[j]
                        break
                else:  # SHORT
                    ask_l = b_l + spread
                    ask_h = b_h + spread
                    if ask_h >= sl_px and ask_l <= tp_px:
                        exit_px = tp_px if b_c < b_o else sl_px
                        exit_reason = "TP" if b_c < b_o else "SL"
                        exit_time = times[j]
                        break
                    elif ask_l <= tp_px:
                        exit_px = tp_px
                        exit_reason = "TP"
                        exit_time = times[j]
                        break
                    elif ask_h >= sl_px:
                        exit_px = sl_px
                        exit_reason = "SL"
                        exit_time = times[j]
                        break

            if exit_px is None:
                exit_j = min(i + 8, n - 1)
                exit_px = closes[exit_j] if sig == 1 else closes[exit_j] + spread
                exit_reason = "TIME_STOP"
                exit_time = times[exit_j]
                j = exit_j

            pts_gain = (exit_px - entry_px) if sig == 1 else (entry_px - exit_px)
            # PnL en EUR = (puntos ganados / puntos arriesgados) * riesgo monetario (30.58 EUR)
            pnl_eur = (pts_gain / sl_dist) * risk_eur

            trades.append({
                "entry_time": entry_time,
                "hour_utc": entry_time.hour,
                "minute_utc": entry_time.minute,
                "pnl_eur": pnl_eur,
                "win": pnl_eur > 0,
                "exit_reason": exit_reason,
            })
            i = j + 2
        else:
            i += 1

    df_t = pd.DataFrame(trades)
    if len(df_t) == 0:
        return {"trades": 0, "wr": 0, "pf": 0, "pnl": 0, "max_dd": 0, "df": df_t}

    wins = df_t[df_t["pnl_eur"] > 0]
    losses = df_t[df_t["pnl_eur"] < 0]
    wr = (len(wins) / len(df_t)) * 100.0
    gross_win = wins["pnl_eur"].sum()
    gross_loss = abs(losses["pnl_eur"].sum())
    pf = (gross_win / gross_loss) if gross_loss > 0 else 99.0
    tot_pnl = df_t["pnl_eur"].sum()

    cum = df_t["pnl_eur"].cumsum()
    max_dd = (cum.cummax() - cum).max()

    return {
        "trades": len(df_t),
        "wins": len(wins),
        "losses": len(losses),
        "wr": wr,
        "pf": pf,
        "pnl": tot_pnl,
        "max_dd": max_dd,
        "df": df_t,
    }


def main():
    print("=" * 105)
    print("AUDITORIA FORENSE MULTI-ACTIVO (2022 - 2026): TODOS LOS ACTIVOS DE CARTERA")
    print("Evaluación de Impacto de Opción A1 (Filtro Campana 5 min) y Distribución Horaria")
    print("=" * 105)

    if not mt5.initialize():
        print("ERROR: Fallo al inicializar MetaTrader 5")
        return

    summary_rows = []

    for sym, info in ASSETS_CONFIG.items():
        print(f"\n>>> Cargando datos para {sym} ({info['tf_str']})...")
        df = load_symbol_bars(sym, info["tf"], count=60000)
        if len(df) == 0:
            print(f"Error: sin datos para {sym}")
            continue

        start_date = df.index[0].strftime("%Y-%m-%d")
        end_date = df.index[-1].strftime("%Y-%m-%d")
        print(f"    Barras: {len(df):,d} | Rango: {start_date} a {end_date}")

        # 1. Simulación Baseline
        res_base = simulate_asset(df, info, sym, veto_opening_bell=False)

        # 2. Simulación Opción A1 (Veto Campana de Apertura 5 min)
        res_a1 = simulate_asset(df, info, sym, veto_opening_bell=True)

        summary_rows.append({
            "symbol": sym,
            "tf": info["tf_str"],
            "bars": len(df),
            "trades_base": res_base["trades"],
            "wr_base": res_base["wr"],
            "pf_base": res_base["pf"],
            "pnl_base": res_base["pnl"],
            "dd_base": res_base["max_dd"],
            "trades_a1": res_a1["trades"],
            "wr_a1": res_a1["wr"],
            "pf_a1": res_a1["pf"],
            "pnl_a1": res_a1["pnl"],
            "dd_a1": res_a1["max_dd"],
            "diff_pnl": res_a1["pnl"] - res_base["pnl"],
        })

        # Desglose Horario de este activo
        df_t = res_base["df"]
        if len(df_t) > 0:
            print(f"    Distribución Horaria de Rendimiento para {sym}:")
            print(f"    {'Hora UTC':<10s} | {'Hora CET':<10s} | {'Trades':<8s} | {'Win Rate':<10s} | {'PnL Total':<12s}")
            print("    " + "-" * 55)
            hours_present = sorted(df_t["hour_utc"].unique())
            for h in hours_present:
                sub_h = df_t[df_t["hour_utc"] == h]
                wr_h = sub_h["win"].mean() * 100
                pnl_h = sub_h["pnl_eur"].sum()
                h_cet = (h + 1) % 24
                print(f"    {h:02d}:00 UTC  | {h_cet:02d}:00 CET  | {len(sub_h):<8d} | {wr_h:>6.1f} %   | {pnl_h:>+10.2f} €")

    # Tabla Resumen Comparativa Multi-Activo
    print("\n" + "=" * 120)
    print("TABLA COMPARATIVA GLOBAL MULTI-ACTIVO: BASELINE vs OPCIÓN A1 (VETO CAMPANA 5 MIN)")
    print("=" * 120)
    print(f"{'Activo':<12s} | {'TF':<4s} | {'Trades Base':<11s} | {'WR Base':<8s} | {'PF Base':<8s} | {'PnL Base (EUR)':<15s} | {'Trades A1':<10s} | {'WR A1':<8s} | {'PF A1':<8s} | {'PnL A1 (EUR)':<14s} | {'Diff PnL':<10s}")
    print("-" * 120)

    tot_pnl_base = 0.0
    tot_pnl_a1 = 0.0
    for r in summary_rows:
        tot_pnl_base += r["pnl_base"]
        tot_pnl_a1 += r["pnl_a1"]
        print(
            f"{r['symbol']:<12s} | {r['tf']:<4s} | {r['trades_base']:<11d} | {r['wr_base']:>5.1f} %  | {r['pf_base']:>6.2f} | {r['pnl_base']:>+13.2f} € | {r['trades_a1']:<10d} | {r['wr_a1']:>5.1f} % | {r['pf_a1']:>6.2f} | {r['pnl_a1']:>+12.2f} € | {r['diff_pnl']:>+9.2f} €"
        )
    print("-" * 120)
    print(f"{'CARTERA TOTAL':<19s} |                         | {tot_pnl_base:>+13.2f} € |                        | {tot_pnl_a1:>+12.2f} € | {tot_pnl_a1 - tot_pnl_base:>+9.2f} €")
    print("=" * 120)


if __name__ == "__main__":
    main()
