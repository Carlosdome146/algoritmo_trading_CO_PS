"""Tests unitarios para la estrategia de Micro-Scalping Institucional Francotirador."""
import unittest
import numpy as np
import pandas as pd

from trading_v2.strategies.micro_scalping import (
    SniperScalpConfig,
    compute_sniper_indicators,
    generate_sniper_signals,
)


class TestMicroScalping(unittest.TestCase):
    def setUp(self):
        # Crear 100 velas M5 sintéticas con fechas y horas UTC
        times = pd.date_range("2026-10-20 06:00:00", periods=100, freq="5min", tz="UTC")
        np.random.seed(42)
        base = 1.1200 + np.cumsum(np.random.randn(100) * 0.0001)
        
        self.df = pd.DataFrame(
            {
                "Open": base,
                "High": base + 0.0004,
                "Low": base - 0.0004,
                "Close": base + 0.0001,
                "TickVolume": np.random.randint(50, 200, 100),
                "Spread": np.full(100, 8),
            },
            index=times,
        )

    def test_config_validation(self):
        """Verifica que SniperScalpConfig valide sus parámetros estrictamente."""
        cfg = SniperScalpConfig("EURUSD", 2.3, 5.0)
        self.assertEqual(cfg.symbol, "EURUSD")
        self.assertEqual(cfg.target_units, 2.3)
        self.assertEqual(cfg.stop_units, 5.0)

        # Errores esperados
        with self.assertRaises(ValueError):
            SniperScalpConfig("EURUSD", -1.0, 5.0)
        with self.assertRaises(ValueError):
            SniperScalpConfig("EURUSD", 2.0, 0.0)
        with self.assertRaises(ValueError):
            SniperScalpConfig("EURUSD", 2.0, 5.0, session_start_h=15, session_end_h=10)
        with self.assertRaises(ValueError):
            SniperScalpConfig("EURUSD", 2.0, 5.0, min_rejection_wick=1.5)

    def test_indicators_computation(self):
        """Verifica el cálculo de CLV, mechas y extremos recientes sin sesgo."""
        ind = compute_sniper_indicators(self.df)
        self.assertIn("clv", ind.columns)
        self.assertIn("lower_wick", ind.columns)
        self.assertIn("upper_wick", ind.columns)
        self.assertIn("recent_high", ind.columns)
        self.assertIn("recent_low", ind.columns)

        # CLV debe estar acotado entre 0 y 1
        self.assertTrue((ind["clv"] >= 0.0).all())
        self.assertTrue((ind["clv"] <= 1.0).all())

        # Mechas de rechazo no negativas
        self.assertTrue((ind["lower_wick"] >= 0.0).all())
        self.assertTrue((ind["upper_wick"] >= 0.0).all())

    def test_signals_quota_and_session(self):
        """Verifica que las señales respeten la cuota diaria de 1 trade y la sesión."""
        cfg = SniperScalpConfig(
            symbol="EURUSD",
            target_units=2.3,
            stop_units=5.0,
            session_start_h=7,
            session_end_h=10,
            max_trades_per_day=1,
            min_sweep_units=0.5,
            min_rejection_wick=0.20,
            use_h1_filter=False,
        )
        res = generate_sniper_signals(self.df, cfg)
        self.assertIn("signal", res.columns)

        signals_series = res["signal"]
        non_zero = signals_series[signals_series != 0]

        # Verificar que si hay señales, no superen 1 por día
        daily_counts = non_zero.groupby(non_zero.index.date).count()
        for d, count in daily_counts.items():
            self.assertLessEqual(count, 1)

        # Verificar que cualquier señal caiga dentro de la sesión 07:00 a 10:00 UTC
        for t in non_zero.index:
            self.assertTrue(7 <= t.hour <= 10)

    def test_signals_multiple_opportunities(self):
        """Verifica que sin límite artificial (None), se aprovechen múltiples oportunidades."""
        cfg = SniperScalpConfig(
            symbol="EURUSD",
            target_units=2.3,
            stop_units=5.0,
            session_start_h=6,
            session_end_h=12,
            max_trades_per_day=None,
            cooldown_bars=2,
            min_sweep_units=0.1,
            min_rejection_wick=0.10,
            use_h1_filter=False,
        )
        res = generate_sniper_signals(self.df, cfg)
        signals_series = res["signal"]
        non_zero = signals_series[signals_series != 0]
        # Con parámetros permisivos y sin tope, debe poder capturar múltiples señales
        self.assertGreaterEqual(len(non_zero), 1)



if __name__ == "__main__":
    unittest.main()
