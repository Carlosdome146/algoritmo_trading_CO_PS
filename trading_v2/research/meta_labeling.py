"""Módulo de Meta-Labeling Cuantitativo y Sincronía Intermercado (inspirado en MLFinLab / FreqAI).

Desacopla la dirección de la apuesta (Modelo Primario: ¿Long o Short?) de la convicción
y el dimensionamiento dinámico del riesgo (Modelo Secundario / Meta-Modelo: ¿Qué probabilidad
de éxito tiene esta señal según la sincronía intermercado y la microestructura?).

Referencias técnicas:
- Marcos López de Prado, 'Advances in Financial Machine Learning' (Capítulo 3: Meta-Labeling).
- Freqtrade / FreqAI & Microsoft Qlib: Ponderación dinámica por confluencia multi-activo.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class AssetRegimeSnapshot:
    """Instantánea causal del estado técnico de un activo para evaluación intermercado."""
    symbol: str
    close: float
    sma200: float
    rsi2: float
    ibs: float
    z_bollinger: float  # Estiramiento en desviaciones estándar respecto a SMA20

    @property
    def is_bull_regime(self) -> bool:
        return self.close > self.sma200 and self.sma200 > 0

    @property
    def is_pullback(self) -> bool:
        return self.rsi2 < 25.0


@dataclass(frozen=True)
class MetaLabelResult:
    """Resultado de la auditoría secundaria de Meta-Labeling sobre una señal primaria."""
    symbol: str
    side: int  # 1 = LONG, -1 = SHORT
    meta_score: float  # Puntuación de 0.0 a 100.0
    tier: Literal["HIGH_CONVICTION", "STANDARD", "LOW_CONVICTION_VETO"]
    risk_multiplier: float  # Multiplicador sobre el riesgo base (ej. 1.25x, 0.75x, 0.0x)
    bull_peers_count: int
    sync_pullback_count: int
    reasons: tuple[str, ...]


def evaluate_meta_label(
    target: AssetRegimeSnapshot,
    side: int,
    peer_snapshots: list[AssetRegimeSnapshot] | None = None,
    min_veto_score: float = 40.0,
    high_conviction_threshold: float = 70.0,
) -> MetaLabelResult:
    """Calcula el Meta-Score (0-100) y el multiplicador de riesgo para una señal primaria.

    Parámetros:
    - target: Instantánea causal del activo que dispara la señal.
    - side: Dirección de la señal primaria (1 para compra, -1 para venta).
    - peer_snapshots: Instantáneas causales de los demás activos de la cartera en esa misma vela.
    """
    if side not in (1, -1):
        raise ValueError("side debe ser 1 (LONG) o -1 (SHORT)")

    peers = list(peer_snapshots) if peer_snapshots else []
    all_snapshots = [target] + [p for p in peers if p.symbol != target.symbol]

    score = 50.0
    reasons: list[str] = ["Base primaria validada (+50.0)"]

    # 1. Sincronía Macro Intermercado (DAX40, SP500, IBEX35)
    bull_count = sum(1 for s in all_snapshots if s.is_bull_regime)
    sync_dip_count = sum(1 for s in all_snapshots if s.is_pullback)

    if side == 1:
        if bull_count >= 3:
            score += 15.0
            reasons.append(f"Sincronía alcista global ({bull_count} índices > SMA200: +15.0)")
        elif bull_count == 2:
            score += 7.5
            reasons.append(f"Mayoría alcista intermercado ({bull_count} índices > SMA200: +7.5)")
        elif not target.is_bull_regime:
            score -= 20.0
            reasons.append("Penalización: Activo objetivo bajo SMA200 en señal LONG (-20.0)")

        if sync_dip_count >= 2:
            score += 15.0
            reasons.append(f"Sobreventa sincronizada intermercado ({sync_dip_count} activos en dip: +15.0)")

    # 2. Microestructura de vela (Internal Bar Strength - IBS)
    if side == 1 and target.ibs < 0.20:
        score += 10.0
        reasons.append(f"Cierre en extremo inferior IBS={target.ibs:.2f} < 0.20 (+10.0)")
    elif side == -1 and target.ibs > 0.80:
        score += 10.0
        reasons.append(f"Cierre en extremo superior IBS={target.ibs:.2f} > 0.80 (+10.0)")

    # 3. Estiramiento estadístico en Bandas de Bollinger
    if target.z_bollinger >= 2.0:
        score += 10.0
        reasons.append(f"Compresión extrema Bollinger Z={target.z_bollinger:.2f}σ >= 2.0σ (+10.0)")
    elif target.z_bollinger < 1.2:
        score -= 10.0
        reasons.append(f"Estiramiento débil Z={target.z_bollinger:.2f}σ < 1.2σ (-10.0)")

    score = max(0.0, min(100.0, score))

    if score < min_veto_score:
        tier: Literal["HIGH_CONVICTION", "STANDARD", "LOW_CONVICTION_VETO"] = "LOW_CONVICTION_VETO"
        mult = 0.0
    elif score >= high_conviction_threshold:
        tier = "HIGH_CONVICTION"
        mult = 1.25
    else:
        tier = "STANDARD"
        mult = 0.75

    return MetaLabelResult(
        symbol=target.symbol,
        side=side,
        meta_score=round(score, 2),
        tier=tier,
        risk_multiplier=mult,
        bull_peers_count=bull_count,
        sync_pullback_count=sync_dip_count,
        reasons=tuple(reasons),
    )
