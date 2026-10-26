"""Estrategias adaptadas del repositorio OpenByteInc/QuantDinger (GitHub).

Fuente: https://github.com/OpenByteInc/QuantDinger
Módulos de origen:
1. backend_api_python/app/services/strategy_authoring.py (_MULTI_TIMEFRAME_TEMPLATE)
   - Cruce rápido M15 (MA10 vs MA30) con confirmación de tendencia en H1 (EMA20 > EMA50).
2. backend_api_python/app/services/factors/registry.py (_keltner)
   - Reversión a la media con Canales de Keltner (EMA20 +/- 2.0 * ATR10) filtrado por tendencia macro.
"""
from __future__ import annotations

import math
import numpy as np
import pandas as pd


# ===========================================================================
# 1. QuantDinger Multi-Timeframe M15 x H1 Golden Cross
# ===========================================================================

def generate_quantdinger_mtf_cross_signals(df: pd.DataFrame) -> np.ndarray:
    """
    Estrategia canónica de QuantDinger Strategy API V2:
    - Marco temporal rápido: M15
    - MA Rápida: SMA 10
    - MA Lenta: SMA 30
    - Filtro Macro H1: h1_trend (EMA20_H1 > EMA50_H1)
    
    LONG: Golden cross en M15 (SMA10 cruza sobre SMA30) confirmado por H1 alcista.
    SHORT: Death cross en M15 (SMA10 cruza bajo SMA30) confirmado por H1 bajista.
    """
    n = len(df)
    signals = np.zeros(n, dtype=int)
    c = df["Close"]

    sma10 = c.rolling(10, min_periods=5).mean().to_numpy()
    sma30 = c.rolling(30, min_periods=15).mean().to_numpy()
    h1_trend = df["h1_trend"].to_numpy(dtype=int) if "h1_trend" in df.columns else np.zeros(n, dtype=int)

    for i in range(35, n - 1):
        if not (math.isfinite(sma10[i]) and math.isfinite(sma30[i]) and math.isfinite(sma10[i-1]) and math.isfinite(sma30[i-1])):
            continue

        golden_cross = (sma10[i-1] <= sma30[i-1]) and (sma10[i] > sma30[i])
        death_cross = (sma10[i-1] >= sma30[i-1]) and (sma10[i] < sma30[i])

        if golden_cross and h1_trend[i] >= 0:
            signals[i] = 1
        elif death_cross and h1_trend[i] <= 0:
            signals[i] = -1

    return signals


# ===========================================================================
# 2. QuantDinger Keltner Channel Reversion
# ===========================================================================

def compute_quantdinger_keltner(df: pd.DataFrame, period: int = 20, atr_period: int = 10, multiplier: float = 2.0) -> pd.DataFrame:
    """Implementa el factor canónico 'keltner_channels' de QuantDinger registry.py."""
    out = df.copy()
    c = out["Close"]
    h = out["High"]
    l = out["Low"]

    # Middle line = EMA(period)
    middle = c.ewm(span=period, adjust=False).mean()

    # True Range & ATR(atr_period)
    prev_c = c.shift(1)
    tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    atr = tr.rolling(atr_period, min_periods=3).mean()

    upper = middle + multiplier * atr
    lower = middle - multiplier * atr

    out["keltner_mid"] = middle
    out["keltner_ub"] = upper
    out["keltner_lb"] = lower
    # Factor 'position' en QuantDinger: (c - lower) / (upper - lower)
    rng = (upper - lower).replace(0, np.nan)
    out["keltner_pos"] = ((c - lower) / rng).fillna(0.5)

    return out


def generate_quantdinger_keltner_signals(df: pd.DataFrame) -> np.ndarray:
    """
    Reversión en Canales de Keltner según QuantDinger:
    - Filtro de tendencia: Close > SMA200 (para compras) o Close < SMA200 (para ventas)
    - Condición LONG: keltner_pos <= 0.05 (precio perfora banda inferior) y rechazo alcista
    - Condición SHORT: keltner_pos >= 0.95 (precio perfora banda superior) y rechazo bajista
    """
    ind = compute_quantdinger_keltner(df)
    n = len(ind)
    signals = np.zeros(n, dtype=int)

    c = ind["Close"].to_numpy(dtype=float)
    sma200 = ind["sma200"].to_numpy(dtype=float) if "sma200" in ind.columns else ind["Close"].rolling(200, min_periods=50).mean().to_numpy()
    k_pos = ind["keltner_pos"].to_numpy(dtype=float)
    lower_wick = ind["lower_wick"].to_numpy(dtype=float) if "lower_wick" in ind.columns else np.zeros(n)
    upper_wick = ind["upper_wick"].to_numpy(dtype=float) if "upper_wick" in ind.columns else np.zeros(n)

    for i in range(205, n - 1):
        if not (math.isfinite(sma200[i]) and math.isfinite(k_pos[i])):
            continue

        long_ok = (c[i] > sma200[i]) and (k_pos[i] <= 0.08) and (lower_wick[i] >= 0.25)
        short_ok = (c[i] < sma200[i]) and (k_pos[i] >= 0.92) and (upper_wick[i] >= 0.25)

        if long_ok and not short_ok:
            signals[i] = 1
        elif short_ok and not long_ok:
            signals[i] = -1

    return signals
