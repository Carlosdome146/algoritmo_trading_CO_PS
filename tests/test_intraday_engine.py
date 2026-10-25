"""Tests unitarios del motor de backtesting intradía (sin necesidad de MT5)."""
from __future__ import annotations
import unittest
import math
import numpy as np
import pandas as pd

from trading_v2.backtesting.intraday_engine import (
    add_base_indicators,
    compute_metrics,
    simulate_strategy,
    wilson_lower_bound,
    BacktestMetrics,
    PASS_WR,
    PASS_MAX_DD,
)


def _make_synthetic_df(n: int = 500, symbol: str = "GERMANY40") -> pd.DataFrame:
    """Genera un DataFrame sintético con OHLCV y Spread para tests."""
    np.random.seed(99)
    times = pd.date_range("2024-01-02 08:00", periods=n, freq="15min", tz="UTC")
    base  = 18000.0 + np.cumsum(np.random.randn(n) * 5.0)
    hi    = base + np.abs(np.random.randn(n) * 3.0) + 1.0
    lo    = base - np.abs(np.random.randn(n) * 3.0) - 1.0
    op    = base + np.random.randn(n) * 2.0
    cl    = base + np.random.randn(n) * 2.0
    # Asegurar High >= max(Open, Close) y Low <= min(Open, Close)
    hi = np.maximum(hi, np.maximum(op, cl))
    lo = np.minimum(lo, np.minimum(op, cl))

    df = pd.DataFrame({
        "Open":       op,
        "High":       hi,
        "Low":        lo,
        "Close":      cl,
        "TickVolume": np.random.randint(100, 500, n).astype(float),
        "Spread":     np.full(n, 10.0),   # 10 points spread
    }, index=times)
    return df


class TestWilsonLowerBound(unittest.TestCase):
    def test_perfect_win_rate(self):
        lb = wilson_lower_bound(100, 100)
        self.assertGreater(lb, 90.0)

    def test_zero_wins(self):
        self.assertEqual(wilson_lower_bound(0, 100), 0.0)

    def test_empty(self):
        self.assertEqual(wilson_lower_bound(0, 0), 0.0)

    def test_50pct(self):
        lb = wilson_lower_bound(50, 100)
        # LB con 50% observado debe estar en torno al 42-43%
        self.assertGreater(lb, 35.0)
        self.assertLess(lb, 50.0)


class TestBaseIndicators(unittest.TestCase):
    def setUp(self):
        self.df = _make_synthetic_df(500)
        self.ind = add_base_indicators(self.df)

    def test_required_columns_present(self):
        for col in ["atr14", "rsi2", "sma200", "ema20", "ema50",
                    "bb_up", "bb_lo", "clv", "lower_wick", "upper_wick",
                    "ib_high", "ib_low", "hour_utc"]:
            self.assertIn(col, self.ind.columns, f"Falta columna: {col}")

    def test_clv_bounded(self):
        clv = self.ind["clv"].dropna()
        self.assertTrue((clv >= 0.0).all())
        self.assertTrue((clv <= 1.0).all())

    def test_wicks_non_negative(self):
        self.assertTrue((self.ind["lower_wick"].dropna() >= 0).all())
        self.assertTrue((self.ind["upper_wick"].dropna() >= 0).all())

    def test_atr_positive(self):
        atr = self.ind["atr14"].dropna()
        self.assertTrue((atr > 0).all())

    def test_rsi2_bounded(self):
        rsi = self.ind["rsi2"].dropna()
        self.assertTrue((rsi >= 0).all())
        self.assertTrue((rsi <= 100).all())


class TestSimulateStrategy(unittest.TestCase):
    def setUp(self):
        df_raw = _make_synthetic_df(500)
        self.df = add_base_indicators(df_raw)
        self.symbol = "GERMANY40"

    def _always_long(self, df):
        """Señal trivial: compra en todas las barras."""
        return np.ones(len(df), dtype=int)

    def _never_signal(self, df):
        return np.zeros(len(df), dtype=int)

    def test_no_signals_returns_empty(self):
        trades = simulate_strategy(self.df, self.symbol, self._never_signal, use_session=False)
        self.assertIsInstance(trades, pd.DataFrame)
        self.assertEqual(len(trades), 0)

    def test_always_long_generates_trades(self):
        trades = simulate_strategy(
            self.df, self.symbol, self._always_long,
            stop_atr=1.0, tp_atr=0.5, max_holding_bars=4,
            use_session=False,
        )
        self.assertGreater(len(trades), 0)
        # Columnas requeridas
        for col in ["entry_time", "exit_time", "side", "r", "reason"]:
            self.assertIn(col, trades.columns)

    def test_no_overlapping_trades(self):
        trades = simulate_strategy(
            self.df, self.symbol, self._always_long,
            stop_atr=1.5, tp_atr=1.0, max_holding_bars=4,
            use_session=False,
        )
        if len(trades) < 2:
            return
        for i in range(1, len(trades)):
            self.assertGreaterEqual(
                trades.iloc[i]["entry_time"],
                trades.iloc[i - 1]["exit_time"],
                "Operaciones solapadas detectadas",
            )

    def test_all_sides_are_long_or_short(self):
        trades = simulate_strategy(
            self.df, self.symbol, self._always_long,
            use_session=False,
        )
        self.assertTrue(trades["side"].isin(["LONG", "SHORT"]).all())

    def test_stop_loss_respected(self):
        """El R de las operaciones paradas no debe superar +0.1 (pequeño margen de spread)."""
        trades = simulate_strategy(
            self.df, self.symbol, self._always_long,
            stop_atr=1.5, tp_atr=1.0, max_holding_bars=4,
            use_session=False,
        )
        if len(trades) == 0:
            return
        # STOP_CONSERVATIVE ocurre cuando TP y SL se tocan en la misma barra;
        # el simulador conservador sale al SL, lo que puede dar R cercano a 0.
        stops = trades[trades["reason"] == "STOP"]
        for _, row in stops.iterrows():
            # Un STOP puro nunca debe dar R positivo mayor que el margen de spread (~0.05R)
            self.assertLessEqual(row["r"], 0.05, "STOP puro no debería dar R positivo")


class TestComputeMetrics(unittest.TestCase):
    def _make_trades(self, win_rate: float, n: int = 200) -> pd.DataFrame:
        np.random.seed(42)
        times = pd.date_range("2024-01-02 09:00", periods=n, freq="4h", tz="UTC")
        wins  = int(n * win_rate)
        r_arr = np.array([+0.8] * wins + [-1.0] * (n - wins), dtype=float)
        np.random.shuffle(r_arr)
        return pd.DataFrame({"r": r_arr, "entry_time": times})

    def test_pass_verdict(self):
        trades = self._make_trades(0.75, 200)
        m = compute_metrics(trades, "GERMANY40", "M15", "Test_PASS")
        self.assertEqual(m.verdict, "PASS OK")
        self.assertGreater(m.win_rate, PASS_WR)

    def test_fail_low_winrate(self):
        trades = self._make_trades(0.55, 200)
        m = compute_metrics(trades, "GERMANY40", "M15", "Test_FAIL_WR")
        self.assertEqual(m.verdict, "FAIL XX")
        self.assertIn("WR", " ".join(m.fail_reasons))

    def test_fail_few_trades(self):
        trades = self._make_trades(0.80, 20)
        m = compute_metrics(trades, "GERMANY40", "M15", "Test_FAIL_N")
        self.assertIn("FAIL", m.verdict)

    def test_profit_factor_positive(self):
        trades = self._make_trades(0.70, 200)
        m = compute_metrics(trades, "GERMANY40", "M15", "Test_PF")
        self.assertGreater(m.profit_factor, 0.0)

    def test_wilson_lb_below_win_rate(self):
        trades = self._make_trades(0.75, 200)
        m = compute_metrics(trades, "GERMANY40", "M15", "Test_Wilson")
        # El lower bound SIEMPRE debe ser <= WR observado
        self.assertLessEqual(m.wilson_lb_pct, m.win_rate + 0.1)

    def test_empty_trades(self):
        trades = pd.DataFrame(columns=["r", "entry_time"])
        m = compute_metrics(trades, "GERMANY40", "M15", "Test_Empty")
        self.assertEqual(m.n_trades, 0)
        self.assertIn("FAIL", m.verdict)

    def test_metrics_str_format(self):
        trades = self._make_trades(0.75, 200)
        m = compute_metrics(trades, "GERMANY40", "M15", "Test_STR")
        s = str(m)
        self.assertIn("Test_STR", s)
        self.assertIn("WR=", s)


if __name__ == "__main__":
    unittest.main(verbosity=2)
