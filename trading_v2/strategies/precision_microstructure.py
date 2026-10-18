"""Microestructura institucional y estrategias de alta tasa de acierto (V2 Offline).

Calcula variables de microestructura 100% causales (VWAP intradía, agotamiento
de rango diario ADR_14 con shift(1) de días completos, Close Location Value CLV,
mechas de rechazo, Ratio de Eficiencia de Kaufman ER20, Variance Ratio VR4 y
fuerza estructural H1 usando exclusivamente velas H1 cerradas).
"""
from __future__ import annotations
from typing import Literal
import numpy as np
import pandas as pd
from scripts import investigar_admirals_v2 as prior

PRECISION_STRATEGIES = (
    "institutional_vwap_pullback",
    "bollinger_regime_reversion",
    "adr_exhaustion_fade",
    "opening_impulse_breakout",
)
PrecisionStrategyName = Literal[
    "institutional_vwap_pullback",
    "bollinger_regime_reversion",
    "adr_exhaustion_fade",
    "opening_impulse_breakout",
]

PRECISION_FEATURES = (
    "dir_ema_gap",
    "dir_close_ema",
    "dir_rsi",
    "dir_clv",
    "dir_z_vwap",
    "dir_bb_z",
    "dir_ret2",
    "dir_ret4",
    "dir_h1_trend",
    "dir_h1_ret3",
    "atr_ratio",
    "spread_atr",
    "er20",
    "vr4",
    "rvol",
    "adr_used",
)


def enrich_microstructure_features(
    m15: pd.DataFrame,
    h1: pd.DataFrame,
    point: float,
    cross_market_closes: dict[str, pd.Series] | None = None,
) -> pd.DataFrame:
    """Enriquece el DataFrame M15 con indicadores de microestructura y régimen sin sesgo de futuro.

    Cada fila i depende únicamente de velas M15 cerradas <= i y velas H1 cuyo
    instante de cierre (open_time + 1h) sea <= al cierre de la vela M15 (open_time + 15m).
    """
    if point <= 0:
        raise ValueError("point debe ser positivo")

    b = prior.causal_indicators(m15, h1)
    c = b["Close"].astype(float)
    o = b["Open"].astype(float)
    hi = b["High"].astype(float)
    lo = b["Low"].astype(float)
    atr = b["atr"].astype(float).replace(0.0, np.nan)
    rng = (hi - lo).replace(0.0, np.nan)

    # 1. Coste relativo Spread/ATR y régimen de liquidez / choque
    b["spread_atr"] = (b["Spread"].astype(float) * point) / atr
    med_spr = b["Spread"].astype(float).rolling(96, min_periods=20).median().replace(0.0, np.nan)
    b["spread_rel"] = b["Spread"].astype(float) / med_spr
    b["bar_range_atr"] = (hi - lo) / atr

    # 2. Anatomía de la vela de señal (Close Location Value y mechas de rechazo)
    b["clv"] = ((c - lo) / rng).fillna(0.5)
    b["lower_wick_ratio"] = ((np.minimum(o, c) - lo) / rng).fillna(0.0)
    b["upper_wick_ratio"] = ((hi - np.maximum(o, c)) / rng).fillna(0.0)
    b["body_atr"] = (c - o) / atr

    # 3. VWAP intradía causal (acumulado desde el inicio del día hasta la barra i inclusive)
    typ = (hi + lo + c) / 3.0
    if "TickVolume" in m15.columns:
        vol = pd.to_numeric(m15["TickVolume"], errors="coerce").reindex(b.index).fillna(1.0).clip(lower=1.0)
    else:
        vol = pd.Series(1.0, index=b.index, dtype=float)
    day_key = b.index.floor("D")
    pv_cum = (typ * vol).groupby(day_key).cumsum()
    v_cum = vol.groupby(day_key).cumsum().replace(0.0, np.nan)
    b["vwap"] = pv_cum / v_cum
    b["z_vwap"] = (c - b["vwap"]) / atr
    vol_sma = vol.rolling(20, min_periods=5).mean().replace(0.0, np.nan)
    b["rvol"] = (vol / vol_sma).fillna(1.0)

    # 4. Consumo de rango diario ADR_14 estrictamente causal:
    # El ADR_14 del día D se calcula SOLO con los 14 días completados previos (shift(1)),
    # y el rango usado hoy hasta la barra i usa cummax(High) - cummin(Low) dentro del día D.
    daily_hi = hi.groupby(day_key).max()
    daily_lo = lo.groupby(day_key).min()
    prev_adr14 = (daily_hi - daily_lo).rolling(14, min_periods=3).mean().shift(1)
    mapped_adr = pd.Series(day_key.map(prev_adr14), index=b.index, dtype=float)
    b["adr14"] = mapped_adr.replace(0.0, np.nan)
    today_hi_so_far = hi.groupby(day_key).cummax()
    today_lo_so_far = lo.groupby(day_key).cummin()
    b["adr_used"] = ((today_hi_so_far - today_lo_so_far) / b["adr14"]).fillna(0.5)

    # 5. Indicadores estadísticos de régimen: Kaufman Efficiency Ratio (ER20), Variance Ratio (VR4), Bollinger Z
    net_move = (c - c.shift(20)).abs()
    sum_moves = c.diff().abs().rolling(20, min_periods=20).sum().replace(0.0, np.nan)
    b["er20"] = net_move / sum_moves

    log_ret1 = np.log(c / c.shift(1).replace(0.0, np.nan))
    log_ret4 = np.log(c / c.shift(4).replace(0.0, np.nan))
    var1 = log_ret1.rolling(24, min_periods=24).var()
    var4 = log_ret4.rolling(24, min_periods=24).var()
    b["vr4"] = (var4 / (4.0 * var1.replace(0.0, np.nan))).fillna(1.0)

    bb_mid = c.rolling(20, min_periods=20).mean()
    bb_std = c.rolling(20, min_periods=20).std(ddof=0).replace(0.0, np.nan)
    b["bb_z"] = (c - bb_mid) / bb_std
    b["z_ema20"] = (c - b["ema20"]) / atr
    b["z_ema50"] = (c - b["ema50"]) / atr
    b["ret2_atr"] = (c - c.shift(2)) / atr
    b["ret4_atr"] = (c - c.shift(4)) / atr
    b["ret8_atr"] = (c - c.shift(8)) / atr

    # 6. Fuerza estructural H1 usando EXCLUSIVAMENTE velas H1 cerradas
    h = h1.copy()
    h_close = h["Close"].astype(float)
    h["ema20"] = h_close.ewm(span=20, adjust=False).mean()
    h["ema50"] = h_close.ewm(span=50, adjust=False).mean()
    h_prev = h_close.shift(1)
    h_tr = pd.concat(
        [h["High"] - h["Low"], (h["High"] - h_prev).abs(), (h["Low"] - h_prev).abs()],
        axis=1,
    ).max(axis=1)
    h["h1_atr"] = h_tr.rolling(14, min_periods=14).mean().replace(0.0, np.nan)
    h["h1_trend_z"] = (h["ema20"] - h["ema50"]) / h["h1_atr"]
    h["h1_ret3"] = (h_close - h_close.shift(3)) / h["h1_atr"]
    h["close_time"] = h.index + pd.Timedelta(hours=1)

    sig_close = pd.DataFrame(
        {"signal_close": b.index + pd.Timedelta(minutes=15), "row": np.arange(len(b))}
    )
    aligned = pd.merge_asof(
        sig_close.sort_values("signal_close"),
        h[["close_time", "h1_trend_z", "h1_ret3"]].reset_index(drop=True).sort_values("close_time"),
        left_on="signal_close",
        right_on="close_time",
        direction="backward",
    ).sort_values("row")
    b["h1_trend_z"] = aligned["h1_trend_z"].to_numpy(dtype=float)
    b["h1_ret3"] = aligned["h1_ret3"].to_numpy(dtype=float)

    hour = pd.Series(b.index.hour, index=b.index, dtype=float)
    b["hour_sin"] = np.sin(2.0 * np.pi * hour / 24.0)
    b["hour_cos"] = np.cos(2.0 * np.pi * hour / 24.0)

    # 7. Confirmación intermercado opcional (si se pasan los cierres de otros activos)
    if cross_market_closes:
        cross_rets = []
        for other_close in cross_market_closes.values():
            aligned_c = other_close.reindex(b.index).ffill()
            r4 = aligned_c.pct_change(4)
            cross_rets.append(r4)
        b["cross_market_ret4"] = pd.concat(cross_rets, axis=1).mean(axis=1).fillna(0.0)
    else:
        b["cross_market_ret4"] = 0.0

    return b.replace([np.inf, -np.inf], np.nan)


def _attach_directional_features(b: pd.DataFrame) -> pd.DataFrame:
    """Alinea el signo de los indicadores direccionales con el sentido de la señal (+1 LONG, -1 SHORT).

    Esto evita que un clasificador lineal (LogisticRegression / Ridge) cancele los pesos
    de compras y ventas entre sí.
    """
    d = b["signal"].astype(float)
    b["dir_ema_gap"] = b["ema_gap_atr"] * d
    b["dir_close_ema"] = b["close_ema_atr"] * d
    b["dir_rsi"] = (b["rsi"] - 50.0) * d
    b["dir_clv"] = (b["clv"] - 0.5) * d
    b["dir_z_vwap"] = b["z_vwap"] * d
    b["dir_bb_z"] = b["bb_z"] * d
    b["dir_ret2"] = b["ret2_atr"] * d
    b["dir_ret4"] = b["ret4_atr"] * d
    b["dir_h1_trend"] = b["h1_trend_z"] * d
    b["dir_h1_ret3"] = b["h1_ret3"] * d
    return b


def generate_precision_signals(
    enriched_base: pd.DataFrame,
    strategy: str,
    point: float,
) -> pd.DataFrame:
    """Genera señales M15 causales para las familias de precisión y construye PRECISION_FEATURES."""
    if strategy not in PRECISION_STRATEGIES:
        raise ValueError(f"Estrategia de precisión desconocida: {strategy}")
    if point <= 0:
        raise ValueError("point debe ser positivo")

    required = {
        "Open", "High", "Low", "Close", "Spread", "atr", "atr_ratio", "rsi",
        "ema20", "ema50", "h1_direction", "h1_trend_z", "h1_ret3", "spread_atr",
        "spread_rel", "bar_range_atr", "clv", "lower_wick_ratio", "upper_wick_ratio",
        "z_vwap", "bb_z", "z_ema20", "er20", "vr4", "rvol", "adr_used", "ret2_atr", "ret4_atr",
    }
    if not required.issubset(enriched_base.columns):
        missing = sorted(required - set(enriched_base.columns))
        raise ValueError(f"Faltan columnas de microestructura: {missing}")

    b = enriched_base.copy()

    # Filtro causal de sesión líquida y veto de barras de choque (Shock Veto)
    spr_q = 0.65 if strategy == "institutional_vwap_pullback" else 0.70
    spr_rel_max = 1.20 if strategy == "institutional_vwap_pullback" else 1.22
    q_spr = b["spread_atr"].rolling(192, min_periods=40).quantile(spr_q)
    liquid = (
        b["atr"].notna()
        & (b["atr"] > 0)
        & (b["Spread"] > 0)
        & (b["spread_rel"] <= spr_rel_max)
        & (b["spread_atr"] <= q_spr)
        & (b["bar_range_atr"] <= 2.5)
        & b["h1_direction"].notna()
        & b["h1_trend_z"].notna()
    )

    b["signal"] = 0
    if strategy == "institutional_vwap_pullback":
        # Pullback institucional hacia EMA20/VWAP a favor de H1 o reversión en rango con cierre comprador/vendedor
        buy = liquid & (
            (
                (b["h1_direction"] == 1)
                & ((b["z_ema20"] <= -0.10) | (b["z_vwap"] <= -0.30))
                & b["rsi"].between(32.0, 54.0)
                & (b["clv"] >= 0.48)
            )
            | (
                (b["h1_trend_z"] >= -0.50)
                & (b["bb_z"] <= -1.40)
                & (b["rsi"] <= 38.0)
                & (b["clv"] >= 0.45)
            )
        )
        sell = liquid & (
            (
                (b["h1_direction"] == -1)
                & ((b["z_ema20"] >= 0.10) | (b["z_vwap"] >= 0.30))
                & b["rsi"].between(46.0, 68.0)
                & (b["clv"] <= 0.52)
            )
            | (
                (b["h1_trend_z"] <= 0.50)
                & (b["bb_z"] >= 1.40)
                & (b["rsi"] >= 62.0)
                & (b["clv"] <= 0.55)
            )
        )
    elif strategy == "bollinger_regime_reversion":
        # Reversión estadística en bandas de Bollinger con veto de tendencia H1 contraria fuerte
        buy = (
            liquid
            & (b["bb_z"] <= -1.25)
            & (b["rsi"] <= 42.0)
            & (b["h1_trend_z"] >= -0.85)
            & ((b["clv"] >= 0.42) | (b["lower_wick_ratio"] >= 0.25))
        )
        sell = (
            liquid
            & (b["bb_z"] >= 1.25)
            & (b["rsi"] >= 58.0)
            & (b["h1_trend_z"] <= 0.85)
            & ((b["clv"] <= 0.58) | (b["upper_wick_ratio"] >= 0.25))
        )
    elif strategy == "adr_exhaustion_fade":
        # Agotamiento intradía respecto al VWAP con protección estructural H1
        buy = (
            liquid
            & (b["z_vwap"] <= -0.90)
            & (b["rsi"] <= 42.0)
            & (b["h1_trend_z"] >= -0.90)
            & (b["clv"] >= 0.42)
        )
        sell = (
            liquid
            & (b["z_vwap"] >= 0.90)
            & (b["rsi"] >= 58.0)
            & (b["h1_trend_z"] <= 0.90)
            & (b["clv"] <= 0.58)
        )
    else:  # opening_impulse_breakout
        # Continuación de impulso limpio cuando el Ratio de Eficiencia de Kaufman confirma direccionalidad
        buy = (
            liquid
            & (b["h1_direction"] == 1)
            & (b["ret4_atr"] > 0.35)
            & (b["clv"] >= 0.60)
            & (b["er20"] >= 0.24)
            & (b["adr_used"] <= 0.85)
        )
        sell = (
            liquid
            & (b["h1_direction"] == -1)
            & (b["ret4_atr"] < -0.35)
            & (b["clv"] <= 0.40)
            & (b["er20"] >= 0.24)
            & (b["adr_used"] <= 0.85)
        )

    buy_mask = buy.fillna(False)
    sell_mask = sell.fillna(False) & ~buy_mask
    b.loc[buy_mask, "signal"] = 1
    b.loc[sell_mask, "signal"] = -1
    b["direction"] = b["signal"].astype(int)
    return _attach_directional_features(b)
