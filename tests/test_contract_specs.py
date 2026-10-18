"""Pruebas unitarias de modelado de costes contractuales y dimensionamiento de lotes."""
import unittest
from trading_v2.backtesting.contract_specs import (
    ADMIRALS_SPECS,
    ContractSpec,
    calculate_lot_size,
    calculate_overnight_swap,
    estimate_margin,
    get_contract_spec,
)


class ContractSpecsTests(unittest.TestCase):
    def test_all_admirals_specs_configured(self):
        expected = {"GERMANY40", "[SP500]", "[DJI30]", "GOLD", "EURUSD", "US100", "[JP225]"}
        self.assertEqual(set(ADMIRALS_SPECS.keys()), expected)
        for sym in expected:
            spec = get_contract_spec(sym)
            self.assertEqual(spec.symbol, sym)
            self.assertGreater(spec.contract_size, 0)
            self.assertGreater(spec.point, 0)
            self.assertGreater(spec.tick_size, 0)
            self.assertGreaterEqual(spec.lot_max, spec.lot_min)

    def test_us100_and_jp225_specs(self):
        us100 = get_contract_spec("US100")
        self.assertEqual(us100.profit_currency, "USD")
        self.assertEqual(us100.lot_min, 0.02)
        tick_val_us100 = us100.tick_value_in_account_currency(eurusd_rate=1.12, account_currency="EUR")
        self.assertAlmostEqual(tick_val_us100, 0.01 / 1.12, places=6)

        jp225 = get_contract_spec("[JP225]")
        self.assertEqual(jp225.profit_currency, "JPY")
        self.assertEqual(jp225.contract_size, 10.0)
        tick_val_jp225 = jp225.tick_value_in_account_currency(eurusd_rate=1.12, account_currency="EUR")
        self.assertAlmostEqual(tick_val_jp225, (10.0 * 0.01) / 162.0, places=6)

    def test_germany40_tick_value_eur(self):
        spec = get_contract_spec("GERMANY40")
        tick_val = spec.tick_value_in_account_currency(eurusd_rate=1.12, account_currency="EUR")
        self.assertAlmostEqual(tick_val, 0.01, places=6)
        point_val = spec.point_value_in_account_currency(eurusd_rate=1.12, account_currency="EUR")
        self.assertAlmostEqual(point_val, 0.01, places=6)

    def test_sp500_tick_value_usd_to_eur(self):
        spec = get_contract_spec("[SP500]")
        # 1 tick = 0.01 USD. A EURUSD = 1.123970, 0.01 / 1.123970 = 0.00889703...
        eurusd = 1.123970346
        tick_val = spec.tick_value_in_account_currency(eurusd_rate=eurusd, account_currency="EUR")
        self.assertAlmostEqual(tick_val, 0.00889703, places=6)

    def test_gold_and_eurusd_point_value(self):
        gold = get_contract_spec("GOLD")
        # 1.0 lot de Gold = 100 oz. 1 point ($0.01) = 1.0 USD = 1/1.12 EUR ~ 0.8928 EUR
        val_gold = gold.point_value_in_account_currency(eurusd_rate=1.12, account_currency="EUR")
        self.assertAlmostEqual(val_gold, 1.0 / 1.12, places=4)

        eurusd_spec = get_contract_spec("EURUSD")
        # 1.0 lot EURUSD = 100,000. 1 point (0.00001) = 1.0 USD = 1/1.12 EUR
        val_eurusd = eurusd_spec.point_value_in_account_currency(eurusd_rate=1.12, account_currency="EUR")
        self.assertAlmostEqual(val_eurusd, 1.0 / 1.12, places=4)

    def test_lot_size_rounds_strictly_down(self):
        spec = get_contract_spec("GERMANY40")
        # Equity = 3000, risk = 0.25% (7.50 EUR). Stop distance = 40.35 puntos (0.4035 EUR por lote)
        res = calculate_lot_size(
            spec=spec,
            account_equity=3000.0,
            risk_fraction=0.0025,
            stop_distance_price=40.35,  # 4035 puntos
            entry_price=25000.0,
            eurusd_rate=1.12,
            leverage=100.0
        )
        self.assertEqual(res.status, "OK")
        self.assertLessEqual(res.lots, res.raw_lots)
        # El riesgo real nunca debe superar el presupuesto
        self.assertLessEqual(res.actual_risk_account_ccy, res.risk_budget_account_ccy + 1e-9)
        # Granularidad de lot_step: debe ser un múltiplo entero exacto
        steps = res.lots / spec.lot_step
        self.assertAlmostEqual(steps, round(steps), places=4)

    def test_rejects_when_risk_below_min_lot(self):
        spec = get_contract_spec("[SP500]")  # lot_min = 0.1, lot_step = 0.1
        # Presupuesto de riesgo muy pequeño (ej. 0.50 EUR) con un stop razonable (50 puntos = 0.50 USD)
        res = calculate_lot_size(
            spec=spec,
            account_equity=200.0,
            risk_fraction=0.0025,  # 0.50 EUR de riesgo
            stop_distance_price=5.0,  # 500 puntos = 5.0 USD por lote = 4.46 EUR por 1.0 lote -> 0.446 EUR por 0.1 lote
            entry_price=7600.0,
            eurusd_rate=1.12
        )
        # Si el lote necesario para arriesgar 0.50 EUR estuviera por debajo de 0.1:
        # Aquí 0.50 / 4.46 = 0.112 -> 0.1 lote cabe. Probemos con stop mayor (20.0 pts):
        res_reject = calculate_lot_size(
            spec=spec,
            account_equity=200.0,
            risk_fraction=0.0025,  # 0.50 EUR de riesgo
            stop_distance_price=20.0,  # Pérdida para 0.1 lote = 1.78 EUR > 0.50 EUR
            entry_price=7600.0,
            eurusd_rate=1.12
        )
        self.assertEqual(res_reject.status, "REJECTED_BELOW_MIN_LOT")
        self.assertEqual(res_reject.lots, 0.0)
        self.assertIn("inferior al mínimo", res_reject.reason)

    def test_rejects_when_stop_distance_below_stops_level(self):
        spec = get_contract_spec("GERMANY40")  # stops_level_points = 120 (1.20 EUR)
        res = calculate_lot_size(
            spec=spec,
            account_equity=3000.0,
            risk_fraction=0.01,
            stop_distance_price=0.50,  # 50 puntos < 120 puntos
            entry_price=25000.0,
            eurusd_rate=1.12
        )
        self.assertEqual(res.status, "REJECTED_STOPS_LEVEL")
        self.assertEqual(res.lots, 0.0)
        self.assertIn("stops_level", res.reason)

    def test_invalid_parameters_handled_safely(self):
        spec = get_contract_spec("GERMANY40")
        res_neg_equity = calculate_lot_size(spec, -100.0, 0.01, 10.0, 25000.0)
        self.assertEqual(res_neg_equity.status, "REJECTED_INVALID_INPUT")

        res_excess_risk = calculate_lot_size(spec, 3000.0, 0.20, 10.0, 25000.0)
        self.assertEqual(res_excess_risk.status, "REJECTED_INVALID_INPUT")

        res_neg_price = calculate_lot_size(spec, 3000.0, 0.01, -10.0, 25000.0)
        self.assertEqual(res_neg_price.status, "REJECTED_INVALID_INPUT")

    def test_margin_estimation(self):
        spec = get_contract_spec("GERMANY40")
        # 1.0 lote a 25000 EUR con apalancamiento 1:100 = 250 EUR
        margin = estimate_margin(spec, lots=1.0, entry_price=25000.0, leverage=100.0, eurusd_rate=1.12)
        self.assertAlmostEqual(margin, 250.0, places=2)

    def test_swap_calculation(self):
        spec = get_contract_spec("GERMANY40")
        # Swap modo 5 (interés anual)
        swap_long = calculate_overnight_swap(spec, direction=1, nights=1, lots=1.0, close_price=25000.0)
        self.assertLess(swap_long, 0.0)  # Es un coste negativo


if __name__ == "__main__":
    unittest.main()
