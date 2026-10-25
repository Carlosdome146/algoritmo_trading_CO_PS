"""Laboratorio Cuantitativo Intradía de Alta Tasa de Acierto (M15 / M30).

Objetivo de Carlos:
- Win Rate > 70%
- Max Drawdown < 5%
- Operaciones en M15 o M30
- Datos históricos reales de MT5 (hasta 99.999 barras: 4.5 años en M15, 8.5 años en M30)
- Costes reales de spread y comisión descontados causalmente.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trading_v2.backtesting.intraday_engine import wilson_lower_bound, POINT, COST_PER_LOT


def fetch_data(symbol: str, timeframe: int, count: int = 99999) -> pd.DataFrame:
    if not mt5.initialize():
        raise RuntimeError("MT5 no conectado")
    mt5.symbol_select(symbol, True)
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None or len(rates) == 0:
        raise ValueError(f"No hay datos para {symbol}")
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


def backtest_mean_reversion_dynamic_exit(
    df: pd.DataFrame,
    symbol: str,
    tf_str: str,
    rsi_entry: float = 10.0,
    stop_atr: float = 2.5,
    exit_rsi: float = 65.0,
    exit_ema_span: int = 7,
    max_bars: int = 12,
    session_start: int = 7,
    session_end: int = 17,
    long_only: bool = True,
) -> dict:
    c = df["Close"].to_numpy(dtype=float)
    o = df["Open"].to_numpy(dtype=float)
    h = df["High"].to_numpy(dtype=float)
    l = df["Low"].to_numpy(dtype=float)
    spr = df["Spread"].to_numpy(dtype=float) * POINT.get(symbol, 0.01)
    n = len(df)
    times = df.index

    # ATR(14)
    prev_c = pd.Series(c).shift(1)
    tr = pd.concat([pd.Series(h - l), (pd.Series(h) - prev_c).abs(), (pd.Series(l) - prev_c).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=5).mean().to_numpy()

    # RSI(2)
    delta = pd.Series(c).diff()
    up = delta.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    rsi2 = (100 - 100 / (1 + up / dn.replace(0, np.nan))).to_numpy()

    # SMA200 (Tendencia macro en el timeframe)
    sma200 = pd.Series(c).rolling(200, min_periods=50).mean().to_numpy()

    # EMA de salida rápida
    ema_exit = pd.Series(c).ewm(span=exit_ema_span, adjust=False).mean().to_numpy()

    hours = times.hour.to_numpy()
    comm = COST_PER_LOT.get(symbol, 0.0)

    trades = []
    i = 205
    while i < n - 2:
        hr = hours[i]
        if not (session_start <= hr <= session_end):
            i += 1
            continue

        if not (math.isfinite(sma200[i]) and math.isfinite(rsi2[i]) and math.isfinite(atr[i]) and atr[i] > 0):
            i += 1
            continue

        # Regla causal de entrada:
        # LONG: Tendencia alcista (Close > SMA200) + Sobrevendido extremo (RSI2 < rsi_entry)
        long_signal = (c[i] > sma200[i]) and (rsi2[i] < rsi_entry)
        
        # SHORT (solo si no es long_only):
        short_signal = False
        if not long_only:
            short_signal = (c[i] < sma200[i]) and (rsi2[i] > (100 - rsi_entry))

        side = 1 if long_signal else (-1 if short_signal else 0)
        if side == 0:
            i += 1
            continue

        # Entrada en apertura de la barra i+1 con medio spread
        k = i + 1
        entry = o[k] + side * (spr[k] / 2.0)
        sl = entry - side * (stop_atr * atr[i])

        exit_px = None
        reason = "TIME"
        j = k

        for j in range(k, min(n - 1, k + max_bars)):
            bar_spr = spr[j]
            # Comprobación de stop loss
            if side == 1 and l[j] <= sl:
                exit_px = sl - (bar_spr / 2.0)
                reason = "STOP"
                break
            elif side == -1 and h[j] >= sl:
                exit_px = sl + (bar_spr / 2.0)
                reason = "STOP"
                break

            # Regla de salida dinámica: reversion lograda (cierre supera EMA de salida o RSI se normaliza)
            if side == 1 and (c[j] > ema_exit[j] or rsi2[j] >= exit_rsi):
                # Salida en la apertura de j+1
                next_bar = min(n - 1, j + 1)
                exit_px = o[next_bar] - (spr[next_bar] / 2.0)
                reason = "RULE"
                j = next_bar
                break
            elif side == -1 and (c[j] < ema_exit[j] or rsi2[j] <= (100 - exit_rsi)):
                next_bar = min(n - 1, j + 1)
                exit_px = o[next_bar] + (spr[next_bar] / 2.0)
                reason = "RULE"
                j = next_bar
                break

        if exit_px is None:
            last_bar = min(n - 1, k + max_bars)
            exit_px = c[last_bar] - side * (spr[last_bar] / 2.0)
            j = last_bar

        net_pnl = side * (exit_px - entry) - comm
        r = net_pnl / (stop_atr * atr[i])

        trades.append({
            "entry_time": times[k],
            "exit_time": times[j],
            "side": "LONG" if side == 1 else "SHORT",
            "entry": entry,
            "exit": exit_px,
            "r": r,
            "won": r > 0,
            "reason": reason,
            "bars": j - k + 1,
        })
        i = j + 1

    if not trades:
        return {"n": 0, "wr": 0.0, "pf": 0.0, "max_dd_pct": 0.0, "verdict": "NO_TRADES"}

    tdf = pd.DataFrame(trades)
    r_arr = tdf["r"].to_numpy()
    n_tr = len(r_arr)
    wins = int((r_arr > 0).sum())
    wr = (wins / n_tr) * 100

    gw = float(r_arr[r_arr > 0].sum()) if wins > 0 else 0.0
    gl = float(abs(r_arr[r_arr <= 0].sum())) if (n_tr - wins) > 0 else 1e-9
    pf = gw / gl if gl > 0 else float("inf")

    # Drawdown en capital simulado (0.5% riesgo por trade sobre 3000€)
    cum_r = np.cumsum(r_arr)
    peak = np.maximum.accumulate(cum_r)
    dd_r = peak - cum_r
    max_dd_r = float(dd_r.max()) if len(dd_r) > 0 else 0.0
    max_dd_pct = (max_dd_r * (3000 * 0.005) / 3000) * 100

    wlb = wilson_lower_bound(wins, n_tr)

    return {
        "symbol": symbol,
        "tf": tf_str,
        "n": n_tr,
        "wr": wr,
        "pf": pf,
        "mean_r": float(r_arr.mean()),
        "max_dd_pct": max_dd_pct,
        "wilson_lb": wlb,
        "total_r": float(cum_r[-1]),
        "period_start": str(times[0].date()),
        "period_end": str(times[-1].date()),
    }


def run_laboratory():
    print("=" * 100)
    print("LABORATORIO INTRADÍA DE ALTA PRECISIÓN: REVERSIÓN DINÁMICA CON SALIDA POR MEDIA")
    print("Objetivo de Carlos: Win Rate > 70% | MaxDD < 5% | M15 / M30 | Historial completo MT5")
    print("=" * 100)
    print(f"{'ACTIVO':<10} | {'TF':<4} | {'N TRADES':<8} | {'WIN RATE':<9} | {'W-LB':<7} | {'PF':<6} | {'MaxDD%':<7} | {'TOTAL R':<8} | {'PERIODO':<23} | {'ESTADO':<8}")
    print("-" * 100)

    assets = [
        ("GERMANY40", 7, 17),
        ("[SP500]", 13, 21),
        ("US100", 13, 21),
        ("GOLD", 7, 21),
    ]

    results = []

    for sym, s_start, s_end in assets:
        for tf_str, tf_code in [("M30", mt5.TIMEFRAME_M30), ("M15", mt5.TIMEFRAME_M15)]:
            try:
                df = fetch_data(sym, tf_code, 99999)
                # Testeamos configuración de alta precisión:
                # Long only en índices, RSI2 < 8, SL = 2.5 ATR, salida dinámica EMA7 o RSI2 > 65
                res = backtest_mean_reversion_dynamic_exit(
                    df=df,
                    symbol=sym,
                    tf_str=tf_str,
                    rsi_entry=8.0,
                    stop_atr=2.5,
                    exit_rsi=65.0,
                    exit_ema_span=7,
                    max_bars=10 if tf_str == "M30" else 16,
                    session_start=s_start,
                    session_end=s_end,
                    long_only=True,
                )
                if res["n"] > 0:
                    status = "[PASS]" if (res["wr"] >= 70.0 and res["max_dd_pct"] <= 5.0 and res["n"] >= 100) else (
                        "[MARG]" if (res["wr"] >= 68.0 and res["max_dd_pct"] <= 5.0) else "[FAIL]"
                    )
                    res["status"] = status
                    results.append(res)
                    period = f"{res['period_start']} -> {res['period_end']}"
                    print(f"{sym:<10} | {tf_str:<4} | {res['n']:<8} | {res['wr']:<8.1f}% | {res['wilson_lb']:<6.1f}% | {res['pf']:<6.2f} | {res['max_dd_pct']:<6.2f}% | {res['total_r']:+7.1f}R | {period:<23} | {status}")
            except Exception as e:
                print(f"{sym:<10} | {tf_str:<4} | ERROR: {e}")

    print("=" * 100)
    mt5.shutdown()
    return results


if __name__ == "__main__":
    run_laboratory()
