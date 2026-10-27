"""Estrategia adaptada del repositorio TauricResearch/TradingAgents (GitHub).

Fuente: https://github.com/TauricResearch/TradingAgents
Módulo de origen: tradingagents/agents/analysts/market_analyst.py & snapshot.py

En el repositorio original, el 'Market Analyst' utiliza un conjunto fijo de indicadores:
- Tendencia: EMA10, SMA50, SMA200 (Golden / Death cross y filtro macro)
- Momentum: MACD (12, 26, 9) y MACD Histogram
- Oscilador: RSI(14) con niveles de sobrecompra / sobreventa
- Volatilidad: Bandas de Bollinger (20 periodos, 2.0 sigma) y ATR(14)

Esta versión traduce la lógica cualitativa del Market Analyst y del Trader Agent a reglas
cuantitativas deterministas anti-lookahead para testear en M15 / M30.
"""
from __future__ import annotations

import math
import numpy as np
import pandas as pd


def compute_tradingagents_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula el set exacto de indicadores del Market Analyst de TradingAgents."""
    out = df.copy()
    c = out["Close"]
    h = out["High"]
    l = out["Low"]

    # Moving Averages
    out["ema10"] = c.ewm(span=10, adjust=False).mean()
    out["sma50"] = c.rolling(50, min_periods=20).mean()
    out["sma200"] = c.rolling(200, min_periods=50).mean()

    # MACD (12, 26, 9)
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    out["macd"] = ema12 - ema26
    out["macds"] = out["macd"].ewm(span=9, adjust=False).mean()
    out["macdh"] = out["macd"] - out["macds"]

    # RSI (14)
    delta = c.diff()
    up14 = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    dn14 = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    out["rsi14"] = (100 - 100 / (1 + up14 / dn14.replace(0, np.nan))).fillna(50.0)

    # Bollinger Bands (20, 2.0 sigma)
    sma20 = c.rolling(20, min_periods=10).mean()
    std20 = c.rolling(20, min_periods=10).std(ddof=0)
    out["boll_mid"] = sma20
    out["boll_ub"] = sma20 + 2.0 * std20
    out["boll_lb"] = sma20 - 2.0 * std20

    # ATR (14)
    prev_c = c.shift(1)
    tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    out["atr14"] = tr.rolling(14, min_periods=5).mean()

    return out


def generate_tradingagents_signals(df: pd.DataFrame) -> np.ndarray:
    """
    Genera señales causales basadas en la confluencia técnica del Market Analyst:
    
    LONG:
    1. Filtro de tendencia: Close > SMA200 y EMA10 > SMA50.
    2. Rebote en soporte dinámico: Low toca o penetra Bollinger inferior o EMA10.
    3. Giro de momentum: MACD Histogram > 0 o cruza al alza (macdh > macdh_prev).
    4. RSI14 saludable (entre 35 y 60, saliendo de sobreventa pero con recorrido).

    SHORT:
    1. Filtro de tendencia: Close < SMA200 y EMA10 < SMA50.
    2. Rechazo en resistencia dinámica: High toca o penetra Bollinger superior o EMA10.
    3. Giro de momentum bajista: MACD Histogram < 0 o cruza a la baja.
    4. RSI14 saliendo de sobrecompra (entre 40 y 65).
    """
    ind = compute_tradingagents_indicators(df)
    n = len(ind)
    signals = np.zeros(n, dtype=int)

    c = ind["Close"].to_numpy(dtype=float)
    h = ind["High"].to_numpy(dtype=float)
    l = ind["Low"].to_numpy(dtype=float)
    ema10 = ind["ema10"].to_numpy(dtype=float)
    sma50 = ind["sma50"].to_numpy(dtype=float)
    sma200 = ind["sma200"].to_numpy(dtype=float)
    macd = ind["macd"].to_numpy(dtype=float)
    macds = ind["macds"].to_numpy(dtype=float)
    macdh = ind["macdh"].to_numpy(dtype=float)
    rsi14 = ind["rsi14"].to_numpy(dtype=float)
    boll_lb = ind["boll_lb"].to_numpy(dtype=float)
    boll_ub = ind["boll_ub"].to_numpy(dtype=float)

    for i in range(205, n - 1):
        if not (math.isfinite(sma200[i]) and math.isfinite(rsi14[i]) and math.isfinite(macdh[i])):
            continue

        # Condiciones LONG
        trend_long = (c[i] > sma200[i]) and (ema10[i] > sma50[i])
        bounce_long = (l[i] <= boll_lb[i]) or (l[i] <= ema10[i] and c[i] > ema10[i])
        momentum_long = (macd[i] > macds[i]) and (macdh[i] > macdh[i-1])
        rsi_long = (35.0 <= rsi14[i] <= 62.0)

        long_ok = trend_long and bounce_long and momentum_long and rsi_long

        # Condiciones SHORT
        trend_short = (c[i] < sma200[i]) and (ema10[i] < sma50[i])
        bounce_short = (h[i] >= boll_ub[i]) or (h[i] >= ema10[i] and c[i] < ema10[i])
        momentum_short = (macd[i] < macds[i]) and (macdh[i] < macdh[i-1])
        rsi_short = (38.0 <= rsi14[i] <= 65.0)

        short_ok = trend_short and bounce_short and momentum_short and rsi_short

        if long_ok and not short_ok:
            signals[i] = 1
        elif short_ok and not long_ok:
            signals[i] = -1

    return signals
