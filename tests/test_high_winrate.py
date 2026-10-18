"""Tests unitarios para Microestructura de Precisión y Laboratorio de Alto Win Rate (>= 79%)."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
import numpy as np
import pandas as pd

from trading_v2.strategies.precision_microstructure import (
    PRECISION_FEATURES,
    PRECISION_STRATEGIES,
    enrich_microstructure_features,
    generate_precision_signals,
)
from trading_v2.research.high_winrate_lab import (
    EXIT_PROFILES,
    HORIZONS,
    QUANTILE_CUTOFFS,
    ExitProfile,
    HighWinRateLabConfig,
    compute_sample_uniqueness_weights,
    expected_shortfall_r,
    fit_meta_selector,
    probabilistic_sharpe_ratio,
    research_market_high_winrate,
    run_high_winrate_archive,
    simulate_precision_event,
    wilson_lower_bound,
    windows,
)


def make_synthetic_m15_h1(n: int = 1200, seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    times = pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC")
    steps = rng.normal(0.0, 0.35, n) + 0.08 * np.sin(np.linspace(0, 18 * np.pi, n))
    close = 2000.0 + np.cumsum(steps)
    open_p = close - rng.normal(0.0, 0.15, n)
    high = np.maximum(open_p, close) + np.abs(rng.normal(0.25, 0.10, n))
    low = np.minimum(open_p, close) - np.abs(rng.normal(0.25, 0.10, n))
    spread = rng.integers(35, 55, size=n).astype(float)
    tick_vol = rng.integers(80, 400, size=n).astype(float)

    m15 = pd.DataFrame(
        {
            "Open": open_p,
            "High": high,
            "Low": low,
            "Close": close,
            "Spread": spread,
            "TickVolume": tick_vol,
        },
        index=times,
    )
    h1 = m15.resample("1h").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Spread": "median"}
    )
    return m15, h1


class PrecisionMicrostructureTests(unittest.TestCase):
    def test_all_precision_strategies_produce_valid_signals_and_features(self):
        m15, h1 = make_synthetic_m15_h1(1000)
        enriched = enrich_microstructure_features(m15, h1, 0.01)
        for strat in PRECISION_STRATEGIES:
            out = generate_precision_signals(enriched, strat, 0.01)
            self.assertEqual(len(out), len(m15))
            self.assertTrue(set(out["signal"].unique()).issubset({-1, 0, 1}), strat)
            self.assertTrue((out["direction"] == out["signal"]).all())
            for feat in PRECISION_FEATURES:
                self.assertIn(feat, out.columns)

    def test_strict_causality_future_cannot_alter_past_features_or_signals(self):
        m15, h1 = make_synthetic_m15_h1(1100, seed=99)
        base_enriched = enrich_microstructure_features(m15, h1, 0.01)

        cut = 750  # En mitad de un día intradía para verificar VWAP y ADR_14
        m15_shock = m15.copy()
        for col in ("Open", "High", "Low", "Close"):
            m15_shock.iloc[cut:, m15_shock.columns.get_loc(col)] *= 1.35
        m15_shock.iloc[cut:, m15_shock.columns.get_loc("Spread")] *= 3.0
        m15_shock.iloc[cut:, m15_shock.columns.get_loc("TickVolume")] *= 5.0
        h1_shock = m15_shock.resample("1h").agg(
            {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Spread": "median"}
        )

        shock_enriched = enrich_microstructure_features(m15_shock, h1_shock, 0.01)
        check_cols = ["vwap", "z_vwap", "adr14", "adr_used", "clv", "er20", "vr4", "bb_z", "h1_trend_z"]
        for col in check_cols:
            s1 = base_enriched[col].iloc[:cut]
            s2 = shock_enriched[col].iloc[:cut]
            np.testing.assert_allclose(
                s1.to_numpy(),
                s2.to_numpy(),
                rtol=1e-12,
                atol=1e-12,
                err_msg=f"Fuga del futuro detectada en {col}",
            )

        for strat in PRECISION_STRATEGIES:
            sig_base = generate_precision_signals(base_enriched, strat, 0.01)["signal"].iloc[:cut]
            sig_shock = generate_precision_signals(shock_enriched, strat, 0.01)["signal"].iloc[:cut]
            self.assertTrue((sig_base == sig_shock).all(), f"Fuga del futuro en estrategia {strat}")

    def test_invalid_inputs_rejected(self):
        m15, h1 = make_synthetic_m15_h1(300)
        with self.assertRaises(ValueError):
            enrich_microstructure_features(m15, h1, 0.0)
        enriched = enrich_microstructure_features(m15, h1, 0.01)
        with self.assertRaises(ValueError):
            generate_precision_signals(enriched, "unknown_strategy", 0.01)
        with self.assertRaises(ValueError):
            generate_precision_signals(pd.DataFrame({"Close": [1.0, 2.0]}), PRECISION_STRATEGIES[0], 0.01)


class CausalExitSimulatorTests(unittest.TestCase):
    def _base_arrays(self, n: int = 10, direction: int = 1) -> dict:
        return {
            "open": np.full(n, 100.0, dtype=float),
            "high": np.full(n, 100.2, dtype=float),
            "low": np.full(n, 99.8, dtype=float),
            "close": np.full(n, 100.0, dtype=float),
            "spread": np.full(n, 2.0, dtype=float),  # 2 * 0.01 = 0.02
            "atr": np.full(n, 1.0, dtype=float),
            "signal": np.array([direction] + [0] * (n - 1), dtype=float),
        }

    def test_intrabar_stop_takes_priority_over_breakeven_trigger(self):
        """Si la vela j toca el stop inicial y también cierra arriba, JAMÁS activa breakeven dentro de j."""
        arr = self._base_arrays(6, direction=1)
        # Entrada en j=1: open=100.0 + spread(0.02) = 100.02. Stop(1.40 ATR) = 98.62.
        arr["low"][1] = 98.50   # Toca el stop inicial intrabarra
        arr["high"][1] = 100.50
        arr["close"][1] = 100.45  # Cierre alto que habría activado breakeven si no hubiera tocado stop
        prof = ExitProfile("test_be", sl_atr=1.40, tp_atr=0.60, be_trigger_atr=0.15)
        r, exit_i, reason = simulate_precision_event(arr, 0, 4, 0.01, slippage_multiplier=0.0, profile=prof)
        self.assertEqual(exit_i, 1)
        self.assertEqual(reason, "STOP")
        self.assertAlmostEqual(r, -1.0, places=5)

    def test_causal_breakeven_arms_at_bar_close_for_next_bar(self):
        """Si la vela j=1 cierra con ganancia >= be_trigger_atr sin tocar TP/SL, protege desde j=2."""
        arr = self._base_arrays(6, direction=1)
        # En j=1 sube sin llegar al TP (0.56 ATR -> 100.58) y cierra en 100.30 (ganancia +0.28 ATR >= 0.15)
        arr["high"][1] = 100.40
        arr["low"][1] = 99.95
        arr["close"][1] = 100.30
        # En j=2 cae a 99.90, tocando el stop protegido en breakeven positivo (> 100.02)
        arr["open"][2] = 100.28
        arr["high"][2] = 100.29
        arr["low"][2] = 99.90
        arr["close"][2] = 99.95
        prof = ExitProfile("test_be", sl_atr=1.40, tp_atr=0.56, be_trigger_atr=0.15, be_lock_ratio=0.45)
        r, exit_i, reason = simulate_precision_event(arr, 0, 4, 0.01, slippage_multiplier=0.5, profile=prof)
        self.assertEqual(exit_i, 2)
        self.assertEqual(reason, "PROTECTED_STOP")
        self.assertGreater(r, 0.0, "El stop protegido debe resultar en retorno neto positivo tras slippage")

    def test_time_invalidation_cuts_adverse_trade_at_bar_close(self):
        arr = self._base_arrays(8, direction=1)
        for j in (1, 2, 3):
            arr["high"][j] = 100.05
            arr["low"][j] = 99.50
            arr["close"][j] = 99.60  # -0.42 ATR respecto a entrada (~100.02)
        prof = ExitProfile(
            "test_time",
            sl_atr=1.40,
            tp_atr=0.55,
            be_trigger_atr=0.15,
            max_adverse_close_bars=3,
            max_adverse_close_atr=-0.30,
        )
        r, exit_i, reason = simulate_precision_event(arr, 0, 6, 0.01, slippage_multiplier=0.0, profile=prof)
        self.assertEqual(exit_i, 3)
        self.assertEqual(reason, "TIME_INVALIDATION")
        self.assertGreater(r, -0.50)
        self.assertLess(r, 0.0)


class StatisticalAuditAndLabTests(unittest.TestCase):
    def test_wilson_lower_bound_monotonicity(self):
        # 80% en 100 trades tiene un límite inferior de Wilson mucho más sólido que 80% en 10 trades
        w_small = wilson_lower_bound(8, 10)
        w_large = wilson_lower_bound(80, 100)
        self.assertGreater(w_large, w_small)
        self.assertGreater(w_large, 72.0)
        self.assertLess(w_large, 80.0)
        self.assertEqual(wilson_lower_bound(0, 0), 0.0)

    def test_psr_and_expected_shortfall(self):
        r_good = np.array([0.35, 0.40, 0.30, -0.80, 0.38, 0.42, 0.35, 0.30, -0.75, 0.40] * 4)
        psr = probabilistic_sharpe_ratio(r_good, 0.0)
        cvar = expected_shortfall_r(r_good, 0.05)
        self.assertIsNotNone(psr)
        self.assertGreater(psr, 0.85)
        self.assertAlmostEqual(cvar, -0.80, places=3)

    def test_sample_uniqueness_weights_penalize_overlaps(self):
        # Dos eventos totalmente solapados [10, 20] y un evento aislado [40, 50]
        events = [
            (10, 20, 0.3, np.ones(4)),
            (10, 20, 0.3, np.ones(4)),
            (40, 50, 0.3, np.ones(4)),
        ]
        w = compute_sample_uniqueness_weights(events, 60)
        self.assertEqual(len(w), 3)
        self.assertAlmostEqual(w[0], w[1], places=6)
        self.assertGreater(w[2], w[0] * 1.8)

    def test_meta_selector_learns_thresholds_from_train_only(self):
        rng = np.random.default_rng(7)
        events = []
        for i in range(80):
            x = rng.normal(0, 1, len(PRECISION_FEATURES))
            r = 0.40 if x[0] + x[1] > 0 else -1.0
            events.append((i * 5, i * 5 + 4, r, x))
        bundle = fit_meta_selector(events, min_events=50)
        self.assertIsNotNone(bundle)
        t50 = bundle.threshold_for_quantile(0.50)
        t65 = bundle.threshold_for_quantile(0.65)
        self.assertLess(t50, t65)

    def test_embargo_and_windows_non_overlapping(self):
        cfg = HighWinRateLabConfig()
        folds, (end_train, test_start, n) = windows(12000, cfg)
        self.assertEqual(test_start - end_train, 40)
        self.assertTrue(all(st - tr == 40 for tr, st, _en in folds))
        self.assertTrue(folds[0][2] <= folds[1][1] and folds[1][2] <= test_start)

    def test_no_mt5_imported_in_offline_lab(self):
        self.assertNotIn("MetaTrader5", sys.modules)

    def test_archive_rejects_live_account_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            zpath = Path(td) / "bad.zip"
            with zipfile.ZipFile(zpath, "w") as z:
                z.writestr(
                    "admirals_manifest.json",
                    json.dumps({"account": {"demo": False, "company": "Admirals Group AS", "currency": "EUR"}}),
                )
            with self.assertRaisesRegex(ValueError, "Admirals DEMO"):
                run_high_winrate_archive(zpath)


if __name__ == "__main__":
    unittest.main()
