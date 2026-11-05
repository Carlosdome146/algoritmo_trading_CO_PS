#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Auditoria Forense Cuantitativa: Cooldown Bars y RiskPause.

Responde numericamente y con datos historicos a:
1. Impacto de variar cooldown_bars (0, 1, 2, 3, 4) en Win Rate, PF, PnL y Drawdown.
2. Analisis de autocorrelacion de rachas: Que probabilidad hay de un 3er fallo tras 2 fallos consecutivos?
3. Comparativa de RiskPause: Permitir 1 vs 2 vs 3 vs 4 vs Ilimitados fallos al dia.
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

from trading_v2.strategies.micro_scalping import SniperScalpConfig, generate_sniper_signals


def load_bars_chunked(symbol: str, tf: int) -> pd.DataFrame:
    d_to = datetime(2026, 11, 5, tzinfo=timezone.utc)
    chunks = []
    for y in [2022, 2023, 2024, 2025, 2026]:
        y_from = datetime(y, 1, 1, tzinfo=timezone.utc)
        y_to = datetime(y, 12, 31, 23, 59, tzinfo=timezone.utc) if y < 2026 else d_to
        r = mt5.copy_rates_range(symbol, tf, y_from, y_to)
        if r is not None and len(r) > 0:
            df_c = pd.DataFrame(r)
            df_c["time"] = pd.to_datetime(df_c["time"], unit="s", utc=True)
            df_c.set_index("time", inplace=True)
            df_c.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "tick_volume": "Volume"}, inplace=True)
            chunks.append(df_c)
    if chunks:
        full_df = pd.concat(chunks)
        return full_df[~full_df.index.duplicated(keep="first")].sort_index()
    return pd.DataFrame()


def backtest_cooldown(df: pd.DataFrame, symbol: str, cooldown_val: int, spread: float, tgt_u: float, sl_u: float, is_fx: bool = False) -> dict:
    if df.empty:
        return {}

    unit_m = 0.00010 if is_fx else 1.0
    tp_dist = tgt_u * unit_m
    sl_dist = sl_u * unit_m
    risk_eur = 45.0

    cfg = SniperScalpConfig(
        symbol=symbol,
        target_units=tgt_u,
        stop_units=sl_u,
        session_start_h=7 if not is_fx else 6,
        session_end_h=17 if not is_fx else 20,
        min_rejection_wick=0.35,
        cooldown_bars=max(1, cooldown_val),
        use_h1_filter=True,
        use_ker_filter=True,
        max_ker_trend=0.45,
        allow_short=True,
    )
    sig_df = generate_sniper_signals(df, cfg)
    signals = sig_df["signal"].to_numpy()

    times = df.index
    opens = df["Open"].to_numpy()
    highs = df["High"].to_numpy()
    lows = df["Low"].to_numpy()
    closes = df["Close"].to_numpy()
    n = len(df)

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

            exit_price = None
            exit_reason = None
            exit_time = None

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
                else:
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
                exit_reason = "TIME"
                exit_time = times[j_end]

            p_delta = (exit_price - entry_price) if sig == 1 else (entry_price - exit_price)
            pnl_eur = (p_delta / sl_dist) * risk_eur

            trades.append({
                "entry_time": entry_time,
                "exit_time": exit_time,
                "date": entry_time.date(),
                "pnl_eur": pnl_eur,
                "win": 1 if pnl_eur > 0 else 0,
                "exit_reason": exit_reason,
            })
            i = j + (cooldown_val if cooldown_val > 0 else 0)
        else:
            i += 1

    df_t = pd.DataFrame(trades)
    if df_t.empty:
        return {"trades": 0, "wr": 0, "pf": 0, "pnl": 0, "max_dd": 0, "df_t": pd.DataFrame()}

    wins = df_t[df_t["win"] == 1]
    losses = df_t[df_t["win"] == 0]
    n_t = len(df_t)
    wr = (len(wins) / n_t) * 100
    gp = wins["pnl_eur"].sum()
    gl = abs(losses["pnl_eur"].sum()) if len(losses) > 0 else 1e-6
    pf = gp / gl
    pnl = df_t["pnl_eur"].sum()
    cum = df_t["pnl_eur"].cumsum()
    max_dd = (cum.cummax() - cum).max()

    return {
        "cooldown": cooldown_val,
        "trades": n_t,
        "wr": wr,
        "pf": pf,
        "pnl": pnl,
        "max_dd": max_dd,
        "df_t": df_t,
    }


def analyze_riskpause_limits(df_trades: pd.DataFrame, max_daily_losses_list: list[int | None]) -> list[dict]:
    results = []

    for max_l in max_daily_losses_list:
        filtered_trades = []
        days = df_trades.groupby("date")

        for d, day_df in days:
            daily_losses = 0
            for _, tr in day_df.iterrows():
                if max_l is not None and daily_losses >= max_l:
                    continue
                filtered_trades.append(tr)
                if tr["win"] == 0:
                    daily_losses += 1

        sub_df = pd.DataFrame(filtered_trades)
        if sub_df.empty:
            continue
        wins = sub_df[sub_df["win"] == 1]
        losses = sub_df[sub_df["win"] == 0]
        n_t = len(sub_df)
        wr = (len(wins) / n_t) * 100
        gp = wins["pnl_eur"].sum()
        gl = abs(losses["pnl_eur"].sum()) if len(losses) > 0 else 1e-6
        pf = gp / gl
        pnl = sub_df["pnl_eur"].sum()
        cum = sub_df["pnl_eur"].cumsum()
        max_dd = (cum.cummax() - cum).max()

        daily_pnls = sub_df.groupby("date")["pnl_eur"].sum()
        worst_day = daily_pnls.min()

        results.append({
            "max_daily_losses": f"Max {max_l} fallos/dia" if max_l is not None else "Sin Limite (Infinito)",
            "trades": n_t,
            "wr": wr,
            "pf": pf,
            "pnl": pnl,
            "max_dd": max_dd,
            "worst_day": worst_day,
        })
    return results


def analyze_conditional_loss_probability(df_trades: pd.DataFrame) -> dict:
    """Calcula la probabilidad condicional de perder tras 1 fallo y tras 2 fallos consecutivos."""
    wins = df_trades["win"].to_numpy()
    n = len(wins)
    
    total_losses = 0
    loss_after_1_loss = 0
    total_after_1_loss = 0
    loss_after_2_losses = 0
    total_after_2_losses = 0

    for i in range(1, n):
        if wins[i-1] == 0:
            total_after_1_loss += 1
            if wins[i] == 0:
                loss_after_1_loss += 1

    for i in range(2, n):
        if wins[i-1] == 0 and wins[i-2] == 0:
            total_after_2_losses += 1
            if wins[i] == 0:
                loss_after_2_losses += 1

    base_loss_rate = (1.0 - wins.mean()) * 100
    prob_after_1 = (loss_after_1_loss / total_after_1_loss * 100) if total_after_1_loss > 0 else 0
    prob_after_2 = (loss_after_2_losses / total_after_2_losses * 100) if total_after_2_losses > 0 else 0

    return {
        "base_loss_rate": base_loss_rate,
        "prob_after_1": prob_after_1,
        "prob_after_2": prob_after_2,
        "n_after_2": total_after_2_losses,
        "losses_after_2": loss_after_2_losses,
    }


def main():
    mt5.initialize()
    print("=" * 85)
    print("AUDITORIA FORENSE CUANTITATIVA: COOLDOWN BARS Y RISKPAUSE (2022 - 2026)")
    print("=" * 85)

    # 1. GERMANY40
    print("\n--- EXPERIMENTO 1: IMPACTO DE COOLDOWN BARS EN GERMANY40 M30 ---")
    df_dax = load_bars_chunked("GERMANY40", mt5.TIMEFRAME_M30)
    print(f"Barras M30 cargadas: {len(df_dax)}")
    print(f"{'Cooldown':<20s} | {'Trades':<8s} | {'Win Rate':<10s} | {'PF':<8s} | {'PnL Total (EUR)':<18s} | {'Max DD (EUR)':<14s}")
    print("-" * 85)
    
    cd_results_dax = {}
    for cd in [0, 1, 2, 3, 4, 6]:
        r = backtest_cooldown(df_dax, "GERMANY40", cd, spread=1.2, tgt_u=22.0, sl_u=35.0, is_fx=False)
        cd_results_dax[cd] = r
        lbl = f"{cd} barras ({cd*30} min)" if cd > 0 else "0 barras (Inmediato)"
        print(f"{lbl:<20s} | {r['trades']:<8d} | {r['wr']:<9.1f}% | {r['pf']:<8.2f} | {r['pnl']:<+18.2f} | {r['max_dd']:<14.2f}")

    # 2. EURUSD M15
    print("\n--- EXPERIMENTO 2: IMPACTO DE COOLDOWN BARS EN EURUSD M15 ---")
    df_fx = load_bars_chunked("EURUSD", mt5.TIMEFRAME_M15)
    print(f"Barras M15 cargadas: {len(df_fx)}")
    print(f"{'Cooldown':<20s} | {'Trades':<8s} | {'Win Rate':<10s} | {'PF':<8s} | {'PnL Total (EUR)':<18s} | {'Max DD (EUR)':<14s}")
    print("-" * 85)
    for cd in [0, 1, 2, 3, 4]:
        r_fx = backtest_cooldown(df_fx, "EURUSD", cd, spread=0.00010, tgt_u=3.5, sl_u=5.5, is_fx=True)
        lbl = f"{cd} barras ({cd*15} min)" if cd > 0 else "0 barras (Inmediato)"
        print(f"{lbl:<20s} | {r_fx['trades']:<8d} | {r_fx['wr']:<9.1f}% | {r_fx['pf']:<8.2f} | {r_fx['pnl']:<+18.2f} | {r_fx['max_dd']:<14.2f}")

    # 3. ANALISIS DE AUTOCORRELACION DE FALLOS (PROBABILIDAD CONDICIONAL)
    print("\n" + "=" * 85)
    print("--- EXPERIMENTO 3: AUTOCORRELACION DE RACHAS (CLUSTER DE VOLATILIDAD / REGIMEN) ---")
    print("Es aleatorio un fallo, o tras 2 fallos consecutivos el mercado se vuelve mas hostil?")
    print("=" * 85)
    cond = analyze_conditional_loss_probability(cd_results_dax[0]["df_t"])
    print(f"Probabilidad Incondicional de Fallo (Base):              {cond['base_loss_rate']:.1f}%")
    print(f"Probabilidad de Fallar el Siguiente tras 1 Fallo:         {cond['prob_after_1']:.1f}%")
    print(f"Probabilidad de Fallar el Siguiente tras 2 Fallos Seguidos: {cond['prob_after_2']:.1f}% (Muestra: {cond['n_after_2']} rachas)")

    # 4. AUDITORIA DE RISKPAUSE
    print("\n" + "=" * 85)
    print("--- EXPERIMENTO 4: AUDITORIA DE RISKPAUSE (FRENO DE PERDIDAS DIARIAS) ---")
    print("Comparativa: Operar sin limites vs Frenar a 1, 2, 3 o 4 fallos en el dia")
    print("=" * 85)
    df_raw = cd_results_dax[0]["df_t"]
    rp_results = analyze_riskpause_limits(df_raw, [1, 2, 3, 4, None])
    print(f"{'Regla RiskPause':<24s} | {'Trades':<8s} | {'Win Rate':<10s} | {'PF':<8s} | {'PnL (EUR)':<15s} | {'Max DD':<12s} | {'Peor Dia':<12s}")
    print("-" * 85)
    for res in rp_results:
        print(f"{res['max_daily_losses']:<24s} | {res['trades']:<8d} | {res['wr']:<9.1f}% | {res['pf']:<8.2f} | {res['pnl']:<+15.2f} | {res['max_dd']:<12.2f} | {res['worst_day']:<+12.2f}")


if __name__ == "__main__":
    main()
