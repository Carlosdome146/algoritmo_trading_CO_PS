"""Tests unitarios para el Filtro de Noticias Macro de Alto Impacto (Macro News Blackout)."""
import unittest
from datetime import datetime, timezone

from trading_v2.execution.macro_news_filter import (
    MacroEvent,
    MacroNewsFilter,
    get_symbol_currencies,
)


class TestMacroNewsFilter(unittest.TestCase):
    def test_symbol_currencies_mapping(self):
        self.assertEqual(get_symbol_currencies("EURUSD"), {"EUR", "USD"})
        self.assertEqual(get_symbol_currencies("GERMANY40"), {"EUR"})
        self.assertEqual(get_symbol_currencies("[IBEX35]"), {"EUR"})
        self.assertEqual(get_symbol_currencies("[SP500]"), {"USD"})
        self.assertEqual(get_symbol_currencies("US100"), {"USD"})
        self.assertEqual(get_symbol_currencies("[DJI30]"), {"USD"})
        self.assertEqual(get_symbol_currencies("GOLD"), {"USD"})

    def test_blackout_window_trigger(self):
        filt = MacroNewsFilter(blackout_before_m=15, blackout_after_m=15)
        # Evento programado a las 15:00 UTC en USD
        event_time = datetime(2026, 11, 4, 15, 0, tzinfo=timezone.utc)
        filt.add_custom_event(
            MacroEvent(
                name="US ISM Services PMI",
                currency="USD",
                time_utc=event_time,
                impact="HIGH",
            )
        )

        # 1. A las 14:40 UTC (20 min antes): Fuera de ventana -> Permitido
        t_before = datetime(2026, 11, 4, 14, 40, tzinfo=timezone.utc)
        blocked, _ = filt.is_blackout_active("EURUSD", t_before)
        self.assertFalse(blocked)

        # 2. A las 14:50 UTC (10 min antes): Dentro de ventana -> Bloqueado para activos en USD
        t_inside = datetime(2026, 11, 4, 14, 50, tzinfo=timezone.utc)
        blocked_usd, reason_usd = filt.is_blackout_active("EURUSD", t_inside)
        self.assertTrue(blocked_usd)
        self.assertIn("US ISM Services PMI", reason_usd)
        self.assertIn("en 10 min", reason_usd)

        # 3. A las 14:50 UTC para un activo solo en EUR (ej. GERMANY40): No debe bloquear si el evento es de USD
        blocked_dax, _ = filt.is_blackout_active("GERMANY40", t_inside)
        self.assertFalse(blocked_dax)

        # 4. A las 15:10 UTC (10 min después): Dentro de ventana post-noticia -> Bloqueado
        t_after = datetime(2026, 11, 4, 15, 10, tzinfo=timezone.utc)
        blocked_after, _ = filt.is_blackout_active("US100", t_after)
        self.assertTrue(blocked_after)

        # 5. A las 15:20 UTC (20 min después): Fuera de ventana -> Permitido
        t_clear = datetime(2026, 11, 4, 15, 20, tzinfo=timezone.utc)
        blocked_clear, _ = filt.is_blackout_active("EURUSD", t_clear)
        self.assertFalse(blocked_clear)

    def test_scheduled_recurring_events(self):
        """Verifica que genere eventos para NFP (1er viernes) e ISM (1er y 3er día hábil)."""
        filt = MacroNewsFilter()
        events = filt.generate_scheduled_events(2026, 11)
        names = [e.name for e in events]
        self.assertTrue(any("Non-Farm Payrolls" in n for n in names))
        self.assertTrue(any("ISM Manufacturing" in n for n in names))
        self.assertTrue(any("ISM Services" in n for n in names))
        self.assertTrue(any("Consumer Price Index" in n for n in names))


if __name__ == "__main__":
    unittest.main()
