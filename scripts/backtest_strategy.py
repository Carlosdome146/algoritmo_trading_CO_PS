#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Runner Universal de Backtesting Intradía (M15 / M30) — Filtro Estricto de Carlos.

Estándares del sistema:
1. Win Rate >= 70.0%
2. Max Drawdown < 5.0%
3. N >= 100 operaciones en datos históricos (hasta 8.5 años MT5)
4. Expectativa matemática neta positiva: Profit Factor > 1.25, E[R] > 0
5. Descuento causal estricto de spread y comisión en cada entrada/salida

Si la estrategia no cumple todos los requisitos, se DESCARTA automáticamente
con el diagnóstico exacto de por qué no supera el filtro.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import MetaTrader5 as mt5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trading_v2.backtesting.intraday_engine import (
    wilson_lower_bound,
    POINT,
    COST_PER_LOT,
    SESSION_UTC,
    CAPITAL_BASE,
)

DASHBOARD_MD_PATH = Path(__file__).resolve().parents[1] / "CUADRO_ESTRATEGIAS_INTRADIA.md"
RESULTS_JSON_PATH = Path(__file__).resolve().parents[1] / "intraday_backtest_results.json"


def fetch_symbol_bars(symbol: str, timeframe: int, count: int = 99999) -> pd.DataFrame:
    """Descarga hasta 99.999 barras reales directamente de MT5 con spreads reales."""
    if not mt5.initialize():
        raise RuntimeError(f"No se pudo conectar a MT5: {mt5.last_error()}")
    mt5.symbol_select(symbol, True)
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None or len(rates) == 0:
        raise ValueError(f"Sin datos en MT5 para el activo: {symbol}")
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    df.sort_index(inplace=True)
    df = df[~df.index.duplicated(keep="first")]
    df.rename(columns={
        "open": "Open", "high": "High", "low": "Low", "close": "Close",
        "tick_volume": "TickVolume", "spread": "Spread"
    }, inplace=True)
    return df


def calculate_intraday_features(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula indicadores técnicos de alta resolución sin sesgo lookahead."""
    out = df.copy()
    c, h, l, o = out["Close"], out["High"], out["Low"], out["Open"]

    # ATR(14)
    prev_c = c.shift(1)
    tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    out["atr14"] = tr.rolling(14, min_periods=5).mean()

    # RSI(2) y RSI(14)
    delta = c.diff()
    up2 = delta.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
    dn2 = (-delta.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    out["rsi2"] = (100 - 100 / (1 + up2 / dn2.replace(0, np.nan))).fillna(50.0)

    up14 = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    dn14 = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    out["rsi14"] = (100 - 100 / (1 + up14 / dn14.replace(0, np.nan))).fillna(50.0)

    # Medias Móviles
    out["sma20"] = c.rolling(20, min_periods=10).mean()
    out["sma50"] = c.rolling(50, min_periods=20).mean()
    out["sma200"] = c.rolling(200, min_periods=50).mean()
    out["ema9"] = c.ewm(span=9, adjust=False).mean()
    out["ema20"] = c.ewm(span=20, adjust=False).mean()
    out["ema50"] = c.ewm(span=50, adjust=False).mean()

    # Bandas de Bollinger (20 periodos, 2.0 sigma)
    std20 = c.rolling(20, min_periods=10).std(ddof=0)
    out["bb_up"] = out["sma20"] + 2.0 * std20
    out["bb_lo"] = out["sma20"] - 2.0 * std20

    # Mechas y CLV
    rng = (h - l).replace(0, np.nan)
    out["clv"] = ((c - l) / rng).fillna(0.5)
    out["lower_wick"] = ((np.minimum(o, c) - l) / rng).fillna(0.0)
    out["upper_wick"] = ((h - np.maximum(o, c)) / rng).fillna(0.0)

    # Extremos de la última hora (4 barras M15 o 2 barras M30)
    out["recent_high"] = h.shift(1).rolling(4, min_periods=2).max()
    out["recent_low"] = l.shift(1).rolling(4, min_periods=2).min()

    # Volumen Relativo
    vol = out["TickVolume"].astype(float)
    out["rvol"] = vol / vol.rolling(20, min_periods=5).mean().replace(0, np.nan)

    out["hour_utc"] = out.index.hour
    out["weekday"] = out.index.weekday
    return out


def simulate_backtest(
    df: pd.DataFrame,
    symbol: str,
    signals: np.ndarray,
    stop_atr: float = 1.5,
    tp_atr: float = 1.0,
    dynamic_exit_ema: int | None = None,
    dynamic_exit_rsi: float | None = None,
    use_breakeven: bool = True,
    be_trigger_atr: float = 0.40,
    be_lock_atr: float = 0.05,
    max_holding_bars: int = 16,
    session_start_h: int = 7,
    session_end_h: int = 17,
) -> dict:
    """Simulación causal estricta con comisiones y spread real en cada barra."""
    point = POINT.get(symbol, 0.01)
    comm = COST_PER_LOT.get(symbol, 0.0)

    c = df["Close"].to_numpy(dtype=float)
    o = df["Open"].to_numpy(dtype=float)
    h = df["High"].to_numpy(dtype=float)
    l = df["Low"].to_numpy(dtype=float)
    spr = df["Spread"].to_numpy(dtype=float) * point
    atr = df["atr14"].to_numpy(dtype=float)
    hours = df["hour_utc"].to_numpy(dtype=int)
    weekdays = df["weekday"].to_numpy(dtype=int)
    times = df.index
    n = len(df)

    ema_exit = df[f"ema{dynamic_exit_ema}"].to_numpy(dtype=float) if dynamic_exit_ema and f"ema{dynamic_exit_ema}" in df.columns else None
    rsi2 = df["rsi2"].to_numpy(dtype=float) if "rsi2" in df.columns else None

    trades = []
    i = 50

    while i < n - 2:
        sig = int(signals[i])
        if sig == 0:
            i += 1
            continue

        hr = hours[i]
        if not (session_start_h <= hr <= session_end_h):
            i += 1
            continue

        # Evitar gaps de fin de semana
        if weekdays[i] == 4 and hr >= 20:
            i += 1
            continue

        cur_atr = atr[i]
        if not math.isfinite(cur_atr) or cur_atr <= 0:
            i += 1
            continue

        # Entrada en apertura de la barra i+1
        k = i + 1
        side = sig  # +1 LONG, -1 SHORT
        entry = o[k] + side * (spr[k] / 2.0)
        sl = entry - side * (stop_atr * cur_atr)
        tp = entry + side * (tp_atr * cur_atr) if tp_atr else None

        sl_curr = sl
        be_active = False
        exit_px = None
        reason = "TIMEOUT"
        j = k

        for j in range(k, min(n - 1, k + max_holding_bars)):
            bar_spr = spr[j]
            eval_lo = l[j] - (bar_spr / 2.0) if side == 1 else l[j] + (bar_spr / 2.0)
            eval_hi = h[j] + (bar_spr / 2.0) if side == -1 else h[j] - (bar_spr / 2.0)

            hit_sl = (eval_lo <= sl_curr) if side == 1 else (eval_hi >= sl_curr)
            hit_tp = ((eval_hi >= tp) if side == 1 else (eval_lo <= tp)) if tp else False

            if hit_sl and hit_tp:
                exit_px = sl_curr
                reason = "STOP_CONSERVATIVE"
                break
            elif hit_sl:
                exit_px = sl_curr
                reason = "STOP"
                break
            elif hit_tp:
                exit_px = tp
                reason = "TP"
                break

            # Regla de salida dinámica si está activada
            if dynamic_exit_ema is not None and ema_exit is not None:
                if side == 1 and c[j] > ema_exit[j]:
                    next_k = min(n - 1, j + 1)
                    exit_px = o[next_k] - (spr[next_k] / 2.0)
                    reason = f"DYNAMIC_EMA{dynamic_exit_ema}"
                    j = next_k
                    break
                elif side == -1 and c[j] < ema_exit[j]:
                    next_k = min(n - 1, j + 1)
                    exit_px = o[next_k] + (spr[next_k] / 2.0)
                    reason = f"DYNAMIC_EMA{dynamic_exit_ema}"
                    j = next_k
                    break

            if dynamic_exit_rsi is not None and rsi2 is not None:
                if side == 1 and rsi2[j] >= dynamic_exit_rsi:
                    next_k = min(n - 1, j + 1)
                    exit_px = o[next_k] - (spr[next_k] / 2.0)
                    reason = "DYNAMIC_RSI"
                    j = next_k
                    break
                elif side == -1 and rsi2[j] <= (100 - dynamic_exit_rsi):
                    next_k = min(n - 1, j + 1)
                    exit_px = o[next_k] + (spr[next_k] / 2.0)
                    reason = "DYNAMIC_RSI"
                    j = next_k
                    break

            # Breakeven
            if use_breakeven and not be_active:
                unrealized = side * (c[j] - entry)
                if unrealized >= (be_trigger_atr * cur_atr):
                    be_active = True
                    sl_curr = entry + side * (be_lock_atr * cur_atr)

        if exit_px is None:
            last_bar = min(n - 1, k + max_holding_bars - 1)
            exit_px = c[last_bar] - side * (spr[last_bar] / 2.0)
            reason = "TIMEOUT"
            j = last_bar

        net_price = side * (exit_px - entry) - comm
        r = net_price / (stop_atr * cur_atr)

        trades.append({
            "entry_time": times[k],
            "exit_time": times[j],
            "side": "LONG" if side == 1 else "SHORT",
            "entry_px": entry,
            "exit_px": exit_px,
            "r": r,
            "won": r > 0,
            "reason": reason,
            "bars": j - k + 1,
        })
        i = j + 1

    if not trades:
        return {
            "n": 0, "wr": 0.0, "pf": 0.0, "mean_r": 0.0,
            "total_r": 0.0, "max_dd_pct": 0.0, "t_stat": 0.0,
            "wilson_lb": 0.0, "verdict": "FAIL [NO TRADES]",
            "fail_reasons": ["Sin operaciones ejecutadas en la ventana"],
        }

    tdf = pd.DataFrame(trades)
    r_arr = tdf["r"].to_numpy()
    n_tr = len(r_arr)
    wins = int((r_arr > 0).sum())
    wr = (wins / n_tr) * 100.0

    gw = float(r_arr[r_arr > 0].sum()) if wins > 0 else 0.0
    gl = float(abs(r_arr[r_arr <= 0].sum())) if (n_tr - wins) > 0 else 1e-9
    pf = gw / gl if gl > 0 else float("inf")

    mean_r = float(r_arr.mean())
    std_r = float(r_arr.std(ddof=1)) if n_tr > 1 else 0.0
    t_stat = (mean_r / (std_r / math.sqrt(n_tr))) if std_r > 0 else 0.0

    cum_r = np.cumsum(r_arr)
    peak = np.maximum.accumulate(cum_r)
    dd_r = peak - cum_r
    max_dd_r = float(dd_r.max()) if len(dd_r) > 0 else 0.0
    max_dd_pct = (max_dd_r * (CAPITAL_BASE * 0.005) / CAPITAL_BASE) * 100.0

    wlb = wilson_lower_bound(wins, n_tr)

    # Evaluación de criterios de Carlos
    fail_reasons = []
    if wr < 70.0:
        fail_reasons.append(f"Win Rate {wr:.1f}% < 70.0%")
    if max_dd_pct > 5.0:
        fail_reasons.append(f"Max Drawdown {max_dd_pct:.2f}% > 5.0%")
    if n_tr < 100:
        fail_reasons.append(f"Solo {n_tr} operaciones (mínimo 100)")
    if pf < 1.25 or mean_r <= 0:
        fail_reasons.append(f"Profit Factor {pf:.2f} <= 1.25 o E[R]={mean_r:+.4f} <= 0")
    if t_stat < 1.5:
        fail_reasons.append(f"t-stat {t_stat:.2f} < 1.5 (baja significancia)")

    verdict = "APROBADA [PASS]" if not fail_reasons else "DESCARTADA [FAIL]"

    return {
        "n": n_tr,
        "wr": wr,
        "pf": pf,
        "mean_r": mean_r,
        "total_r": float(cum_r[-1]),
        "max_dd_pct": max_dd_pct,
        "t_stat": t_stat,
        "wilson_lb": wlb,
        "verdict": verdict,
        "fail_reasons": fail_reasons,
        "start_date": str(times[0].date()),
        "end_date": str(times[-1].date()),
    }


def update_dashboard_markdown(result_entry: dict):
    """Actualiza automáticamente el archivo CUADRO_ESTRATEGIAS_INTRADIA.md con el nuevo resultado."""
    # Leemos o creamos el archivo
    header = (
        "# Cuadro de Mando de Estrategias Intradía (M15 / M30)\n\n"
        "> **Criterios de Admisión para Cuenta Real:**\n"
        "> 1. Win Rate > 70.0%\n"
        "> 2. Drawdown Máximo < 5.0%\n"
        "> 3. M15 o M30 en 4 activos (DAX40, SP500, US100, EURUSD / GOLD)\n"
        "> 4. Rentabilidad neta verificada con costes reales de broker (E[R] > 0, PF > 1.25)\n"
        "> 5. Histórico robusto (N >= 100 operaciones en datos de 4 a 8 años)\n\n"
        "---\n\n"
        "## Registro Histórico de Pruebas de Backtesting\n\n"
        "| Fecha | Estrategia / Fuente | Activo | TF | N | Win Rate | PF | Max DD | E[R] | Estado | Veredicto / Motivo del Descarte |\n"
        "| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |\n"
    )

    if not DASHBOARD_MD_PATH.exists():
        content = header
    else:
        content = DASHBOARD_MD_PATH.read_text(encoding="utf-8")
        if "| Fecha | Estrategia" not in content:
            content = header

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    status_icon = "🟢 APROBADA" if "PASS" in result_entry["verdict"] else "🔴 DESCARTADA"
    reason_str = "CUMPLE TODOS LOS CRITERIOS" if "PASS" in result_entry["verdict"] else "; ".join(result_entry["fail_reasons"])

    row = (
        f"| {date_str} | {result_entry['strategy_name']} | {result_entry['symbol']} | "
        f"{result_entry['timeframe']} | {result_entry['n']} | **{result_entry['wr']:.1f}%** | "
        f"{result_entry['pf']:.2f} | {result_entry['max_dd_pct']:.2f}% | {result_entry['mean_r']:+.4f} | "
        f"{status_icon} | {reason_str} |\n"
    )

    content += row
    DASHBOARD_MD_PATH.write_text(content, encoding="utf-8")
    print(f"\n[DASHBOARD ACTUALIZADO] -> {DASHBOARD_MD_PATH.name}")


def main():
    parser = argparse.ArgumentParser(description="Backtest Universal de Estrategias Intradía.")
    parser.add_argument("--strategy", type=str, required=True, help="Nombre de la estrategia.")
    parser.add_argument("--symbol", type=str, default="GERMANY40", help="Símbolo a testear.")
    parser.add_argument("--timeframe", type=str, default="M30", choices=["M15", "M30"], help="Timeframe.")
    parser.add_argument("--stop-atr", type=float, default=2.0, help="Múltiplo de ATR para Stop Loss.")
    parser.add_argument("--tp-atr", type=float, default=None, help="Múltiplo de ATR para Take Profit fijo (opcional).")
    parser.add_argument("--dynamic-ema", type=int, default=9, help="EMA para salida dinámica (default: 9).")
    parser.add_argument("--dynamic-rsi", type=float, default=65.0, help="Umbral RSI para salida dinámica (default: 65.0).")
    args = parser.parse_args()

    tf_code = mt5.TIMEFRAME_M30 if args.timeframe == "M30" else mt5.TIMEFRAME_M15
    print(f"Descargando datos históricos para {args.symbol} ({args.timeframe})...")
    df_raw = fetch_symbol_bars(args.symbol, tf_code, 99999)
    df = calculate_intraday_features(df_raw)

    print(f"Datos cargados: {len(df):,} barras ({df.index[0].date()} a {df.index[-1].date()})")

    # Señal placeholder para test de CLI:
    signals = np.zeros(len(df), dtype=int)

    session = SESSION_UTC.get(args.symbol, (7, 17))
    res = simulate_backtest(
        df=df,
        symbol=args.symbol,
        signals=signals,
        stop_atr=args.stop_atr,
        tp_atr=args.tp_atr,
        dynamic_exit_ema=args.dynamic_ema,
        dynamic_exit_rsi=args.dynamic_rsi,
        session_start_h=session[0],
        session_end_h=session[1],
    )
    res["strategy_name"] = args.strategy
    res["symbol"] = args.symbol
    res["timeframe"] = args.timeframe

    print("\n" + "=" * 80)
    print(f"RESULTADO DEL BACKTEST: {args.strategy} en {args.symbol} {args.timeframe}")
    print("=" * 80)
    print(f"Operaciones (N):   {res['n']}")
    print(f"Win Rate:          {res['wr']:.2f}%")
    print(f"Profit Factor:     {res['pf']:.2f}")
    print(f"Max Drawdown:      {res['max_dd_pct']:.2f}%")
    print(f"E[R] por trade:    {res['mean_r']:+.4f} R")
    print(f"Veredicto:         {res['verdict']}")
    if res["fail_reasons"]:
        print(f"Motivo descarte:   {', '.join(res['fail_reasons'])}")
    print("=" * 80)

    update_dashboard_markdown(res)
    mt5.shutdown()


if __name__ == "__main__":
    main()
