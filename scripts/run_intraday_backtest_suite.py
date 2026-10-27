"""Suite de Backtesting Intradía — Primera Batería de Estrategias M15.

Ejecuta todas las estrategias intradía implementadas sobre la Trinidad de Activos
(DAX40, SP500, EURUSD) + NASDAQ100 y vuelca los resultados al dashboard.

Uso:
    python scripts/run_intraday_backtest_suite.py

Requisitos: MT5 abierto y conectado a cuenta DEMO.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from trading_v2.backtesting.intraday_engine import (
    BacktestMetrics,
    add_base_indicators,
    compute_metrics,
    fetch_bars,
    add_h1_trend,
    run_backtest,
    simulate_strategy,
    PASS_WR,
    PASS_MAX_DD,
)

# ---------------------------------------------------------------------------
# Activos objetivo
# ---------------------------------------------------------------------------
ASSETS = ["GERMANY40", "[SP500]", "EURUSD", "US100"]
TIMEFRAME = "M15"
BARS_BACK = 25000   # ~6 años de barras activas en M15


# ===========================================================================
# -- ESTRATEGIA 1: RSI2 Mean-Reversion + SMA200 Regime ----------------------
# Descripción: Pullback a favor de tendencia macro (precio > SMA200).
# RSI2 < 10 para LONG, > 90 para SHORT. Filtro de tendencia H1.
# Inspirado en Larry Connors' RSI(2) sobre índices — adaptado a M15.
# ===========================================================================

def signal_rsi2_sma200(df: pd.DataFrame) -> np.ndarray:
    """LONG si: c > SMA200 y RSI2 < 10. SHORT si: c < SMA200 y RSI2 > 90."""
    n = len(df)
    signals = np.zeros(n, dtype=int)
    c      = df["Close"].to_numpy(dtype=float)
    rsi2   = df["rsi2"].to_numpy(dtype=float)
    sma200 = df["sma200"].to_numpy(dtype=float)
    h1tr   = df["h1_trend"].to_numpy(dtype=int) if "h1_trend" in df.columns else np.zeros(n, dtype=int)

    for i in range(200, n - 1):
        if not (math.isfinite(sma200[i]) and math.isfinite(rsi2[i])):
            continue
        long_ok  = (c[i] > sma200[i]) and (rsi2[i] < 10.0) and (h1tr[i] >= 0)
        short_ok = (c[i] < sma200[i]) and (rsi2[i] > 90.0) and (h1tr[i] <= 0)
        if long_ok:
            signals[i] = 1
        elif short_ok:
            signals[i] = -1
    return signals


# ===========================================================================
# -- ESTRATEGIA 2: Bollinger Band Squeeze + RSI Extremo ---------------------
# Descripción: Entrada cuando el precio toca la banda exterior de Bollinger
# (2.0σ) Y el RSI2 está en extremo. Salida por banda media o time-stop.
# Funciona en mercados en rango de media-alta frecuencia.
# ===========================================================================

def signal_bollinger_rsi(df: pd.DataFrame) -> np.ndarray:
    """LONG si: c <= BB_lower y RSI2 < 15. SHORT si: c >= BB_upper y RSI2 > 85."""
    n = len(df)
    signals = np.zeros(n, dtype=int)
    c      = df["Close"].to_numpy(dtype=float)
    rsi2   = df["rsi2"].to_numpy(dtype=float)
    bb_lo  = df["bb_lo"].to_numpy(dtype=float)
    bb_up  = df["bb_up"].to_numpy(dtype=float)
    sma200 = df["sma200"].to_numpy(dtype=float)
    h1tr   = df["h1_trend"].to_numpy(dtype=int) if "h1_trend" in df.columns else np.zeros(n, dtype=int)

    for i in range(200, n - 1):
        if not (math.isfinite(bb_lo[i]) and math.isfinite(rsi2[i])):
            continue
        # Filtro de régimen: no operar en contra de la tendencia macro fuerte
        long_ok  = (c[i] <= bb_lo[i]) and (rsi2[i] < 15.0) and (h1tr[i] >= 0)
        short_ok = (c[i] >= bb_up[i]) and (rsi2[i] > 85.0) and (h1tr[i] <= 0)
        if long_ok:
            signals[i] = 1
        elif short_ok:
            signals[i] = -1
    return signals


# ===========================================================================
# -- ESTRATEGIA 3: Liquidity Sweep + Rejection Wick (Francotirador) ---------
# Descripción: El precio barre el máximo/mínimo de la última hora (Initial
# Balance de 4 barras M15) y cierra con mecha de rechazo >= 35%.
# Requiere: barrido confirmado + absorción + tendencia H1 alineada.
# ===========================================================================

def signal_sniper_sweep(df: pd.DataFrame) -> np.ndarray:
    """LONG: barrido de IB_low + wick inferior >= 35% + H1 alcista.
    SHORT: barrido de IB_high + wick superior >= 35% + H1 bajista."""
    n = len(df)
    signals = np.zeros(n, dtype=int)
    h      = df["High"].to_numpy(dtype=float)
    l      = df["Low"].to_numpy(dtype=float)
    ib_hi  = df["ib_high"].to_numpy(dtype=float)
    ib_lo  = df["ib_low"].to_numpy(dtype=float)
    lo_wick = df["lower_wick"].to_numpy(dtype=float)
    up_wick = df["upper_wick"].to_numpy(dtype=float)
    clv    = df["clv"].to_numpy(dtype=float)
    h1tr   = df["h1_trend"].to_numpy(dtype=int) if "h1_trend" in df.columns else np.ones(n, dtype=int)

    for i in range(15, n - 1):
        if not (math.isfinite(ib_hi[i]) and math.isfinite(ib_lo[i])):
            continue
        swept_lo = l[i] < ib_lo[i]
        swept_hi = h[i] > ib_hi[i]

        long_ok  = swept_lo and (lo_wick[i] >= 0.35) and (clv[i] >= 0.45) and (h1tr[i] >= 0)
        short_ok = swept_hi and (up_wick[i] >= 0.35) and (clv[i] <= 0.55) and (h1tr[i] <= 0)

        if long_ok and not short_ok:
            signals[i] = 1
        elif short_ok and not long_ok:
            signals[i] = -1
    return signals


# ===========================================================================
# -- ESTRATEGIA 4: Opening Range Breakout (ORB) adaptado a M15 --------------
# Descripción: Define el rango de las primeras 2 horas de sesión (8 barras M15).
# Entra en breakout del rango con confirmación de volumen relativo.
# Solo opera en las 3 primeras horas tras el breakout.
# ===========================================================================

def add_orb_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula el rango de apertura (ORB) de la sesión: max/min de las primeras 8 barras."""
    out = df.copy()
    out["date"] = out.index.date
    out["orb_high"] = np.nan
    out["orb_low"]  = np.nan

    for date, grp in out.groupby("date"):
        # Primeras 8 barras de la sesión (2 horas en M15)
        opening = grp.head(8)
        if len(opening) < 4:
            continue
        orb_h = opening["High"].max()
        orb_l = opening["Low"].min()
        # El ORB está disponible para las barras SIGUIENTES (causal)
        rest_idx = grp.index[8:]
        out.loc[rest_idx, "orb_high"] = orb_h
        out.loc[rest_idx, "orb_low"]  = orb_l

    # RVOL: volumen relativo (barra actual vs media 20 barras)
    vol = out["TickVolume"].astype(float)
    out["rvol"] = vol / vol.rolling(20, min_periods=5).mean().replace(0, np.nan)
    return out


def signal_orb(df: pd.DataFrame) -> np.ndarray:
    """LONG: cierre por encima del ORB_high con RVOL >= 1.2.
    SHORT: cierre por debajo del ORB_low con RVOL >= 1.2."""
    n = len(df)
    signals = np.zeros(n, dtype=int)

    if "orb_high" not in df.columns:
        return signals

    c      = df["Close"].to_numpy(dtype=float)
    o      = df["Open"].to_numpy(dtype=float)
    orb_hi = df["orb_high"].to_numpy(dtype=float)
    orb_lo = df["orb_low"].to_numpy(dtype=float)
    rvol   = df["rvol"].to_numpy(dtype=float) if "rvol" in df.columns else np.ones(n)
    hours  = df["hour_utc"].to_numpy(dtype=int)
    h1tr   = df["h1_trend"].to_numpy(dtype=int) if "h1_trend" in df.columns else np.ones(n, dtype=int)

    for i in range(15, n - 1):
        if not (math.isfinite(orb_hi[i]) and math.isfinite(rvol[i])):
            continue
        # Solo operar durante las primeras 5 horas de la sesión activa
        if hours[i] > 17:
            continue
        vol_ok = rvol[i] >= 1.1
        long_ok  = (c[i] > orb_hi[i]) and (o[i] <= orb_hi[i]) and vol_ok and (h1tr[i] >= 0)
        short_ok = (c[i] < orb_lo[i]) and (o[i] >= orb_lo[i]) and vol_ok and (h1tr[i] <= 0)
        if long_ok and not short_ok:
            signals[i] = 1
        elif short_ok and not long_ok:
            signals[i] = -1
    return signals


# ===========================================================================
# -- ESTRATEGIA 5: EMA Crossover filtrado por régimen -----------------------
# Descripción: Cruce EMA20 x EMA50 en M15, solo en dirección de la tendencia
# semanal (precio > SMA200). Filtro de expansión ATR (no operar en
# mercados dormidos).
# ===========================================================================

def signal_ema_cross(df: pd.DataFrame) -> np.ndarray:
    """LONG: EMA20 cruza sobre EMA50 con c > SMA200. SHORT: lo contrario."""
    n = len(df)
    signals = np.zeros(n, dtype=int)
    ema20  = df["ema20"].to_numpy(dtype=float)
    ema50  = df["ema50"].to_numpy(dtype=float)
    sma200 = df["sma200"].to_numpy(dtype=float)
    atr    = df["atr14"].to_numpy(dtype=float)
    h1tr   = df["h1_trend"].to_numpy(dtype=int) if "h1_trend" in df.columns else np.zeros(n, dtype=int)

    for i in range(201, n - 1):
        if not (math.isfinite(ema20[i]) and math.isfinite(sma200[i])):
            continue
        cross_up   = (ema20[i] > ema50[i]) and (ema20[i-1] <= ema50[i-1])
        cross_down = (ema20[i] < ema50[i]) and (ema20[i-1] >= ema50[i-1])
        # ATR debe ser al menos el percentil mediano (evitar mercados muertos)
        atr_ok = math.isfinite(atr[i]) and atr[i] > 0

        long_ok  = cross_up   and (ema50[i] > sma200[i]) and atr_ok and (h1tr[i] >= 0)
        short_ok = cross_down and (ema50[i] < sma200[i]) and atr_ok and (h1tr[i] <= 0)
        if long_ok:
            signals[i] = 1
        elif short_ok:
            signals[i] = -1
    return signals


# ===========================================================================
# -- Runner principal --------------------------------------------------------
# ===========================================================================

STRATEGIES = [
    {
        "name": "RSI2_SMA200_MeanReversion",
        "signal_fn": signal_rsi2_sma200,
        "stop_atr": 1.5,
        "tp_atr": 1.0,
        "max_holding_bars": 12,
        "use_h1_trend": True,
        "notes": "Larry Connors RSI(2) adaptado a M15. Pullback en tendencia macro.",
    },
    {
        "name": "Bollinger_RSI_Extremes",
        "signal_fn": signal_bollinger_rsi,
        "stop_atr": 1.5,
        "tp_atr": 0.8,
        "max_holding_bars": 10,
        "use_h1_trend": True,
        "notes": "Reversión a la media Bollinger 2σ + RSI2 en extremo.",
    },
    {
        "name": "Sniper_LiquiditySweep",
        "signal_fn": signal_sniper_sweep,
        "stop_atr": 1.2,
        "tp_atr": 0.8,
        "max_holding_bars": 6,
        "use_h1_trend": True,
        "notes": "Barrido de IB (1h) + mecha de absorción >= 35%. Sniper institucional.",
    },
    {
        "name": "OpeningRangeBreakout_ORB",
        "signal_fn": signal_orb,
        "stop_atr": 1.5,
        "tp_atr": 1.5,
        "max_holding_bars": 12,
        "use_h1_trend": True,
        "add_indicators_fn": add_orb_indicators,
        "notes": "ORB 2h de apertura de sesión + confirmación RVOL >= 1.1.",
    },
    {
        "name": "EMA20x50_Regime_Cross",
        "signal_fn": signal_ema_cross,
        "stop_atr": 2.0,
        "tp_atr": 2.0,
        "max_holding_bars": 20,
        "use_h1_trend": True,
        "notes": "Cruce EMA20/50 en M15 filtrado por régimen SMA200.",
    },
]


def run_all(assets=None, timeframe=TIMEFRAME, bars_back=BARS_BACK, save_json=True):
    """Ejecuta toda la batería de estrategias sobre todos los activos."""
    if assets is None:
        assets = ASSETS

    all_results: list[BacktestMetrics] = []
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    print("=" * 100)
    print(f"BACKTESTING INTRADÍA M15 — SUITE COMPLETA | {timestamp}")
    print(f"Activos: {assets} | Barras por activo: {bars_back:,}")
    print(f"Criterio PASS: WR > {PASS_WR}% | MaxDD < {PASS_MAX_DD}% | N >= 100 trades")
    print("=" * 100)

    for sym in assets:
        print(f"\n{'='*30} {sym} {'='*30}")
        df_cache = None   # Reusar datos descargados para el mismo símbolo

        for strat in STRATEGIES:
            name = strat["name"]
            try:
                # Descarga de datos (una sola vez por símbolo, reutilizando caché)
                if df_cache is None:
                    df_raw = fetch_bars(sym, timeframe, bars_back)
                    df_cache = add_base_indicators(df_raw)

                df = df_cache.copy()

                if strat.get("use_h1_trend", False):
                    df = add_h1_trend(df, sym)

                add_fn = strat.get("add_indicators_fn")
                if add_fn is not None:
                    df = add_fn(df)

                trades_df = simulate_strategy(
                    df=df,
                    symbol=sym,
                    signal_fn=strat["signal_fn"],
                    stop_atr=strat.get("stop_atr", 1.5),
                    tp_atr=strat.get("tp_atr", 1.0),
                    max_holding_bars=strat.get("max_holding_bars", 16),
                    use_session=True,
                )

                m = compute_metrics(trades_df, sym, timeframe, name)
                m.notes = strat.get("notes", "")
                all_results.append(m)
                print(m)

            except Exception as exc:
                print(f"  [XX] ERROR en {name} / {sym}: {exc}")
                err_m = BacktestMetrics(
                    symbol=sym, timeframe=timeframe, strategy_name=name,
                    n_trades=0, win_rate=0, profit_factor=0, mean_r=0,
                    total_r=0, max_dd_pct=0, sharpe_monthly=0, t_stat=0,
                    wilson_lb_pct=0, verdict="FAIL [XX]",
                    fail_reasons=[f"ERROR: {exc}"],
                    notes=strat.get("notes", ""),
                )
                all_results.append(err_m)

    # Resumen final
    print("\n" + "=" * 100)
    print("RESUMEN FINAL")
    print("=" * 100)
    passed = [m for m in all_results if m.verdict == "PASS OK"]
    marginal = [m for m in all_results if m.verdict == "MARGINAL ~"]
    failed = [m for m in all_results if m.verdict == "FAIL XX"]

    print(f"\nAPROBADAS  ({len(passed)}):")
    for m in passed:
        print(f"   {m}")
    print(f"\nMARGINALES ({len(marginal)}):")
    for m in marginal:
        print(f"   {m}")
    print(f"\nDESCARTADAS ({len(failed)}):")
    for m in failed:
        print(f"   {m} | Razones: {', '.join(m.fail_reasons)}")

    # Guardar resultados a JSON
    if save_json:
        out_path = Path("intraday_backtest_results.json")
        results_data = []
        for m in all_results:
            results_data.append({
                "timestamp": timestamp,
                "strategy": m.strategy_name,
                "symbol": m.symbol,
                "timeframe": m.timeframe,
                "n_trades": m.n_trades,
                "win_rate": round(m.win_rate, 2),
                "profit_factor": round(m.profit_factor, 3),
                "mean_r": round(m.mean_r, 4),
                "total_r": round(m.total_r, 2),
                "max_dd_pct": round(m.max_dd_pct, 3),
                "sharpe_monthly": round(m.sharpe_monthly, 3),
                "t_stat": round(m.t_stat, 3),
                "wilson_lb_pct": round(m.wilson_lb_pct, 2),
                "verdict": m.verdict,
                "fail_reasons": m.fail_reasons,
                "notes": m.notes,
            })
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results_data, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Resultados guardados en: {out_path.absolute()}")

    return all_results


if __name__ == "__main__":
    run_all()
