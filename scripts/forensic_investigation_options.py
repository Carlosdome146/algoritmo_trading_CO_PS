#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Auditoría Forense Cuantitativa: Evaluación de Opciones de Control de Riesgo (2022 - 2026).

Compara con rigor matemático sobre 54,000+ barras M30 de GERMANY40:
- Opción A: Filtros de Apertura / Timing de Sesión:
    A0: Baseline (Inicio 07:00 UTC / 08:00 CET, sin filtro de campana)
    A1: Filtro de Campana de Apertura (Veto a disparos en la apertura exacta de las 07:00 UTC / 08:00 CET)
    A2: Retraso a Apertura de Contado Xetra (Inicio 08:00 UTC / 09:00 CET - Commit de Carlos)
- Opción B: Stop Loss Adaptativo a la Volatilidad (ATR M30):
    B0: Stop rígido de 35.0 pts (Baseline)
    B1: SL Adaptativo Leve: max(35.0, 1.0 * ATR14_M30) con TP fijo 22.0 pts
    B2: SL Adaptativo Medio: max(35.0, 1.25 * ATR14_M30) con TP fijo 22.0 pts
    B3: SL Adaptativo Amplio: max(45.0, 1.30 * ATR14_M30) con TP proporcional max(22.0, 0.75 * ATR14_M30)
- Opciones Combinadas (A + B).
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


def load_dax_m30() -> pd.DataFrame:
    if not mt5.initialize():
        raise RuntimeError("No se pudo inicializar MetaTrader 5")
    d_from = datetime(2022, 1, 1, tzinfo=timezone.utc)
    d_to = datetime(2026, 11, 7, tzinfo=timezone.utc)
    rates = mt5.copy_rates_range("GERMANY40", mt5.TIMEFRAME_M30, d_from, d_to)
    if rates is None or len(rates) == 0:
        raise RuntimeError("No se pudieron cargar datos M30 de GERMANY40")
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    df.rename(
        columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "tick_volume": "Volume"},
        inplace=True,
    )
    # Cálculo de ATR14 causal
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - df["Close"].shift(1)).abs(),
        (df["Low"] - df["Close"].shift(1)).abs(),
    ], axis=1).max(axis=1)
    df["atr14"] = tr.rolling(14, min_periods=5).mean().bfill()
    return df


def simulate_sniper_variant(
    df: pd.DataFrame,
    session_start_h: int = 7,
    veto_opening_bell_0700: bool = False,
    sl_mode: str = "fixed_35",  # "fixed_35", "atr_1_0", "atr_1_25", "atr_proportional"
    apply_climax_filter: bool = True,
    risk_eur: float = 30.58,  # 1.0% de 3058.12 EUR
    spread: float = 1.2,
) -> dict:
    cfg = SniperScalpConfig(
        symbol="GERMANY40",
        target_units=22.0,
        stop_units=35.0,
        session_start_h=session_start_h,
        session_end_h=17,
        min_rejection_wick=0.35,
        use_h1_filter=True,
        use_ker_filter=True,
        max_ker_trend=0.45,
        cooldown_bars=2,
        use_climax_filter=apply_climax_filter,
        allow_short=True,
    )

    sig_df = generate_sniper_signals(df, cfg)
    signals = sig_df["signal"].to_numpy().copy()

    # Veto de campana de apertura (07:00 UTC / 08:00 CET)
    if veto_opening_bell_0700:
        times_idx = df.index
        for k in range(len(signals)):
            # Si la barra que da señal termina a las 07:00 UTC, la entrada se produciría a las 07:00:00 UTC
            # O si la barra es la de las 07:00 UTC
            t_bar = times_idx[k]
            if t_bar.hour == 6 and t_bar.minute == 30:  # Cierre a las 07:00:00 UTC
                signals[k] = 0
            elif t_bar.hour == 7 and t_bar.minute == 0:  # Barra de apertura
                signals[k] = 0

    times = df.index
    opens = df["Open"].to_numpy()
    highs = df["High"].to_numpy()
    lows = df["Low"].to_numpy()
    closes = df["Close"].to_numpy()
    atrs = df["atr14"].to_numpy()
    n = len(df)

    trades = []
    i = 0
    while i < n - 1:
        sig = signals[i]
        if sig != 0:
            entry_time = times[i + 1]
            atr_i = atrs[i]

            # Determinación de Stop Loss y Take Profit según sl_mode
            if sl_mode == "fixed_35":
                sl_pts = 35.0
                tp_pts = 22.0
            elif sl_mode == "atr_1_0":
                sl_pts = max(35.0, 1.0 * atr_i)
                tp_pts = 22.0
            elif sl_mode == "atr_1_25":
                sl_pts = max(35.0, 1.25 * atr_i)
                tp_pts = 22.0
            elif sl_mode == "atr_proportional":
                sl_pts = max(40.0, 1.25 * atr_i)
                tp_pts = max(22.0, 0.75 * atr_i)
            elif sl_mode == "atr_wide":
                sl_pts = max(45.0, 1.40 * atr_i)
                tp_pts = max(25.0, 0.85 * atr_i)
            else:
                sl_pts = 35.0
                tp_pts = 22.0

            if sig == 1:
                entry_px = opens[i + 1] + spread
                sl_px = entry_px - sl_pts
                tp_px = entry_px + tp_pts
            else:
                entry_px = opens[i + 1]
                sl_px = entry_px + sl_pts
                tp_px = entry_px - tp_pts

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
                # Time stop tras 8 barras
                exit_j = min(i + 8, n - 1)
                exit_px = closes[exit_j] if sig == 1 else closes[exit_j] + spread
                exit_reason = "TIME_STOP"
                exit_time = times[exit_j]
                j = exit_j

            # Cálculo estricto de PnL en EUR (Riesgo monetario constante del 1% = 30.58 EUR)
            # PnL = (puntos ganados / puntos arriesgados) * risk_eur
            pts_gain = (exit_px - entry_px) if sig == 1 else (entry_px - exit_px)
            pnl_eur = (pts_gain / sl_pts) * risk_eur

            trades.append({
                "entry_time": entry_time,
                "exit_time": exit_time,
                "sig": sig,
                "entry_px": entry_px,
                "exit_px": exit_px,
                "sl_pts": sl_pts,
                "tp_pts": tp_pts,
                "atr": atr_i,
                "exit_reason": exit_reason,
                "pts_gain": pts_gain,
                "pnl_eur": pnl_eur,
                "year": entry_time.year,
            })

            # Avanzamos respetando cooldown
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
    cummax = cum.cummax()
    max_dd = (cummax - cum).max()

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
    print("=" * 95)
    print("AUDITORIA FORENSE 4+ ANOS (2022 - 2026): GERMANY40 M30")
    print("Evaluación de Filtros de Apertura vs Stop Loss Adaptativo vs Baseline (1.0% Riesgo = 30.58 EUR)")
    print("=" * 95)

    df_dax = load_dax_m30()
    print(f"Total barras M30 cargadas: {len(df_dax)} (desde {df_dax.index[0].strftime('%Y-%m-%d')} hasta {df_dax.index[-1].strftime('%Y-%m-%d')})\n")

    variants = [
        # (Nombre, start_h, veto_bell_0700, sl_mode)
        ("1. BASELINE ACTUAL (08:00 CET, SL Fijo 35)", 7, False, "fixed_35"),
        ("2. OPCION A1: Veto Campana 08:00 CET (SL Fijo 35)", 7, True, "fixed_35"),
        ("3. OPCION A2: Inicio 09:00 CET Xetra (Commit Carlos)", 8, False, "fixed_35"),
        ("4. OPCION B1: SL Adaptativo Leve (max 35, 1.0*ATR)", 7, False, "atr_1_0"),
        ("5. OPCION B2: SL Adaptativo Medio (max 35, 1.25*ATR)", 7, False, "atr_1_25"),
        ("6. OPCION B3: SL Proporcional (max 40, 1.25*ATR, TP prop)", 7, False, "atr_proportional"),
        ("7. COMBO A1 + B2 (Veto Campana 08:00 + SL 1.25*ATR)", 7, True, "atr_1_25"),
        ("8. COMBO A1 + B3 (Veto Campana 08:00 + SL Proporcional)", 7, True, "atr_proportional"),
        ("9. COMBO A2 + B2 (Inicio 09:00 CET + SL 1.25*ATR)", 8, False, "atr_1_25"),
        ("10. COMBO A2 + B3 (Inicio 09:00 CET + SL Proporcional)", 8, False, "atr_proportional"),
    ]

    results = []
    for label, s_h, v_bell, sl_m in variants:
        res = simulate_sniper_variant(
            df_dax,
            session_start_h=s_h,
            veto_opening_bell_0700=v_bell,
            sl_mode=sl_m,
            apply_climax_filter=True,
            risk_eur=30.58,
        )
        results.append((label, res))

    print("-" * 115)
    print(f"{'Variante Evaluada':<44s} | {'Trades':<7s} | {'Win Rate':<9s} | {'PF':<6s} | {'PnL Total':<12s} | {'Max DD':<10s} | {'PnL/DD':<7s}")
    print("-" * 115)
    for label, res in results:
        pnl_dd = (res["pnl"] / res["max_dd"]) if res["max_dd"] > 0 else 0
        print(
            f"{label:<44s} | {res['trades']:<7d} | {res['wr']:>6.1f} %  | {res['pf']:>5.2f} | {res['pnl']:>+10.2f} € | {res['max_dd']:>8.2f} € | {pnl_dd:>6.2f}"
        )
    print("-" * 115)

    # Desglose Anual de las variantes clave
    key_indices = [0, 1, 2, 4, 6, 7, 8, 9]
    years = [2022, 2023, 2024, 2025, 2026]
    print("\n" + "=" * 115)
    print("DESGLOSE ANUAL DE BENEFICIO NETO (EUR) POR MODELO:")
    print("=" * 115)
    header = f"{'Ano':<6s}"
    for idx in [0, 1, 2, 4, 6, 7]:
        short_name = results[idx][0].split(":")[0]
        header += f" | {short_name:<14s}"
    print(header)
    print("-" * 115)

    for y in years:
        row = f"{y:<6d}"
        for idx in [0, 1, 2, 4, 6, 7]:
            df_res = results[idx][1]["df"]
            pnl_y = df_res[df_res["year"] == y]["pnl_eur"].sum() if len(df_res) > 0 else 0.0
            row += f" | {pnl_y:>+12.2f} €"
        print(row)
    print("-" * 115)

    # Autopsia específica de la operación del viernes 2026-11-06 08:00 CET
    print("\n" + "=" * 95)
    print("AUTOPSIA FORENSE ESPECÍFICA: Veda / Operación del Viernes 2026-11-06 08:00 CET")
    print("=" * 95)
    for label, res in results:
        df_res = res["df"]
        if len(df_res) == 0:
            continue
        fri_trade = df_res[df_res["entry_time"].dt.strftime("%Y-%m-%d") == "2026-11-06"]
        if len(fri_trade) > 0:
            row = fri_trade.iloc[0]
            print(f"- {label:<44s}: DISPARÓ a las {row['entry_time'].strftime('%H:%M')} UTC | SL={row['sl_pts']:.1f} pts, TP={row['tp_pts']:.1f} pts -> {row['exit_reason']} | PnL: {row['pnl_eur']:+.2f} €")
        else:
            print(f"- {label:<44s}: NO OPERÓ (Filtrado / Veto preventivo)")


if __name__ == "__main__":
    main()
