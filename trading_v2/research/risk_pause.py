"""Control offline de pausas. Sin lógica de reanudación automática de trading.

Un resultado negativo reduce riesgo futuro pero no se usa para reentrenar
inmediatamente. La verificación del modelo debe producirse por separado.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


@dataclass
class RiskPause:
    cooldown_minutes: int = 60
    max_consecutive_losses: int = 3
    max_daily_loss_fraction: float = .015
    reference_equity: float = 3000.
    consecutive_losses: int = 0
    daily_pnl: float = 0.
    paused_until: datetime | None = None
    halted: bool = False
    session_day: str | None = None
    reasons: list[str] = field(default_factory=list)

    def __post_init__(self):
        if self.cooldown_minutes < 0 or self.max_consecutive_losses < 1:
            raise ValueError("Límites de pausa inválidos")
        if not 0 < self.max_daily_loss_fraction <= .1 or self.reference_equity <= 0:
            raise ValueError("Riesgo diario inválido")

    def _roll_day(self, now:datetime):
        if now.tzinfo is None:
            raise ValueError("Se requiere fecha UTC aware")
        day=now.astimezone(timezone.utc).date().isoformat()
        if day != self.session_day:
            self.session_day=day
            self.daily_pnl=0.
            # STOP por pérdidas consecutivas NO se reinicia solo al cambiar de día.

    def register_closed_trade(self, pnl:float, at:datetime):
        self._roll_day(at)
        if self.halted:
            raise RuntimeError("Sistema bloqueado: requiere revisión y rearme manual")
        self.daily_pnl+=pnl
        if pnl<0:
            self.consecutive_losses+=1
            self.paused_until=at+timedelta(minutes=self.cooldown_minutes)
            self.reasons.append('POST_LOSS_COOLDOWN')
        elif pnl>0:
            self.consecutive_losses=0
        if self.consecutive_losses>=self.max_consecutive_losses:
            self.halted=True
            self.reasons.append('CONSECUTIVE_LOSS_HALT')
        if self.daily_pnl<=-self.reference_equity*self.max_daily_loss_fraction:
            self.halted=True
            self.reasons.append('DAILY_LOSS_HALT')

    def can_open_new_trade(self, at:datetime) -> tuple[bool,str]:
        self._roll_day(at)
        if self.halted:
            return False,'HALTED_REQUIRES_MANUAL_REVIEW'
        if self.paused_until and at<self.paused_until:
            return False,'COOLDOWN'
        return True,'READY_FOR_OFFLINE_RESEARCH'
