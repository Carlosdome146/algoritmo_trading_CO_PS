"""Tests para el optimizador de ejecución y comparador de carteras."""
from __future__ import annotations

import unittest
import numpy as np
import pandas as pd

from trading_v2.research.regime_lab_v3 import StrategySpec, add_indicators, simulate_daily
from tests.test_regime_lab_v3 import synthetic_daily


class ExecutionOptimizationTests(unittest.TestCase):
    def test_limit_order_execution_semantics(self):
        d = add_indicators(synthetic_daily(seed=42))
        s = StrategySpec("idx_rsi2_dip", ("DAX40",), "long", {"sma": 200, "rsi_th": 30}, 2.5, 10)
        
        mkt = simulate_daily(d, s, "DAX40", entry_mode="market")
        lim = simulate_daily(d, s, "DAX40", entry_mode="limit_discount", limit_offset_atr=0.15)
        
        self.assertFalse(mkt.empty)
        # Una orden límite exigente no puede ejecutar más órdenes que el mercado
        self.assertLessEqual(len(lim), len(mkt))

    def test_invalid_mode_raises(self):
        d = add_indicators(synthetic_daily(seed=42))
        s = StrategySpec("idx_rsi2_dip", ("DAX40",), "long", {"sma": 200, "rsi_th": 30}, 2.5, 10)
        with self.assertRaises(ValueError):
            simulate_daily(d, s, "DAX40", entry_mode="unknown_mode")


if __name__ == "__main__":
    unittest.main()
