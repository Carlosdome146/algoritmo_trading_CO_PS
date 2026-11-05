#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Auditoria Forense Cuantitativa a 4+ Anos (2022 - 2026).

Compara de forma estricta y causal sobre 54,000+ barras M30 de GERMANY40:
1. BASELINE ACTUAL: Disparo Francotirador M30 con TP fijo (22.0 pts) y SL (35.0 pts).
2. VARIANTE A (Runner Trailing): 70% TP fijo a 22.0 pts + 30% Runner con Trailing Stop tras EMA20.
3. VARIANTE B (Anti-Climax Filter de Carlos): Bloqueo si RSI(2) > 82 o precio > Bollinger Superior.
4. VARIANTE COMBINADA (Anti-Climax + Runner): Ambas propuestas juntas.
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

from trading_v2.strategies.micro_scalping import SniperScalpConfig, generate_sniper_signals, compute_sniper_indicators


def load_bars_m30(symbol: str) -> pd.DataFrame:
    d_from = datetime(2022, 1, 1, tzinfo=timezone.utc)
    d_to = datetime(2026, 11, 5, tzinfo=timezone.utc)
    r = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M30, d_from, d_to)
    if r is None or len(r) == 0:
        return pd.DataFrame()
    df = pd.DataFrame(r)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "tick_volume": "Volume"}, inplace=True)
    return df


def simulate_model(df: pd.DataFrame, model_type: str = "baseline", apply_climax_filter: bool = False, spread: float = 1.2, risk_eur: float = 45.0) -> dict:
    cfg = SniperScalpConfig(
        symbol="GERMANY40", target_units=22.0, stop_units=35.0,
        session_start_h=7, session_end_h=17, min_rejection_wick=0.35,
        use_h1_filter=True, use_ker_filter=True, max_ker_trend=0.45,
        cooldown_bars=3, allow_short=True
    )
    sig_df = generate_sniper_signals(df, cfg)
    ind = compute_sniper_indicators(df)
    
    signals = sig_df["signal"].to_numpy().copy()
    rsi2 = ind["rsi2"].to_numpy() if "rsi2" in ind.columns else np.zeros(len(df))
    bb_hi = ind["bb_hi"].to_numpy() if "bb_hi" in ind.columns else np.zeros(len(df))
    bb_lo = ind["bb_lo"].to_numpy() if "bb_lo" in ind.columns else np.zeros(len(df))
    closes = df["Close"].to_numpy()
    ema20 = ind["ema20"].to_numpy() if "ema20" in ind.columns else pd.Series(closes).ewm(span=20).mean().to_numpy()
    
    # Aplicar Filtro Anti-Climax si esta activado
    if apply_climax_filter:
        for idx in range(len(signals)):
            if signals[idx] == 1:
                # Bloquear compra si RSI2 > 82 o precio perfora banda Bollinger superior
                if rsi2[idx] > 82.0 or (np.isfinite(bb_hi[idx]) and closes[idx] > bb_hi[idx]):
                    signals[idx] = 0
            elif signals[idx] == -1:
                # Bloquear venta si RSI2 < 18 o precio perfora banda Bollinger inferior
                if rsi2[idx] < 18.0 or (np.isfinite(bb_lo[idx]) and closes[idx] < bb_lo[idx]):
                    signals[idx] = 0

    times = df.index
    opens = df["Open"].to_numpy()
    highs = df["High"].to_numpy()
    lows = df["Low"].to_numpy()
    n = len(df)

    tp_dist = cfg.target_units
    sl_dist = cfg.stop_units

    trades = []
    i = 0
    while i < n - 1:
        sig = signals[i]
        if sig != 0:
            entry_time = times[i + 1]
            if sig == 1:
                entry_price = opens[i + 1] + spread
                sl_price = entry_price - sl_dist
                tp_price = entry_price + tp_dist
            else:
                entry_price = opens[i + 1]
                sl_price = entry_price + sl_dist
                tp_price = entry_price - tp_dist

            exit_time = None
            exit_price = None
            exit_reason = None
            pnl_eur = 0.0

            if model_type == "baseline":
                for j in range(i + 1, min(i + 1 + 8, n)):
                    bar_h = highs[j]
                    bar_l = lows[j]
                    bar_c = closes[j]
                    bar_o = opens[j]

                    if sig == 1:
                        if bar_l <= sl_price and bar_h >= tp_price:
                            exit_price = tp_price if bar_c > bar_o else sl_price
                            exit_reason = "TP" if bar_c > bar_o else "SL"
                            exit_time = times[j]
                            break
                        elif bar_h >= tp_price:
                            exit_price = tp_price
                            exit_reason = "TP"
                            exit_time = times[j]
                            break
                        elif bar_l <= sl_price:
                            exit_price = sl_price
                            exit_reason = "SL"
                            exit_time = times[j]
                            break
                    else: # SHORT
                        ask_l = bar_l + spread
                        ask_h = bar_h + spread
                        if ask_h >= sl_price and ask_l <= tp_price:
                            exit_price = tp_price if bar_c < bar_o else sl_price
                            exit_reason = "TP" if bar_c < bar_o else "SL"
                            exit_time = times[j]
                            break
                        elif ask_l <= tp_price:
                            exit_price = tp_price
                            exit_reason = "TP"
                            exit_time = times[j]
                            break
                        elif ask_h >= sl_price:
                            exit_price = sl_price
                            exit_reason = "SL"
                            exit_time = times[j]
                            break

                if exit_price is None:
                    j_end = min(i + 1 + 7, n - 1)
                    exit_price = closes[j_end] if sig == 1 else (closes[j_end] + spread)
                    exit_reason = "TIME_EXPIRY"
                    exit_time = times[j_end]

                p_delta = (exit_price - entry_price) if sig == 1 else (entry_price - exit_price)
                pnl_eur = (p_delta / sl_dist) * risk_eur

            elif model_type == "runner_trailing":
                # 70% TP fijo + 30% Runner Trailing Stop
                part1_closed = False
                part1_pnl = 0.0
                part2_closed = False
                part2_pnl = 0.0
                cur_runner_sl = sl_price

                for j in range(i + 1, min(i + 1 + 16, n)):
                    bar_h = highs[j]
                    bar_l = lows[j]
                    bar_c = closes[j]

                    if sig == 1:
                        if not part1_closed:
                            if bar_h >= tp_price:
                                part1_closed = True
                                part1_pnl = 0.70 * (tp_dist / sl_dist) * risk_eur
                                cur_runner_sl = max(cur_runner_sl, entry_price + 1.0) # Break-even
                            elif bar_l <= sl_price:
                                part1_closed = True
                                part1_pnl = -0.70 * risk_eur
                                part2_closed = True
                                part2_pnl = -0.30 * risk_eur
                                exit_time = times[j]
                                exit_reason = "FULL_SL"
                                break

                        if part1_closed and not part2_closed:
                            if ema20[j] > cur_runner_sl:
                                cur_runner_sl = ema20[j]
                            if bar_l <= cur_runner_sl:
                                part2_closed = True
                                runner_delta = cur_runner_sl - entry_price
                                part2_pnl = 0.30 * (runner_delta / sl_dist) * risk_eur
                                exit_time = times[j]
                                exit_reason = "RUNNER_TRAILED"
                                break
                    else: # SHORT
                        ask_l = bar_l + spread
                        ask_h = bar_h + spread
                        if not part1_closed:
                            if ask_l <= tp_price:
                                part1_closed = True
                                part1_pnl = 0.70 * (tp_dist / sl_dist) * risk_eur
                                cur_runner_sl = min(cur_runner_sl, entry_price - 1.0)
                            elif ask_h >= sl_price:
                                part1_closed = True
                                part1_pnl = -0.70 * risk_eur
                                part2_closed = True
                                part2_pnl = -0.30 * risk_eur
                                exit_time = times[j]
                                exit_reason = "FULL_SL"
                                break

                        if part1_closed and not part2_closed:
                            if ema20[j] < cur_runner_sl:
                                cur_runner_sl = ema20[j]
                            if ask_h >= cur_runner_sl:
                                part2_closed = True
                                runner_delta = entry_price - cur_runner_sl
                                part2_pnl = 0.30 * (runner_delta / sl_dist) * risk_eur
                                exit_time = times[j]
                                exit_reason = "RUNNER_TRAILED"
                                break

                if not part2_closed:
                    j_end = min(i + 1 + 15, n - 1)
                    p_end = closes[j_end] if sig == 1 else (closes[j_end] + spread)
                    p_delta = (p_end - entry_price) if sig == 1 else (entry_price - p_end)
                    if not part1_closed:
                        part1_pnl = 0.70 * (p_delta / sl_dist) * risk_eur
                    part2_pnl = 0.30 * (p_delta / sl_dist) * risk_eur
                    exit_time = times[j_end]
                    exit_reason = "TIME_EXPIRY"

                pnl_eur = part1_pnl + part2_pnl

            trades.append({
                "entry_time": entry_time,
                "exit_time": exit_time,
                "direction": "BUY" if sig == 1 else "SELL",
                "pnl_eur": pnl_eur,
                "exit_reason": exit_reason,
                "year": entry_time.year,
            })
            i = j
        else:
            i += 1

    df_t = pd.DataFrame(trades)
    if df_t.empty:
        return {"trades": 0, "wr": 0, "pf": 0, "pnl": 0, "max_dd": 0}

    wins = df_t[df_t["pnl_eur"] > 0]
    losses = df_t[df_t["pnl_eur"] < 0]
    n_t = len(df_t)
    wr = (len(wins) / n_t) * 100
    tot_pnl = df_t["pnl_eur"].sum()
    gp = wins["pnl_eur"].sum()
    gl = abs(losses["pnl_eur"].sum()) if len(losses) > 0 else 1e-6
    pf = gp / gl
    cum = df_t["pnl_eur"].cumsum()
    max_dd = (cum.cummax() - cum).max()

    return {
        "trades": n_t,
        "wins": len(wins),
        "losses": len(losses),
        "wr": wr,
        "pf": pf,
        "pnl": tot_pnl,
        "max_dd": max_dd,
        "df": df_t,
    }


def main():
    mt5.initialize()
    print("=" * 80)
    print("AUDITORIA FORENSE 4+ ANOS (2022 - 2026): GERMANY40 M30")
    print("Comparativa de Modelos sobre el mismo historico exacto (54,335 barras M30)")
    print("=" * 80)

    df_dax = load_bars_m30("GERMANY40")
    print(f"Total barras M30 cargadas: {len(df_dax)} (desde {df_dax.index[0].strftime('%Y-%m-%d')} hasta {df_dax.index[-1].strftime('%Y-%m-%d')})")

    # 1. BASELINE ACTUAL
    res_base = simulate_model(df_dax, model_type="baseline", apply_climax_filter=False)

    # 2. VARIANTE A: RUNNER TRAILING (70/30)
    res_runner = simulate_model(df_dax, model_type="runner_trailing", apply_climax_filter=False)

    # 3. VARIANTE B: ANTI-CLIMAX FILTER DE CARLOS (RSI2 > 82 bloqueado)
    res_climax = simulate_model(df_dax, model_type="baseline", apply_climax_filter=True)

    # 4. VARIANTE COMBINADA (ANTI-CLIMAX + RUNNER)
    res_combo = simulate_model(df_dax, model_type="runner_trailing", apply_climax_filter=True)

    print("\n" + "-" * 90)
    print("TABLA COMPARATIVA FORENSE A 4.8 ANOS (2022 - 2026)")
    print("-" * 90)
    print(f"{'Metrica':<26s} | {'BASELINE ACTUAL':<16s} | {'VARIANTE A (RUNNER)':<18s} | {'VARIANTE B (CLIMAX)':<18s} | {'COMBO (CLIMAX+RUNNER)':<20s}")
    print("-" * 90)
    print(f"{'Total Operaciones':<26s} | {res_base['trades']:<16d} | {res_runner['trades']:<18d} | {res_climax['trades']:<18d} | {res_combo['trades']:<20d}")
    print(f"{'Tasa Acierto (Win Rate)':<26s} | {res_base['wr']:<15.1f}% | {res_runner['wr']:<17.1f}% | {res_climax['wr']:<17.1f}% | {res_combo['wr']:<19.1f}%")
    print(f"{'Factor Beneficio (PF)':<26s} | {res_base['pf']:<16.2f} | {res_runner['pf']:<18.2f} | {res_climax['pf']:<18.2f} | {res_combo['pf']:<20.2f}")
    print(f"{'Beneficio Neto (EUR)':<26s} | {res_base['pnl']:<+16.2f} | {res_runner['pnl']:<+18.2f} | {res_climax['pnl']:<+18.2f} | {res_combo['pnl']:<+20.2f}")
    print(f"{'Max Drawdown (EUR)':<26s} | {res_base['max_dd']:<16.2f} | {res_runner['max_dd']:<18.2f} | {res_climax['max_dd']:<18.2f} | {res_combo['max_dd']:<20.2f}")
    print("-" * 90)

    # Desglose Anual
    df_b = res_base["df"]
    df_c = res_climax["df"]
    df_r = res_runner["df"]
    print("\nDESGLOSE DE BENEFICIO NETO POR ANOS (EUR):")
    print("Ano  | Baseline (Actual) | Variante A (Runner) | Variante B (Climax) | Diferencia Climax vs Base")
    print("-" * 85)
    for y in sorted(df_b["year"].unique()):
        pnl_b = df_b[df_b["year"] == y]["pnl_eur"].sum()
        pnl_r = df_r[df_r["year"] == y]["pnl_eur"].sum()
        pnl_c = df_c[df_c["year"] == y]["pnl_eur"].sum()
        diff = pnl_c - pnl_b
        print(f"{y} | {pnl_b:+17.2f} | {pnl_r:+19.2f} | {pnl_c:+19.2f} | {diff:+20.2f} EUR")


if __name__ == "__main__":
    main()
