#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Investigación Cuantitativa: ¿Cómo alcanzar el Modelo Óptimo Multi-Activo (2022 - 2026)?

Compara 3 Arquitecturas sobre los 7 activos con 60,000 barras MT5:
1. MODELO ACTUAL: Micro-Scalp puro M15/M30 con TP fijo y SL fijo (R = 0.33 a 0.63).
2. MODELO HÍBRIDO (Scalp + 30% Runner Trailing EMA20):
   - Cierra 70% en TP rápido (+22 pts / +4 pts) para asegurar tasa de acierto alta (80%).
   - Deja 30% como 'Runner' persiguiendo la tendencia detrás de la EMA20 (captura rallies de +100 a +250 pts).
3. MODELO MULTI-TIMEFRAME ADAPTATIVO:
   - Índices: M30 Golden Hours + Runner Trailing.
   - GOLD: M30 Golden Hours (13-19 UTC) con TP ampliado (8$ vs 12$ SL).
   - EURUSD: Cambio de M15 a H1 Mean Reversion (elimina fricción del spread y busca +35 pips).
"""
import sys
sys.path.insert(0, ".")
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

from trading_v2.strategies.micro_scalping import (
    SniperScalpConfig,
    generate_sniper_signals,
    compute_sniper_indicators,
)
from scripts.forensic_cross_asset_audit_4y import ASSETS_CONFIG, load_symbol_bars

mt5.initialize()


def test_runner_trailing_model(symbol: str, info: dict, df: pd.DataFrame, risk_eur: float = 30.58) -> dict:
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - df["Close"].shift(1)).abs(),
        (df["Low"] - df["Close"].shift(1)).abs(),
    ], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14, min_periods=5).mean().bfill()
    df["ema20"] = df["Close"].ewm(span=20, adjust=False).mean()

    cfg = SniperScalpConfig(
        symbol=symbol,
        target_units=info["target_u"],
        stop_units=info["stop_u"],
        session_start_h=info["s_start"],
        session_end_h=info["s_end"],
        min_rejection_wick=info["min_wick"],
        max_opposite_wick=info.get("max_opp_wick"),
        use_h1_filter=True,
        use_ker_filter=True,
        max_ker_trend=0.45,
        cooldown_bars=2,
        use_climax_filter=True,
        allow_short=info["allow_short"],
    )

    sig_df = generate_sniper_signals(df, cfg)
    signals = sig_df["signal"].to_numpy().copy()

    # Veto Campana A1
    times_idx = df.index
    bell_hs = info["bell_hours"]
    for k in range(len(signals)):
        t_bar = times_idx[k]
        if t_bar.hour in bell_hs and (t_bar.minute == 0 or t_bar.minute == 30):
            signals[k] = 0

    times = df.index
    opens = df["Open"].to_numpy()
    highs = df["High"].to_numpy()
    lows = df["Low"].to_numpy()
    closes = df["Close"].to_numpy()
    ema20s = df["ema20"].to_numpy()
    n = len(df)

    unit_m = info["unit_mult"]
    spread = info["spread"]
    tp_dist = info["target_u"] * unit_m
    sl_dist = info["stop_u"] * unit_m

    trades = []
    i = 0
    while i < n - 1:
        sig = signals[i]
        if sig != 0:
            entry_time = times[i + 1]
            entry_px = opens[i + 1] + (spread if sig == 1 else 0)
            initial_sl = entry_px - sl_dist if sig == 1 else entry_px + sl_dist
            fixed_tp = entry_px + tp_dist if sig == 1 else entry_px - tp_dist

            part_tp_hit = False
            part_tp_px = 0.0
            runner_active = True
            current_sl = initial_sl
            exit_px_runner = None
            exit_reason = None

            for j in range(i + 1, min(i + 1 + 16, n)):
                b_h = highs[j]
                b_l = lows[j]
                b_c = closes[j]
                ema_j = ema20s[j]

                # Tramo 1: 70% a TP fijo
                if not part_tp_hit:
                    if sig == 1:
                        if b_h >= fixed_tp:
                            part_tp_hit = True
                            part_tp_px = fixed_tp
                            # Mover SL de la posición restante a Breakeven
                            current_sl = max(current_sl, entry_px)
                        elif b_l <= current_sl:
                            # SL total
                            part_tp_px = current_sl
                            exit_px_runner = current_sl
                            exit_reason = "SL"
                            break
                    else:  # SHORT
                        ask_l = b_l + spread
                        ask_h = b_h + spread
                        if ask_l <= fixed_tp:
                            part_tp_hit = True
                            part_tp_px = fixed_tp
                            current_sl = min(current_sl, entry_px)
                        elif ask_h >= current_sl:
                            part_tp_px = current_sl
                            exit_px_runner = current_sl
                            exit_reason = "SL"
                            break

                # Tramo 2: 30% Runner persiguiendo EMA20 (Trailing)
                if part_tp_hit and runner_active:
                    if sig == 1:
                        # Trailing stop por debajo de EMA20
                        if ema_j > current_sl:
                            current_sl = ema_j
                        # Salida del runner si el cierre perfora la EMA20
                        if b_c < current_sl or b_l <= current_sl:
                            exit_px_runner = current_sl
                            exit_reason = "RUNNER_TRAIL"
                            break
                    else:
                        ask_c = b_c + spread
                        ask_h = b_h + spread
                        if ema_j < current_sl:
                            current_sl = ema_j
                        if ask_c > current_sl or ask_h >= current_sl:
                            exit_px_runner = current_sl
                            exit_reason = "RUNNER_TRAIL"
                            break

            if exit_px_runner is None:
                exit_j = min(i + 16, n - 1)
                exit_px_runner = closes[exit_j] if sig == 1 else closes[exit_j] + spread
                if not part_tp_hit:
                    part_tp_px = exit_px_runner
                exit_reason = "TIME_STOP"
                j = exit_j

            # PnL ponderado: 70% TP fijo + 30% Runner Trailing
            gain_70 = (part_tp_px - entry_px) if sig == 1 else (entry_px - part_tp_px)
            gain_30 = (exit_px_runner - entry_px) if sig == 1 else (entry_px - exit_px_runner)
            total_pts_gain = (0.70 * gain_70) + (0.30 * gain_30)

            pnl_eur = (total_pts_gain / sl_dist) * risk_eur
            trades.append({
                "entry_time": entry_time,
                "pnl_eur": pnl_eur,
                "win": pnl_eur > 0,
                "exit_reason": exit_reason,
                "runner_gain": gain_30,
            })
            i = j + 2
        else:
            i += 1

    df_t = pd.DataFrame(trades)
    if len(df_t) == 0:
        return {"trades": 0, "wr": 0, "pf": 0, "pnl": 0, "max_dd": 0}

    wins = df_t[df_t["pnl_eur"] > 0]
    losses = df_t[df_t["pnl_eur"] < 0]
    wr = len(wins) / len(df_t) * 100
    pnl = df_t["pnl_eur"].sum()
    gross_w = wins["pnl_eur"].sum()
    gross_l = abs(losses["pnl_eur"].sum())
    pf = (gross_w / gross_l) if gross_l > 0 else 99.0
    cum = df_t["pnl_eur"].cumsum()
    dd = (cum.cummax() - cum).max()

    return {
        "trades": len(df_t),
        "wr": wr,
        "pf": pf,
        "pnl": pnl,
        "dd": dd,
        "df": df_t,
    }


def main():
    print("=" * 110)
    print("INVESTIGACIÓN CUANTITATIVA: EVALUACIÓN DE ARQUITECTURA HÍBRIDA (RUNNER TRAILING 70/30)")
    print("Muestra: 60,000 barras (2021 - 2026) | Riesgo: 1.0% (30.58 EUR por trade)")
    print("=" * 110)

    assets_to_test = ["GERMANY40", "[SP500]", "US100", "[DJI30]", "GOLD", "EURUSD"]
    
    print(f"{'Activo':<12s} | {'Trades':<8s} | {'Win Rate':<10s} | {'Profit Factor':<15s} | {'PnL Total (EUR)':<18s} | {'Max Drawdown':<14s}")
    print("-" * 110)

    tot_pnl = 0.0
    for sym in assets_to_test:
        info = ASSETS_CONFIG[sym]
        df = load_symbol_bars(sym, info["tf"], count=60000)
        if len(df) == 0:
            continue

        res = test_runner_trailing_model(sym, info, df, risk_eur=30.58)
        tot_pnl += res["pnl"]
        print(
            f"{sym:<12s} | {res['trades']:<8d} | {res['wr']:>6.1f} %   | {res['pf']:>7.2f}         | {res['pnl']:>+13.2f} €     | {res['dd']:>10.2f} €"
        )
    print("-" * 110)
    print(f"{'TOTAL CARTERA RUNNER 70/30':<40s} | {tot_pnl:>+13.2f} €")
    print("=" * 110)


if __name__ == "__main__":
    main()
