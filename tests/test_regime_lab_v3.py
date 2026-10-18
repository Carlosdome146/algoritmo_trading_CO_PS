"""Tests del laboratorio V3 diario: causalidad, costes y salvaguardas."""
from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from trading_v2.research.regime_lab_v3 import (
    StrategySpec,
    add_indicators,
    bonferroni_t,
    canonical_strategies,
    entry_exit_signals,
    metrics,
    simulate_daily,
    wilson_lb,
)


def synthetic_daily(n: int = 800, seed: int = 7, drift: float = 0.0004, spread: int = 150) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2018-01-01", periods=n)
    ret = drift + 0.01 * rng.standard_normal(n)
    close = 15000 * np.exp(np.cumsum(ret))
    open_ = np.concatenate([[close[0]], close[:-1]]) * (1 + 0.002 * rng.standard_normal(n))
    high = np.maximum(open_, close) * (1 + 0.004 * rng.random(n))
    low = np.minimum(open_, close) * (1 - 0.004 * rng.random(n))
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "TickVolume": 1000, "Spread": spread, "RealVolume": 0},
        index=idx,
    )


class RegimeLabV3Tests(unittest.TestCase):
    def test_signals_are_causal(self):
        d = add_indicators(synthetic_daily())
        cut = 600
        d_trunc = add_indicators(synthetic_daily().iloc[:cut])
        for s in canonical_strategies():
            full_e, full_x = entry_exit_signals(d, s)
            tr_e, tr_x = entry_exit_signals(d_trunc, s)
            pd.testing.assert_series_equal(full_e.iloc[:cut], tr_e, check_names=False)
            pd.testing.assert_series_equal(full_x.iloc[:cut], tr_x, check_names=False)

    def test_entry_executes_next_open_never_signal_bar(self):
        d = add_indicators(synthetic_daily())
        s = StrategySpec("idx_rsi2_dip", ("DAX40",), "long", {"sma": 200, "rsi_th": 30}, 2.5, 10)
        trades = simulate_daily(d, s, "DAX40")
        self.assertFalse(trades.empty)
        self.assertTrue((trades["entry_time"] > trades["signal_time"]).all())
        self.assertTrue((trades["exit_time"] >= trades["entry_time"]).all())
        # Sin solapamiento
        self.assertTrue((trades["entry_time"].iloc[1:].values > trades["exit_time"].iloc[:-1].values).all())

    def test_costs_make_flat_market_lose(self):
        d = synthetic_daily(drift=0.0)
        d[["Open", "High", "Low", "Close"]] = 15000.0
        d["High"] += 1.0
        d["Low"] -= 1.0
        d = add_indicators(d)
        d["atr20"] = 50.0
        s = StrategySpec("tsmom", ("DAX40",), "both", {"sma": 200}, 3.0, 5)
        # Forzamos señal larga constante manipulando la tendencia: precio plano => sin señal; comprobamos coste directo
        s_long = StrategySpec("idx_ibs_dip", ("DAX40",), "long", {"sma": 5, "ibs_th": 0.9}, 2.5, 5)
        d["sma5"] = 14000.0  # Close > sma => entra siempre que ibs < 0.9 (ibs = 0.5)
        trades = simulate_daily(d, s_long, "DAX40")
        self.assertFalse(trades.empty)
        self.assertTrue((trades["r"] < 0).all(), "En mercado plano los costes deben producir pérdida")
        self.assertIsNotNone(s)

    def test_metrics_and_wilson(self):
        r = np.array([1.0, -0.5, 0.5, 0.5, -1.0])
        m = metrics(r)
        self.assertEqual(m["n"], 5)
        self.assertAlmostEqual(m["win_rate"], 60.0)
        self.assertAlmostEqual(m["profit_factor"], 2.0 / 1.5, places=3)
        self.assertLess(wilson_lb(60, 100), 60.0)
        self.assertGreater(wilson_lb(600, 1000), wilson_lb(60, 100))

    def test_bonferroni_grows_with_trials(self):
        self.assertGreater(bonferroni_t(20), bonferroni_t(1))

    def test_limit_order_simulation_modes(self):
        d = add_indicators(synthetic_daily())
        s = StrategySpec("idx_rsi2_dip", ("DAX40",), "long", {"sma": 200, "rsi_th": 30}, 2.5, 10)
        t_mkt = simulate_daily(d, s, "DAX40", entry_mode="market")
        t_lim = simulate_daily(d, s, "DAX40", entry_mode="limit_discount", limit_offset_atr=0.20)
        self.assertFalse(t_mkt.empty)
        # Una orden límite con descuento exigente debe ejecutar igual o menos operaciones que a mercado
        self.assertLessEqual(len(t_lim), len(t_mkt))


if __name__ == "__main__":
    unittest.main()
