"""Estrategias V2: señales offline en velas cerradas."""
from .candidates import STRATEGIES, generate_signals
from .micro_scalping import (
    SniperScalpConfig,
    compute_sniper_indicators,
    generate_sniper_signals,
)

__all__ = [
    "STRATEGIES",
    "generate_signals",
    "SniperScalpConfig",
    "compute_sniper_indicators",
    "generate_sniper_signals",
]
