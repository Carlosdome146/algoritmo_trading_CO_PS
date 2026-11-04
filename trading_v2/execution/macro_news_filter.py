"""Filtro de Noticias Macroeconómicas de Alto Impacto (Macro News Blackout).

Protege la cuenta frente a volatilidad extrema, deslizamiento (slippage) y
ensanchamiento anómalo del spread durante eventos Tier-1 (NFP, IPC, FOMC, BCE, ISM).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class MacroEvent:
    name: str
    currency: str
    time_utc: datetime
    impact: str = "HIGH"


SYMBOL_CURRENCIES: dict[str, set[str]] = {
    "EURUSD": {"EUR", "USD"},
    "GERMANY40": {"EUR"},
    "DE40": {"EUR"},
    "[IBEX35]": {"EUR"},
    "IBEX35": {"EUR"},
    "[SP500]": {"USD"},
    "US500": {"USD"},
    "US100": {"USD"},
    "USTEC": {"USD"},
    "[DJI30]": {"USD"},
    "US30": {"USD"},
    "GOLD": {"USD"},
    "XAUUSD": {"USD"},
}


def get_symbol_currencies(symbol: str) -> set[str]:
    """Devuelve las divisas macroeconómicas relevantes para un símbolo dado."""
    if symbol in SYMBOL_CURRENCIES:
        return set(SYMBOL_CURRENCIES[symbol])
    s = symbol.upper()
    currs = set()
    if "EUR" in s or "GER" in s or "DE40" in s or "IBEX" in s:
        currs.add("EUR")
    if "USD" in s or "SP500" in s or "US" in s or "DJ" in s or "GOLD" in s or "XAU" in s:
        currs.add("USD")
    if "GBP" in s or "UK100" in s:
        currs.add("GBP")
    return currs or {"USD", "EUR"}


def _first_business_day(year: int, month: int) -> date:
    d = date(year, month, 1)
    while d.weekday() >= 5:  # Sábado (5) o Domingo (6)
        d += timedelta(days=1)
    return d


def _nth_business_day(year: int, month: int, n: int) -> date:
    d = date(year, month, 1)
    b_count = 0
    while True:
        if d.weekday() < 5:
            b_count += 1
            if b_count == n:
                return d
        d += timedelta(days=1)


def _first_friday_of_month(year: int, month: int) -> date:
    d = date(year, month, 1)
    while d.weekday() != 4:  # 4 = Viernes
        d += timedelta(days=1)
    return d


class MacroNewsFilter:
    """Detector causal de ventanas de apagón de noticias de alto impacto."""

    def __init__(
        self,
        blackout_before_m: int = 15,
        blackout_after_m: int = 15,
        calendar_file: Path | str | None = None,
        custom_events: list[MacroEvent] | None = None,
    ):
        self.blackout_before = timedelta(minutes=blackout_before_m)
        self.blackout_after = timedelta(minutes=blackout_after_m)
        self.calendar_file = Path(calendar_file) if calendar_file else None
        self.custom_events: list[MacroEvent] = list(custom_events or [])
        self._loaded_file_events: list[MacroEvent] = []
        if self.calendar_file and self.calendar_file.exists():
            self._load_from_file(self.calendar_file)

    def _load_from_file(self, path: Path) -> None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            events = []
            for item in data:
                t_str = item.get("time_utc")
                dt = datetime.fromisoformat(t_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                events.append(
                    MacroEvent(
                        name=item.get("name", "Evento Macro"),
                        currency=item.get("currency", "USD").upper(),
                        time_utc=dt,
                        impact=item.get("impact", "HIGH").upper(),
                    )
                )
            self._loaded_file_events = events
        except Exception:
            self._loaded_file_events = []

    def add_custom_event(self, event: MacroEvent) -> None:
        self.custom_events.append(event)

    def generate_scheduled_events(self, year: int, month: int) -> list[MacroEvent]:
        """Genera el calendario programado de los principales informes macroeconómicos recurrentes."""
        events: list[MacroEvent] = []

        # 1. US NFP (Non-Farm Payrolls) & Desempleo: 1er Viernes de mes (13:30 UTC / 12:30 EDT)
        nfp_day = _first_friday_of_month(year, month)
        # Aproximación horaria estándar (13:30 UTC)
        events.append(
            MacroEvent(
                name="US Non-Farm Payrolls & Unemployment Rate",
                currency="USD",
                time_utc=datetime(nfp_day.year, nfp_day.month, nfp_day.day, 13, 30, tzinfo=timezone.utc),
            )
        )

        # 2. US ISM Manufacturing PMI: 1er día hábil del mes a las 15:00 UTC (14:00 UTC en horario verano)
        ism_mfg_day = _first_business_day(year, month)
        events.append(
            MacroEvent(
                name="US ISM Manufacturing PMI",
                currency="USD",
                time_utc=datetime(ism_mfg_day.year, ism_mfg_day.month, ism_mfg_day.day, 15, 0, tzinfo=timezone.utc),
            )
        )

        # 3. US ISM Services PMI: 3er día hábil del mes a las 15:00 UTC
        ism_srv_day = _nth_business_day(year, month, 3)
        events.append(
            MacroEvent(
                name="US ISM Services PMI",
                currency="USD",
                time_utc=datetime(ism_srv_day.year, ism_srv_day.month, ism_srv_day.day, 15, 0, tzinfo=timezone.utc),
            )
        )

        # 4. US CPI (Índice de Precios al Consumidor): Habitualmente segundo miércoles de mes (aprox día 10-15)
        # Determinamos el 2º miércoles
        cpi_day = date(year, month, 1)
        wed_count = 0
        while wed_count < 2:
            if cpi_day.weekday() == 2:  # Miércoles
                wed_count += 1
                if wed_count == 2:
                    break
            cpi_day += timedelta(days=1)
        events.append(
            MacroEvent(
                name="US Consumer Price Index (CPI)",
                currency="USD",
                time_utc=datetime(cpi_day.year, cpi_day.month, cpi_day.day, 13, 30, tzinfo=timezone.utc),
            )
        )

        # 5. Eurozone Flash CPI / PMI (Aproximadamente día 22 de cada mes a las 09:00 UTC)
        ez_pmi_day = date(year, month, 22)
        if ez_pmi_day.weekday() >= 5:
            ez_pmi_day += timedelta(days=(7 - ez_pmi_day.weekday()))
        events.append(
            MacroEvent(
                name="Eurozone Flash PMI Composite",
                currency="EUR",
                time_utc=datetime(ez_pmi_day.year, ez_pmi_day.month, ez_pmi_day.day, 9, 0, tzinfo=timezone.utc),
            )
        )

        return events

    def get_events_for_window(self, start_dt: datetime, end_dt: datetime) -> list[MacroEvent]:
        """Obtiene todos los eventos macro programados o cargados que caigan en la ventana temporal."""
        all_events: list[MacroEvent] = []
        all_events.extend(self.custom_events)
        all_events.extend(self._loaded_file_events)

        # Añadir eventos calculados algorítmicamente para los meses cubiertos
        y_m_set = {(start_dt.year, start_dt.month), (end_dt.year, end_dt.month)}
        for y, m in y_m_set:
            all_events.extend(self.generate_scheduled_events(y, m))

        filtered = [
            ev for ev in all_events
            if ev.impact == "HIGH" and (start_dt <= ev.time_utc <= end_dt)
        ]
        return filtered

    def is_blackout_active(
        self,
        symbol: str,
        now_utc: datetime,
    ) -> tuple[bool, str | None]:
        """Comprueba si un símbolo está en ventana de apagón por una noticia inminente o recién publicada.

        Devuelve:
            (True, mensaje_motivo) si está bloqueado.
            (False, None) si no hay noticias que afecten al símbolo en este momento.
        """
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)

        target_currencies = get_symbol_currencies(symbol)
        search_start = now_utc - self.blackout_after - timedelta(hours=1)
        search_end = now_utc + self.blackout_before + timedelta(hours=1)

        events = self.get_events_for_window(search_start, search_end)

        for ev in events:
            if ev.currency not in target_currencies:
                continue

            window_start = ev.time_utc - self.blackout_before
            window_end = ev.time_utc + self.blackout_after

            if window_start <= now_utc <= window_end:
                diff_m = int(round((ev.time_utc - now_utc).total_seconds() / 60.0))
                if diff_m > 0:
                    timing_str = f"en {diff_m} min"
                elif diff_m < 0:
                    timing_str = f"hace {abs(diff_m)} min"
                else:
                    timing_str = "ahora mismo"

                reason = (
                    f"BLACKOUT NOTICIA TIER-1: [{ev.currency}] '{ev.name}' ({timing_str}, a las "
                    f"{ev.time_utc.strftime('%H:%M')} UTC). Ventana protegida: ±{int(self.blackout_before.total_seconds() // 60)}m"
                )
                return True, reason

        return False, None
