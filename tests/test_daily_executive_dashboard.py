"""Tests para el cuadro de mando ejecutivo y módulo fiscal (IRPF España)."""
from __future__ import annotations

import unittest
from trading_v2.reporting.daily_executive_dashboard import calculate_spanish_tax, render_executive_markdown


class DailyExecutiveDashboardTests(unittest.TestCase):
    def test_tax_calculation_positive_first_bracket(self):
        # 1.000 € de beneficio neto debe tributar al 19%
        res = calculate_spanish_tax(1000.0)
        self.assertEqual(res["taxable_base_eur"], 1000.0)
        self.assertEqual(res["estimated_tax_eur"], 190.0)
        self.assertEqual(res["effective_tax_rate_pct"], 19.0)
        self.assertEqual(res["after_tax_net_eur"], 810.0)

    def test_tax_calculation_progressive_brackets(self):
        # 10.000 € de beneficio:
        # Primeros 6.000 € al 19% = 1.140 €
        # Siguientes 4.000 € al 21% = 840 €
        # Total = 1.980 € (tipo efectivo 19.8%)
        res = calculate_spanish_tax(10000.0)
        self.assertEqual(res["estimated_tax_eur"], 1980.0)
        self.assertEqual(res["effective_tax_rate_pct"], 19.8)
        self.assertEqual(res["after_tax_net_eur"], 8020.0)

    def test_tax_calculation_loss_generates_tax_credit_note(self):
        res = calculate_spanish_tax(-450.0)
        self.assertEqual(res["estimated_tax_eur"], 0.0)
        self.assertEqual(res["effective_tax_rate_pct"], 0.0)
        self.assertEqual(res["after_tax_net_eur"], -450.0)
        self.assertIn("compensable", res["fiscal_note"].lower())

    def test_render_executive_markdown_structure(self):
        fake_data = {
            "timestamp_utc": "2026-10-19 16:00:00 UTC",
            "date_str": "2026-10-19",
            "account": {"login": 58678879, "server": "AdmiralsGroup-Demo", "balance": 3000.0, "equity": 3025.0, "floating_pnl": 25.0},
            "performance": {
                "closed_trades_count": 1,
                "gross_profit_eur": 35.0,
                "gross_loss_eur": 0.0,
                "total_commissions_eur": 0.0,
                "total_swaps_eur": 0.0,
                "net_closed_pnl_eur": 35.0,
            },
            "fiscal": calculate_spanish_tax(35.0),
            "closed_trades": [],
            "open_positions": [],
            "signals": [
                {
                    "market": "NASDAQ100",
                    "symbol": "US100",
                    "strategy": "idx_rsi2_dip_regime",
                    "signal_active": True,
                    "reasons": ["RSI(2) en sobreventa extrema (2.3 < 10.0)"],
                    "close": 29600.0,
                    "sma200": 27800.0,
                    "rsi2": 2.3,
                    "ibs": 0.15,
                    "atr_regime": 0.95,
                }
            ],
        }
        md = render_executive_markdown(fake_data)
        self.assertIn("Cuadro de Mando Ejecutivo", md)
        self.assertIn("Módulo de Tributación Estimada", md)
        self.assertIn("Diario de Decisiones", md)
        self.assertIn("NASDAQ100", md)


if __name__ == "__main__":
    unittest.main()
