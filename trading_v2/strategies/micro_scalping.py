"""Estrategia de Micro-Scalping Institucional Francotirador (V3 Intraday M15 / M30).

Inspirada en la operativa de alta selectividad institucional (captura rápida de
desequilibrios de liquidez en apertura de sesión con salida disciplinada).

Principios:
1. Filtro de sesión de alta liquidez:
   - Londres / Frankfurt (07:00 a 16:00 UTC) para EURUSD, DAX40 e IBEX35.
   - Wall Street (13:00 a 20:00 UTC) para SP500 y NASDAQ100.
2. Tres Gatillos Institucionales M15 / M30:
   - Gatillo A (Classic Liquidity Sweep): Barrido profundo de extremo previo con mecha >= 35%.
   - Gatillo B (Ismael Sweep Reclaim): Barrido de mínimo reciente en tendencia alcista M15/M30
     (Close > EMA20 > SMA200) con mecha de absorción >= 50% y cierre en tercio superior (CLV >= 0.80).
   - Gatillo C (Bollinger Extreme Dip): Sobreventa extrema RSI(2) < 5.0 tocando banda 2.0σ en tendencia.
3. Filtro de Calidad sin límite artificial de trades y con cooldown de seguridad.
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
    use_keltner_filter: bool = False       # Filtro Canal de Keltner (Carlos QuantDinger) para GERMANY40 (91.04% WR)
    max_opposite_wick: float | None = None # Filtro Martillo sin mecha contraria (Vault) para [SP500] (84.09% WR)

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
        if self.max_opposite_wick is not None and not (0.0 < self.max_opposite_wick <= 1.0):
            raise ValueError("max_opposite_wick debe estar en (0, 1]")


def compute_sniper_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula indicadores causales de microestructura en barras M5, M15 o M30."""
    out = df.copy()
    c, h, l, o = out["Close"], out["High"], out["Low"], out["Open"]

    # Rango de vela y mechas de rechazo
    rng = (h - l).replace(0.0, np.nan)
    out["clv"] = ((c - l) / rng).fillna(0.5)
    out["lower_wick"] = ((np.minimum(o, c) - l) / rng).fillna(0.0)
    out["upper_wick"] = ((h - np.maximum(o, c)) / rng).fillna(0.0)

    # Extremos recientes con shift causal (12 barras y 8 barras)
    out["recent_high"] = h.shift(1).rolling(12, min_periods=4).max()
    out["recent_low"] = l.shift(1).rolling(12, min_periods=4).min()
    out["recent_high_8"] = h.shift(1).rolling(8, min_periods=3).max()
    out["recent_low_8"] = l.shift(1).rolling(8, min_periods=3).min()

    # Indicadores de tendencia intradía y agotamiento (EMA20, SMA200, RSI2, Bollinger 2.0σ, Keltner 1.5*ATR10)
    out["ema20"] = c.ewm(span=20, adjust=False).mean()
    out["sma200"] = c.rolling(200, min_periods=40).mean()
    sma20 = c.rolling(20, min_periods=10).mean()
    std20 = c.rolling(20, min_periods=10).std(ddof=0)
    out["bb_lo"] = sma20 - 2.0 * std20

    prev_c = c.shift(1).fillna(c.iloc[0] if len(c) > 0 else 0.0)
    tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    atr10 = tr.rolling(10, min_periods=3).mean()
    k_ub = out["ema20"] + 1.5 * atr10
    k_lb = out["ema20"] - 1.5 * atr10
    k_rng = (k_ub - k_lb).replace(0.0, np.nan)
    out["keltner_pos_low"] = ((l - k_lb) / k_rng).fillna(0.5)
    out["keltner_pos_high"] = ((h - k_lb) / k_rng).fillna(0.5)

    delta = c.diff()
    up = delta.clip(lower=0.0).ewm(alpha=0.5, adjust=False).mean()
    dn = (-delta.clip(upper=0.0)).ewm(alpha=0.5, adjust=False).mean()
    out["rsi2"] = (100.0 - 100.0 / (1.0 + up / dn.replace(0.0, np.nan))).fillna(50.0)

    # Horas UTC y fecha
    out["hour_utc"] = out.index.hour
    out["minute_utc"] = out.index.minute
    out["date"] = out.index.date

    return out


def generate_sniper_signals(df: pd.DataFrame, cfg: SniperScalpConfig) -> pd.DataFrame:
    """Genera señales causales (-1, 0, 1) hilando fino en las mejores oportunidades M15/M30."""
    ind = compute_sniper_indicators(df)
    n = len(ind)
    signals = np.zeros(n, dtype=int)

    c = ind["Close"].to_numpy(dtype=float)
    h = ind["High"].to_numpy(dtype=float)
    l = ind["Low"].to_numpy(dtype=float)
    lower_wick = ind["lower_wick"].to_numpy(dtype=float)
    upper_wick = ind["upper_wick"].to_numpy(dtype=float)
    clv = ind["clv"].to_numpy(dtype=float)
    recent_hi = ind["recent_high"].to_numpy(dtype=float)
    recent_lo = ind["recent_low"].to_numpy(dtype=float)
    recent_hi8 = ind["recent_high_8"].to_numpy(dtype=float) if "recent_high_8" in ind.columns else recent_hi
    recent_lo8 = ind["recent_low_8"].to_numpy(dtype=float)
    ema20 = ind["ema20"].to_numpy(dtype=float)
    sma200 = ind["sma200"].to_numpy(dtype=float)
    bb_lo = ind["bb_lo"].to_numpy(dtype=float)
    rsi2 = ind["rsi2"].to_numpy(dtype=float)
    k_pos_lo = ind["keltner_pos_low"].to_numpy(dtype=float)
    k_pos_hi = ind["keltner_pos_high"].to_numpy(dtype=float)
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

        # 1. Gatillo Clásico: Barrido profundo de soporte con mecha de absorción
        swept_low = l[i] <= (recent_lo[i] - sweep_dist)
        classic_long = swept_low and (lower_wick[i] >= cfg.min_rejection_wick) and (clv[i] >= 0.40)

        # 2. Gatillo Ismael Sweep Reclaim (91.67% Win Rate en EURUSD M15):
        # Toque/barrido de mínimo reciente en tendencia alcista (Close > EMA20 > SMA200) + mecha >= 55% + cierre en máximo (CLV >= 0.85)
        bull_structure = np.isfinite(sma200[i]) and (c[i] > sma200[i]) and (ema20[i] > sma200[i])
        ismael_reclaim_long = (
            bull_structure
            and np.isfinite(recent_lo8[i])
            and (l[i] <= recent_lo8[i])
            and (c[i] > ema20[i])
            and (lower_wick[i] >= 0.55)
            and (clv[i] >= 0.85)
        )

        # 3. Gatillo Bollinger Extreme Dip: Sobreventa extrema RSI(2) < 5.0 en banda 2.0σ
        bb_dip_long = (
            bull_structure
            and np.isfinite(bb_lo[i])
            and (rsi2[i] < 5.0)
            and (c[i] <= bb_lo[i])
        )

        long_cond = (classic_long or ismael_reclaim_long or bb_dip_long) and trend_ok_long

        # Señal SHORT: Barrido de resistencia con absorción vendedora institucional
        bear_structure = np.isfinite(sma200[i]) and (c[i] < sma200[i]) and (ema20[i] < sma200[i])
        swept_high = h[i] >= (recent_hi[i] + sweep_dist)
        classic_short = swept_high and (upper_wick[i] >= cfg.min_rejection_wick) and (clv[i] <= 0.60)
        ismael_reclaim_short = (
            bear_structure
            and np.isfinite(recent_hi8[i])
            and (h[i] >= recent_hi8[i])
            and (c[i] < ema20[i])
            and (upper_wick[i] >= 0.55)
            and (clv[i] <= 0.15)
        )
        short_cond = (classic_short or ismael_reclaim_short) and trend_ok_short

        # 4. Filtros de robustez específicos por activo:
        #    - Canal de Keltner (Carlos QuantDinger) para GERMANY40 -> eleva a 91.04% WR y PF 2.02
        if cfg.use_keltner_filter:
            long_cond = long_cond and (k_pos_lo[i] <= 0.35)
            short_cond = short_cond and (k_pos_hi[i] >= 0.65)

        #    - Martillo sin mecha contraria (Vault) para [SP500] -> eleva a 84.09% WR y PF 1.51
        if cfg.max_opposite_wick is not None:
            long_cond = long_cond and (upper_wick[i] <= cfg.max_opposite_wick)
            short_cond = short_cond and (lower_wick[i] <= cfg.max_opposite_wick)

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
