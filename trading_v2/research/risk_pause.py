"""Control offline de pausas. Sin lógica de reanudación automática de trading.

Un resultado negativo reduce riesgo futuro pero no se usa para reentrenar
inmediatamente. La verificación del modelo debe producirse por separado.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


def get_asset_family(symbol: str) -> str:
    """Clasifica un símbolo en su familia de activo para aislamiento de riesgo."""
    sym = symbol.replace("[", "").replace("]", "").strip().upper()
    if any(fx in sym for fx in ("EUR", "USD", "GBP", "JPY", "CHF", "AUD", "NZD", "CAD")):
        return "forex"
    if any(comm in sym for comm in ("GOLD", "XAU", "OIL", "BRENT", "WTI", "SILVER")):
        return "commodities"
    return "indices"


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
    family_cooldowns: dict[str, datetime] = field(default_factory=dict)

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

    def register_closed_trade(self, pnl:float, at:datetime, symbol: str = ""):
        self._roll_day(at)
        if self.halted:
            raise RuntimeError("Sistema bloqueado: requiere revisión y rearme manual")
        self.daily_pnl+=pnl
        if pnl<0:
            self.consecutive_losses+=1
            cooldown_dt = at + timedelta(minutes=self.cooldown_minutes)
            if symbol:
                fam = get_asset_family(symbol)
                self.family_cooldowns[fam] = cooldown_dt
                self.family_cooldowns[symbol] = cooldown_dt
                self.reasons.append(f'POST_LOSS_COOLDOWN_{fam.upper()}')
            else:
                self.paused_until = cooldown_dt
                self.reasons.append('POST_LOSS_COOLDOWN')
        elif pnl>0:
            self.consecutive_losses=0
        if self.consecutive_losses>=self.max_consecutive_losses:
            self.halted=True
            self.reasons.append('CONSECUTIVE_LOSS_HALT')
        if self.daily_pnl<=-self.reference_equity*self.max_daily_loss_fraction:
            self.halted=True
            self.reasons.append('DAILY_LOSS_HALT')

    def can_open_new_trade(self, at:datetime, symbol: str = "") -> tuple[bool,str]:
        self._roll_day(at)
        if self.halted:
            return False,'HALTED_REQUIRES_MANUAL_REVIEW'
        if self.paused_until and at<self.paused_until:
            return False,'COOLDOWN'
        if symbol:
            fam = get_asset_family(symbol)
            if fam in self.family_cooldowns and at < self.family_cooldowns[fam]:
                return False, f'COOLDOWN_{fam.upper()}'
            if symbol in self.family_cooldowns and at < self.family_cooldowns[symbol]:
                return False, f'COOLDOWN_{symbol}'
        return True,'READY_FOR_OFFLINE_RESEARCH'

    def reset_halt(self, reason: str = "MANUAL_REVIEW_RESOLVED", reset_daily_pnl: bool = True):
        """Rearme manual del sistema tras investigación y resolución técnica por un operador."""
        self.halted = False
        self.consecutive_losses = 0
        self.paused_until = None
        self.family_cooldowns.clear()
        if reset_daily_pnl:
            self.daily_pnl = 0.0
        self.reasons.append(f"RESET_BY_OPERATOR: {reason}")
