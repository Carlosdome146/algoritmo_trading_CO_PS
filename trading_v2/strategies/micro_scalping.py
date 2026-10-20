"""Estrategia de Micro-Scalping Institucional Francotirador (V3 Intraday).

Inspirada en la operativa de alta selectividad institucional (captura rápida de
desequilibrios de liquidez en apertura de sesión con salida disciplinada).

Principios:
1. Filtro de sesión de alta liquidez:
   - Londres / Frankfurt (07:00 a 10:30 UTC) para EURUSD y DAX40.
   - Wall Street (13:30 a 16:30 UTC) para SP500 y NASDAQ100.
2. Detección de Barrido de Liquidez (Liquidity Sweep) y Absorción:
   - El precio rebasa el extremo de la última hora (Initial Balance) y presenta
     una mecha de rechazo absorptiva (rejection wick >= 35%).
3. Filtro de Calidad sin límite artificial de trades:
   - No se limita arbitrariamente a 1 trade diario. Si el mercado presenta 2, 3 o 5
     oportunidades prístinas que cumplan todos los filtros institucionales, el
     algoritmo las ejecuta. Se incluye un cooldown de seguridad entre entradas
     para evitar sobre-exposición simultánea.
4. Salida estricta por tiempo o target:
   - Se busca captura rápida de recorrido (impulso inicial) con protección de
     catástrofe temporal para no quedar atrapado en continuaciones tendenciales adversas.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SniperScalpConfig:
    symbol: str
    target_units: float
    stop_units: float
    session_start_h: int = 7
    session_end_h: int = 11
    max_holding_bars: int = 4
    min_sweep_units: float = 1.5
    min_rejection_wick: float = 0.35
    max_trades_per_day: int | None = None  # None = sin límite artificial, opera cada oportunidad válida
    cooldown_bars: int = 4                 # Barras mínimas de separación entre operaciones consecutivas
    use_h1_filter: bool = True

    def __post_init__(self):
        if self.target_units <= 0 or self.stop_units <= 0:
            raise ValueError("target_units y stop_units deben ser positivos")
        if not (0 <= self.session_start_h < self.session_end_h <= 24):
            raise ValueError("Ventana horaria inválida")
        if self.max_holding_bars < 1:
            raise ValueError("max_holding_bars debe ser >= 1")
        if not 0.0 <= self.min_rejection_wick < 1.0:
            raise ValueError("min_rejection_wick debe estar en [0, 1)")
        if self.max_trades_per_day is not None and self.max_trades_per_day < 1:
            raise ValueError("max_trades_per_day debe ser >= 1 o None")
        if self.cooldown_bars < 1:
            raise ValueError("cooldown_bars debe ser >= 1")


def compute_sniper_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula indicadores causales de microestructura en barras M5 o M15."""
    out = df.copy()
    c, h, l, o = out["Close"], out["High"], out["Low"], out["Open"]

    # Rango de vela y mechas de rechazo
    rng = (h - l).replace(0.0, np.nan)
    out["clv"] = ((c - l) / rng).fillna(0.5)
    out["lower_wick"] = ((np.minimum(o, c) - l) / rng).fillna(0.0)
    out["upper_wick"] = ((h - np.maximum(o, c)) / rng).fillna(0.0)

    # Extremos de la última hora (12 barras en M5, 4 barras en M15) con shift causal
    n_lookback = 12
    out["recent_high"] = h.shift(1).rolling(n_lookback, min_periods=4).max()
    out["recent_low"] = l.shift(1).rolling(n_lookback, min_periods=4).min()

    # Horas UTC y fecha
    out["hour_utc"] = out.index.hour
    out["minute_utc"] = out.index.minute
    out["date"] = out.index.date

    return out


def generate_sniper_signals(df: pd.DataFrame, cfg: SniperScalpConfig) -> pd.DataFrame:
    """Genera señales causales (-1, 0, 1) hilando fino en las mejores oportunidades del día."""
    ind = compute_sniper_indicators(df)
    n = len(ind)
    signals = np.zeros(n, dtype=int)

    h = ind["High"].to_numpy(dtype=float)
    l = ind["Low"].to_numpy(dtype=float)
    lower_wick = ind["lower_wick"].to_numpy(dtype=float)
    upper_wick = ind["upper_wick"].to_numpy(dtype=float)
    clv = ind["clv"].to_numpy(dtype=float)
    recent_hi = ind["recent_high"].to_numpy(dtype=float)
    recent_lo = ind["recent_low"].to_numpy(dtype=float)
    hours = ind["hour_utc"].to_numpy(dtype=int)
    dates = ind["date"].to_numpy()

    # Multiplicador de unidades a precio
    if cfg.symbol == "EURUSD":
        unit = 0.00010
    else:
        unit = 1.0
    sweep_dist = cfg.min_sweep_units * unit

    h1_trend = ind["h1_trend"].to_numpy(dtype=int) if "h1_trend" in ind.columns else np.zeros(n, dtype=int)

    trades_today = 0
    current_date = None
    last_signal_idx = -cfg.cooldown_bars

    for i in range(15, n):
        d = dates[i]
        if d != current_date:
            current_date = d
            trades_today = 0

        # Filtro de cuota diaria opcional
        if cfg.max_trades_per_day is not None and trades_today >= cfg.max_trades_per_day:
            continue

        # Cooldown para no disparar sobre la misma posición abierta
        if (i - last_signal_idx) < cfg.cooldown_bars:
            continue

        # Filtro de sesión de liquidez
        hr = hours[i]
        if not (cfg.session_start_h <= hr <= cfg.session_end_h):
            continue

        trend_ok_long = (h1_trend[i] >= 0) if cfg.use_h1_filter else True
        trend_ok_short = (h1_trend[i] <= 0) if cfg.use_h1_filter else True

        # Señal LONG: Barrido de soporte con absorción compradora
        swept_low = l[i] <= (recent_lo[i] - sweep_dist)
        long_cond = swept_low and (lower_wick[i] >= cfg.min_rejection_wick) and (clv[i] >= 0.40) and trend_ok_long

        # Señal SHORT: Barrido de resistencia con absorción vendedora
        swept_high = h[i] >= (recent_hi[i] + sweep_dist)
        short_cond = swept_high and (upper_wick[i] >= cfg.min_rejection_wick) and (clv[i] <= 0.60) and trend_ok_short

        if long_cond and not short_cond:
            signals[i] = 1
            trades_today += 1
            last_signal_idx = i
        elif short_cond and not long_cond:
            signals[i] = -1
            trades_today += 1
            last_signal_idx = i

    out = ind.copy()
    out["signal"] = signals
    return out
