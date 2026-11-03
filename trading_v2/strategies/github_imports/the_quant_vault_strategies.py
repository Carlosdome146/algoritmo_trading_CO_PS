"""Estrategias adaptadas del repositorio brainbrick-trades/The-Quant-Trading-Vault (GitHub).

Fuente: https://github.com/brainbrick-trades/The-Quant-Trading-Vault
Estrategias implementadas:
1. Vault_BB_VWAP_Anomaly:
   - Origen: Bollinger-Bands-and-VWAP-based-Quantitative-Trading-Strategy.md
   - Lógica: Tendencia EMA50 > EMA200 + VWAP intradía + anomalía de precio bajo banda inferior de Bollinger (20, 2.0).
2. Vault_Connors_RSI2_Reversal:
   - Origen: Connors-Dual-Moving-Average-RSI-Reversal-Trading-Strategy.md
   - Lógica: Filtro macro SMA200 + sobreventa extrema RSI(2) < 10 + salida en SMA5 / EMA9.
3. Vault_Consecutive_Candle_Reversal:
   - Origen: Mean-Reversion-Consecutive-Candle-Reversal-Trading-Strategy.md
   - Lógica: 3 velas bajistas consecutivas con rechazo alcista (mecha inferior) a favor de la tendencia EMA200.
"""
from __future__ import annotations

import math
import numpy as np
import pandas as pd


def compute_intraday_vwap(df: pd.DataFrame) -> pd.Series:
    """Calcula el VWAP intradía reseteado cada medianoche UTC."""
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3.0
    vol = df["TickVolume"].astype(float).replace(0, 1.0)
    tp_vol = typical_price * vol

    # Agrupar por fecha
    dates = df.index.date
    cum_tp_vol = tp_vol.groupby(dates).cumsum()
    cum_vol = vol.groupby(dates).cumsum()

    vwap = cum_tp_vol / cum_vol.replace(0, np.nan)
    return vwap.fillna(typical_price)


# ===========================================================================
# 1. Bollinger Bands + VWAP Short-Term Anomaly Strategy
# ===========================================================================

def generate_vault_bb_vwap_signals(df: pd.DataFrame) -> np.ndarray:
    """
    Estrategia canónica de The Quant Trading Vault:
    - EMA 50 > EMA 200 (Tendencia alcista)
    - Close > VWAP intradía (Momentum positivo intradiario)
    - El mínimo de las últimas 10 barras perforó la Banda Inferior de Bollinger (anomalía de precio)
    - Vela actual cierra alcista (Close > Open)
    """
    n = len(df)
    signals = np.zeros(n, dtype=int)
    c = df["Close"].to_numpy(dtype=float)
    o = df["Open"].to_numpy(dtype=float)
    l = df["Low"].to_numpy(dtype=float)

    ema50 = df["Close"].ewm(span=50, adjust=False).mean().to_numpy()
    ema200 = df["Close"].ewm(span=200, adjust=False).mean().to_numpy()
    
    # Bollinger Bands (20 periodos, 2.0 std)
    sma20 = df["Close"].rolling(20, min_periods=10).mean()
    std20 = df["Close"].rolling(20, min_periods=10).std(ddof=0)
    bb_lo = (sma20 - 2.0 * std20).to_numpy()
    bb_up = (sma20 + 2.0 * std20).to_numpy()

    # VWAP
    vwap = compute_intraday_vwap(df).to_numpy()

    # Perforó banda inferior en las últimas 10 barras
    dipped_below_bb = (df["Low"] < (sma20 - 2.0 * std20)).rolling(10, min_periods=1).max().to_numpy()

    for i in range(210, n - 1):
        # Filtro de tendencia macro
        uptrend = ema50[i] > ema200[i]
        
        # BUY signal:
        # Tendencia alcista + precio sobre VWAP + anomalía reciente en banda inferior + vela verde
        if uptrend and (c[i] > vwap[i]) and (dipped_below_bb[i] > 0) and (c[i] > o[i]):
            signals[i] = 1

    return signals


# ===========================================================================
# 2. Connors Dual Moving Average RSI-2 Reversal
# ===========================================================================

def generate_vault_connors_rsi2_signals(df: pd.DataFrame) -> np.ndarray:
    """
    Estrategia Connors RSI-2 Reversal:
    - Tendencia: Close > SMA200 (o EMA200)
    - Gatillo: RSI(2) < 10 (sobreventa extrema intradiaria)
    - Confirmación de soporte: Close > Low anterior o mecha de absorción >= 30%
    """
    n = len(df)
    signals = np.zeros(n, dtype=int)
    c = df["Close"].to_numpy(dtype=float)
    o = df["Open"].to_numpy(dtype=float)
    l = df["Low"].to_numpy(dtype=float)
    h = df["High"].to_numpy(dtype=float)

    sma200 = df["Close"].rolling(200, min_periods=50).mean().to_numpy()

    # RSI(2)
    delta = df["Close"].diff()
    up2 = delta.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
    dn2 = (-delta.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    rsi2 = (100 - 100 / (1 + up2 / dn2.replace(0, np.nan))).fillna(50.0).to_numpy()

    rng = np.maximum(h - l, 1e-9)
    lower_wick = (np.minimum(o, c) - l) / rng

    for i in range(205, n - 1):
        # Long only en tendencia
        if (c[i] > sma200[i]) and (rsi2[i] < 10.0) and (lower_wick[i] >= 0.25):
            signals[i] = 1

    return signals


# ===========================================================================
# 3. Consecutive Candle Reversal Strategy
# ===========================================================================

def generate_vault_consecutive_candle_signals(df: pd.DataFrame) -> np.ndarray:
    """
    Estrategia Mean-Reversion Consecutive Candle Reversal:
    - 3 barras consecutivas bajistas: Close[i-1] < Close[i-2] < Close[i-3]
    - Filtro de tendencia macro: Close > EMA200
    - Barra actual i es verde (Close > Open) con mecha de rechazo inferior >= 35%
    """
    n = len(df)
    signals = np.zeros(n, dtype=int)
    c = df["Close"].to_numpy(dtype=float)
    o = df["Open"].to_numpy(dtype=float)
    l = df["Low"].to_numpy(dtype=float)
    h = df["High"].to_numpy(dtype=float)

    ema200 = df["Close"].ewm(span=200, adjust=False).mean().to_numpy()
    rng = np.maximum(h - l, 1e-9)
    lower_wick = (np.minimum(o, c) - l) / rng

    for i in range(205, n - 1):
        if c[i] > ema200[i]:
            # 3 velas rojas consecutivas previas
            three_red = (c[i-1] < o[i-1]) and (c[i-2] < o[i-2]) and (c[i-3] < o[i-3]) and (c[i-1] < c[i-2] < c[i-3])
            # Vela actual de rebote
            reversal = (c[i] > o[i]) and (lower_wick[i] >= 0.35)
            if three_red and reversal:
                signals[i] = 1

    return signals
