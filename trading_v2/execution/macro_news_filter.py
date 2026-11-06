"""Filtro de Noticias Macroeconómicas de Alto Impacto (Macro News Blackout).

Protege la cuenta frente a volatilidad extrema, deslizamiento (slippage) y
ensanchamiento anómalo del spread durante eventos Tier-1 y Tier-2:
- Alemania (EUR): Producción Industrial, Balanza Comercial, IFO, ZEW, IPC Alemán, PIB.
- España (EUR): IPC Preliminar (INE), PIB España, PMI Manufacturero/Servicios.
- Eurozona y BCE (EUR): Tipos de Interés BCE, Rueda de Prensa Lagarde, IPC Flash, PIB.
- EE.UU. y Global (USD): NFP, IPC (CPI), PPI, Ventas Minoristas, PCE Core, FOMC (Fed) y Powell.
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
    country: str = "GLOBAL"  # "DE", "ES", "EU", "US", "GLOBAL"


SYMBOL_CURRENCIES: dict[str, set[str]] = {
    "EURUSD": {"EUR", "USD"},
    "GERMANY40": {"EUR"},
    "DE40": {"EUR"},
    "[IBEX35]": {"EUR"},
    "IBEX35": {"EUR"},
    "SPAIN35": {"EUR"},
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
    if "EUR" in s or "GER" in s or "DE40" in s or "IBEX" in s or "SPAIN" in s:
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


def _penultimate_business_day(year: int, month: int) -> date:
    # Último día de mes
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    d = next_month - timedelta(days=1)
    # Contar hacia atrás para encontrar los 2 últimos días hábiles
    business_days = []
    while len(business_days) < 2:
        if d.weekday() < 5:
            business_days.append(d)
        d -= timedelta(days=1)
    return business_days[1]  # Penúltimo día hábil


def _first_friday_of_month(year: int, month: int) -> date:
    d = date(year, month, 1)
    while d.weekday() != 4:  # 4 = Viernes
        d += timedelta(days=1)
    return d


def _last_friday_of_month(year: int, month: int) -> date:
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    d = next_month - timedelta(days=1)
    while d.weekday() != 4:
        d -= timedelta(days=1)
    return d


def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """weekday: 0=Lunes, 1=Martes, 2=Miércoles, 3=Jueves, 4=Viernes."""
    d = date(year, month, 1)
    count = 0
    while True:
        if d.weekday() == weekday:
            count += 1
            if count == n:
                return d
        d += timedelta(days=1)


def _nearest_weekday(year: int, month: int, day: int) -> date:
    """Ajusta un día del mes al día laborable más cercano si cae en fin de semana."""
    try:
        d = date(year, month, day)
    except ValueError:
        d = _first_business_day(year, month)
    if d.weekday() == 5:  # Sábado -> Viernes
        d -= timedelta(days=1)
    elif d.weekday() == 6:  # Domingo -> Lunes
        d += timedelta(days=1)
    return d


# Calendario Oficial de Reuniones de Política Monetaria del BCE (Jueves 13:15 / 13:45 UTC)
ECB_MEETINGS_SCHEDULE: dict[int, list[tuple[int, int]]] = {
    2024: [(1, 25), (3, 7), (4, 11), (6, 6), (7, 18), (9, 12), (10, 17), (12, 12)],
    2025: [(1, 30), (3, 6), (4, 17), (6, 5), (7, 24), (9, 11), (10, 30), (12, 18)],
    2026: [(1, 29), (3, 12), (4, 23), (6, 11), (7, 23), (9, 10), (10, 29), (12, 17)],
    2027: [(1, 28), (3, 11), (4, 22), (6, 10), (7, 22), (9, 9), (10, 28), (12, 16)],
}

# Calendario Oficial de Decisiones de Tipos FOMC de la Fed (Miércoles 18:00 / 18:30 UTC)
FOMC_MEETINGS_SCHEDULE: dict[int, list[tuple[int, int]]] = {
    2024: [(1, 31), (3, 20), (5, 1), (6, 12), (7, 31), (9, 18), (11, 7), (12, 18)],
    2025: [(1, 29), (3, 19), (5, 7), (6, 18), (7, 30), (9, 17), (11, 5), (12, 17)],
    2026: [(1, 28), (3, 18), (5, 6), (6, 17), (7, 29), (9, 16), (11, 4), (12, 16)],
    2027: [(1, 27), (3, 17), (5, 5), (6, 16), (7, 28), (9, 15), (11, 3), (12, 15)],
}


class MacroNewsFilter:
    """Detector causal de ventanas de apagón de noticias de alto impacto mundiales, europeas, alemanas y españolas."""

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
        if self.calendar_file is None:
            # Comprobar si existe data/macro_calendar.json en la raíz del proyecto
            default_path = Path("data/macro_calendar.json")
            if default_path.exists():
                self.calendar_file = default_path

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
                        country=item.get("country", "GLOBAL").upper(),
                    )
                )
            self._loaded_file_events = events
        except Exception:
            self._loaded_file_events = []

    def add_custom_event(self, event: MacroEvent) -> None:
        self.custom_events.append(event)

    def generate_scheduled_events(self, year: int, month: int) -> list[MacroEvent]:
        """Genera el calendario programado de los principales informes macroeconómicos recurrentes.

        Cubre:
        - Alemania (EUR): Producción Industrial, Balanza Comercial, IFO, ZEW, IPC Preliminar.
        - España (EUR): IPC Armonizado Preliminar INE, PMI, PIB.
        - Eurozona / BCE (EUR): Tipos BCE, Lagarde Press Conf, IPC Flash, PMI Flash.
        - EE.UU. / Mundial (USD): NFP, ISM Mfg/Srv, CPI, PPI, Ventas Minoristas, PCE Core, FOMC.
        """
        events: list[MacroEvent] = []

        # =========================================================================
        # 1. ALEMANIA (EUR) - Crítico para GERMANY40 y EURUSD
        # =========================================================================
        # 1a. Producción Industrial de Alemania (Destatis): 5º día hábil a las 07:00 UTC (08:00 CET)
        de_ip_day = _nth_business_day(year, month, 5)
        events.append(
            MacroEvent(
                name="German Industrial Production (Produktion)",
                currency="EUR",
                time_utc=datetime(de_ip_day.year, de_ip_day.month, de_ip_day.day, 7, 0, tzinfo=timezone.utc),
                country="DE",
            )
        )

        # 1b. Balanza Comercial de Alemania (Handelsbilanz): 6º día hábil a las 07:00 UTC (08:00 CET)
        de_tb_day = _nth_business_day(year, month, 6)
        events.append(
            MacroEvent(
                name="German Trade Balance (Handelsbilanz)",
                currency="EUR",
                time_utc=datetime(de_tb_day.year, de_tb_day.month, de_tb_day.day, 7, 0, tzinfo=timezone.utc),
                country="DE",
            )
        )

        # 1c. Confianza Inversora ZEW de Alemania: 2º martes del mes a las 10:00 UTC (11:00 CET)
        de_zew_day = _nth_weekday_of_month(year, month, weekday=1, n=2)
        events.append(
            MacroEvent(
                name="German ZEW Economic Sentiment",
                currency="EUR",
                time_utc=datetime(de_zew_day.year, de_zew_day.month, de_zew_day.day, 10, 0, tzinfo=timezone.utc),
                country="DE",
            )
        )

        # 1d. Clima Empresarial IFO de Alemania: aprox día 24 a las 09:00 UTC (10:00 CET)
        de_ifo_day = _nearest_weekday(year, month, 24)
        events.append(
            MacroEvent(
                name="German IFO Business Climate Index",
                currency="EUR",
                time_utc=datetime(de_ifo_day.year, de_ifo_day.month, de_ifo_day.day, 9, 0, tzinfo=timezone.utc),
                country="DE",
            )
        )

        # 1e. IPC Preliminar de Alemania (VPI): Penúltimo día hábil a las 13:00 UTC (14:00 CET)
        de_cpi_day = _penultimate_business_day(year, month)
        events.append(
            MacroEvent(
                name="German Preliminary CPI (Verbraucherpreisindex)",
                currency="EUR",
                time_utc=datetime(de_cpi_day.year, de_cpi_day.month, de_cpi_day.day, 13, 0, tzinfo=timezone.utc),
                country="DE",
            )
        )

        # =========================================================================
        # 2. ESPAÑA (EUR) - Crítico para [IBEX35] y EURUSD
        # =========================================================================
        # 2a. IPC Preliminar de España (INE): Penúltimo día hábil a las 07:00 UTC (08:00 CET / 09:00 CEST)
        es_cpi_day = _penultimate_business_day(year, month)
        events.append(
            MacroEvent(
                name="Spanish Flash CPI (IPC Preliminar INE)",
                currency="EUR",
                time_utc=datetime(es_cpi_day.year, es_cpi_day.month, es_cpi_day.day, 7, 0, tzinfo=timezone.utc),
                country="ES",
            )
        )

        # 2b. PMI Manufacturero de España: 1er día hábil a las 08:15 UTC (09:15 CET)
        es_pmi_mfg_day = _first_business_day(year, month)
        events.append(
            MacroEvent(
                name="Spanish Manufacturing PMI",
                currency="EUR",
                time_utc=datetime(es_pmi_mfg_day.year, es_pmi_mfg_day.month, es_pmi_mfg_day.day, 8, 15, tzinfo=timezone.utc),
                country="ES",
            )
        )

        # 2c. PMI Servicios de España: 3er día hábil a las 08:15 UTC (09:15 CET)
        es_pmi_srv_day = _nth_business_day(year, month, 3)
        events.append(
            MacroEvent(
                name="Spanish Services PMI",
                currency="EUR",
                time_utc=datetime(es_pmi_srv_day.year, es_pmi_srv_day.month, es_pmi_srv_day.day, 8, 15, tzinfo=timezone.utc),
                country="ES",
            )
        )

        # =========================================================================
        # 3. EUROZONA Y BANCO CENTRAL EUROPEO (BCE) (EUR)
        # =========================================================================
        # 3a. Reunión de Tipos de Interés del BCE (13:15 UTC) y Conferencia Lagarde (13:45 UTC)
        ecb_dates = ECB_MEETINGS_SCHEDULE.get(year, [])
        for m, d in ecb_dates:
            if m == month:
                events.append(
                    MacroEvent(
                        name="ECB Monetary Policy Decision (Tipos de Interés)",
                        currency="EUR",
                        time_utc=datetime(year, m, d, 13, 15, tzinfo=timezone.utc),
                        country="EU",
                    )
                )
                events.append(
                    MacroEvent(
                        name="ECB Press Conference (Christine Lagarde)",
                        currency="EUR",
                        time_utc=datetime(year, m, d, 13, 45, tzinfo=timezone.utc),
                        country="EU",
                    )
                )

        # 3b. Eurozone Flash CPI (IPC Eurozona): 1er o 2º día hábil a las 10:00 UTC (11:00 CET)
        ez_cpi_day = _nth_business_day(year, month, 2)
        events.append(
            MacroEvent(
                name="Eurozone Flash CPI (IPC Eurozona)",
                currency="EUR",
                time_utc=datetime(ez_cpi_day.year, ez_cpi_day.month, ez_cpi_day.day, 10, 0, tzinfo=timezone.utc),
                country="EU",
            )
        )

        # 3c. Eurozone Flash PMI Composite: aprox día 22 a las 09:00 UTC (10:00 CET)
        ez_pmi_day = _nearest_weekday(year, month, 22)
        events.append(
            MacroEvent(
                name="Eurozone Flash PMI Composite",
                currency="EUR",
                time_utc=datetime(ez_pmi_day.year, ez_pmi_day.month, ez_pmi_day.day, 9, 0, tzinfo=timezone.utc),
                country="EU",
            )
        )

        # =========================================================================
        # 4. ESTADOS UNIDOS Y GLOBAL (USD) - Crítico para [SP500], US100, [DJI30], GOLD, EURUSD
        # =========================================================================
        # 4a. US NFP (Non-Farm Payrolls) & Desempleo: 1er Viernes de mes (13:30 UTC / 12:30 EDT)
        nfp_day = _first_friday_of_month(year, month)
        events.append(
            MacroEvent(
                name="US Non-Farm Payrolls & Unemployment Rate",
                currency="USD",
                time_utc=datetime(nfp_day.year, nfp_day.month, nfp_day.day, 13, 30, tzinfo=timezone.utc),
                country="US",
            )
        )

        # 4b. US ISM Manufacturing PMI: 1er día hábil a las 15:00 UTC
        ism_mfg_day = _first_business_day(year, month)
        events.append(
            MacroEvent(
                name="US ISM Manufacturing PMI",
                currency="USD",
                time_utc=datetime(ism_mfg_day.year, ism_mfg_day.month, ism_mfg_day.day, 15, 0, tzinfo=timezone.utc),
                country="US",
            )
        )

        # 4c. US ISM Services PMI: 3er día hábil a las 15:00 UTC
        ism_srv_day = _nth_business_day(year, month, 3)
        events.append(
            MacroEvent(
                name="US ISM Services PMI",
                currency="USD",
                time_utc=datetime(ism_srv_day.year, ism_srv_day.month, ism_srv_day.day, 15, 0, tzinfo=timezone.utc),
                country="US",
            )
        )

        # 4d. US CPI (IPC de EE.UU.): 2º miércoles de mes a las 13:30 UTC
        us_cpi_day = _nth_weekday_of_month(year, month, weekday=2, n=2)
        events.append(
            MacroEvent(
                name="US Consumer Price Index (CPI)",
                currency="USD",
                time_utc=datetime(us_cpi_day.year, us_cpi_day.month, us_cpi_day.day, 13, 30, tzinfo=timezone.utc),
                country="US",
            )
        )

        # 4e. US PPI (Índice de Precios al Productor): día después de CPI (2º jueves) a las 13:30 UTC
        us_ppi_day = _nth_weekday_of_month(year, month, weekday=3, n=2)
        events.append(
            MacroEvent(
                name="US Producer Price Index (PPI)",
                currency="USD",
                time_utc=datetime(us_ppi_day.year, us_ppi_day.month, us_ppi_day.day, 13, 30, tzinfo=timezone.utc),
                country="US",
            )
        )

        # 4f. US Retail Sales (Ventas Minoristas): 3er martes de mes a las 13:30 UTC
        us_retail_day = _nth_weekday_of_month(year, month, weekday=1, n=3)
        events.append(
            MacroEvent(
                name="US Retail Sales (Advance Monthly)",
                currency="USD",
                time_utc=datetime(us_retail_day.year, us_retail_day.month, us_retail_day.day, 13, 30, tzinfo=timezone.utc),
                country="US",
            )
        )

        # 4g. US Core PCE Price Index (Gasto Personal - Favorito de la Fed): Último viernes a las 13:30 UTC
        us_pce_day = _last_friday_of_month(year, month)
        events.append(
            MacroEvent(
                name="US Core PCE Price Index",
                currency="USD",
                time_utc=datetime(us_pce_day.year, us_pce_day.month, us_pce_day.day, 13, 30, tzinfo=timezone.utc),
                country="US",
            )
        )

        # 4h. Reunión FOMC de la Reserva Federal (18:00 UTC) y Rueda de Prensa Powell (18:30 UTC)
        fomc_dates = FOMC_MEETINGS_SCHEDULE.get(year, [])
        for m, d in fomc_dates:
            if m == month:
                events.append(
                    MacroEvent(
                        name="US FOMC Interest Rate Decision",
                        currency="USD",
                        time_utc=datetime(year, m, d, 18, 0, tzinfo=timezone.utc),
                        country="US",
                    )
                )
                events.append(
                    MacroEvent(
                        name="US FOMC Press Conference (Jerome Powell)",
                        currency="USD",
                        time_utc=datetime(year, m, d, 18, 30, tzinfo=timezone.utc),
                        country="US",
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
                    f"BLACKOUT NOTICIA TIER-1: [{ev.country}|{ev.currency}] '{ev.name}' ({timing_str}, a las "
                    f"{ev.time_utc.strftime('%H:%M')} UTC). Ventana protegida: ±{int(self.blackout_before.total_seconds() // 60)}m"
                )
                return True, reason

        return False, None
