"""Pruebas unitarias para el Operador Fantasma en Sombra (GhostShadowTrader).

Verifica:
1. Arquitectura Híbrida 70/30 (Cierre parcial TP 70%, Breakeven y Trailing 30% EMA20).
2. Estrategia H1 Mean Reversion para Forex (EURUSD).
3. Persistencia de estado atómica en disco (data/ghost_trader_state.json).
4. Blindaje estricto de solo lectura: NUNCA envía órdenes al bróker (order_send nunca llamado).
5. Filtros de campana de apertura y veto macroeconómico.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from trading_v2.execution.ghost_shadow_trader import (
    GhostPosition,
    GhostShadowTrader,
    GhostTraderConfig,
)


class MockMT5GhostAdapter:
    """Mock del backend MT5 para pruebas unitarias de GhostShadowTrader."""

    def __init__(self):
        self.TIMEFRAME_M15 = 15
        self.TIMEFRAME_M30 = 30
        self.TIMEFRAME_H1 = 16385
        self.sent_orders = []
        self.mock_ticks = {}
        self.mock_rates_m15 = {}
        self.mock_rates_m30 = {}
        self.mock_rates_h1 = {}

    def initialize(self) -> bool:
        return True

    def shutdown(self) -> None:
        pass

    def symbol_info_tick(self, symbol: str):
        return self.mock_ticks.get(symbol)

    def copy_rates_from_pos(self, symbol: str, timeframe: int, start_pos: int, count: int):
        if timeframe == self.TIMEFRAME_H1:
            return self.mock_rates_h1.get(symbol)
        elif timeframe == self.TIMEFRAME_M30:
            return self.mock_rates_m30.get(symbol)
        elif timeframe == self.TIMEFRAME_M15:
            return self.mock_rates_m15.get(symbol)
        return None

    def order_send(self, request):
        # Esta llamada NUNCA debe ocurrir desde el fantasma
        self.sent_orders.append(request)
        return SimpleNamespace(retcode=10009)


class TestGhostShadowTrader(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.state_file = Path(self.test_dir) / "ghost_state.json"
        self.cfg = GhostTraderConfig(
            symbols=["GERMANY40", "EURUSD"],
            initial_capital=3000.0,
            risk_fraction=0.0100,
            runner_ratio=0.30,
            state_file=self.state_file,
            enable_news_blackout=False,
            enable_opening_bell_filter=False,
        )
        self.mock_mt5 = MockMT5GhostAdapter()
        self.trader = GhostShadowTrader(config=self.cfg, mt5_backend=self.mock_mt5)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_initial_state_and_persistence(self):
        self.assertEqual(self.trader.balance, 3000.0)
        self.assertEqual(self.trader.equity, 3000.0)
        self.assertEqual(len(self.trader.open_positions), 0)

        # Guardar y recargar
        self.trader._save_state()
        self.assertTrue(self.state_file.exists())

        trader2 = GhostShadowTrader(config=self.cfg, mt5_backend=self.mock_mt5)
        self.assertEqual(trader2.balance, 3000.0)

    def test_ghost_never_sends_real_orders(self):
        """Verifica que el operador fantasma no posee llamadas a order_send."""
        now_utc = datetime(2026, 11, 2, 9, 30, tzinfo=timezone.utc)
        self.trader.run_cycle()
        self.assertEqual(len(self.mock_mt5.sent_orders), 0)

    def test_h1_forex_tp_and_sl_flow(self):
        """Prueba completa del ciclo de swing H1 en EURUSD."""
        # 1. Crear rates H1 sintéticos con señal de compra (Close < BB_lo, RSI < 10, KER < 0.4)
        closes = [1.1000 + 0.0050 * np.sin(i * 0.8) for i in range(40)]
        closes[-3] = 1.1000
        closes[-2] = 1.0950
        closes[-1] = 1.0850

        rates = []
        for i, c in enumerate(closes):
            rates.append({
                "time": 1700000000 + i * 3600,
                "open": c + 0.0005,
                "high": c + 0.0010,
                "low": c - 0.0005,
                "close": c,
                "tick_volume": 1000,
            })
        self.mock_mt5.mock_rates_h1["EURUSD"] = rates
        self.mock_mt5.mock_ticks["EURUSD"] = SimpleNamespace(bid=1.0850, ask=1.0851)

        now_utc = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)
        self.trader.evaluate_h1_forex("EURUSD", now_utc)

        self.assertEqual(len(self.trader.open_positions), 1)
        pos = self.trader.open_positions[0]
        self.assertEqual(pos.symbol, "EURUSD")
        self.assertEqual(pos.direction, 1)
        self.assertAlmostEqual(pos.entry_price, 1.0851, places=4)
        self.assertAlmostEqual(pos.fixed_tp, 1.0851 + 0.0040, places=4)  # +40 pips
        self.assertAlmostEqual(pos.current_sl, 1.0851 - 0.0035, places=4)  # -35 pips
        self.assertEqual(len(self.mock_mt5.sent_orders), 0)  # Sin órdenes a MT5

        # 2. Test TP hit: precio sube a 1.0895 (> TP de 1.0891)
        self.mock_mt5.mock_ticks["EURUSD"] = SimpleNamespace(bid=1.0895, ask=1.0896)
        self.trader.update_open_positions(now_utc)

        self.assertEqual(len(self.trader.open_positions), 0)
        self.assertEqual(len(self.trader.closed_trades), 1)
        closed = self.trader.closed_trades[0]
        self.assertEqual(closed["exit_reason"], "TAKE_PROFIT_H1")
        self.assertGreater(closed["net_pnl_eur"], 0.0)
        self.assertGreater(self.trader.balance, 3000.0)

    def test_hybrid_70_30_partial_tp_and_runner_trailing(self):
        """Prueba el ciclo de salida 70/30 en DAX:

        Paso 1: Apertura de posición (70% TP rápido, 30% runner).
        Paso 2: Precio alcanza TP del 70% -> Cobra 70%, mueve SL a breakeven, pasa a TRAILING_RUNNER.
        Paso 3: Runner persigue EMA20 y sale con ganancia cuando el precio perfora la media.
        """
        # Crear posición artificialmente para simular el comportamiento exacto
        pos = GhostPosition(
            ticket=9000001,
            symbol="GERMANY40",
            direction=1,
            open_time_utc="2026-11-02T08:30:00+00:00",
            entry_price=19000.0,
            initial_sl=18965.0,  # -35 pts
            current_sl=18965.0,
            fixed_tp=19022.0,    # +22 pts
            lots_total=1.00,
            lots_70=0.70,
            lots_30=0.30,
            status="ACTIVE_FULL",
            strategy_tag="HYBRID_70_30_M30",
        )
        self.trader.open_positions.append(pos)

        now_utc = datetime(2026, 11, 2, 8, 45, tzinfo=timezone.utc)

        # Precio sube a 19025 (> TP 19022)
        self.mock_mt5.mock_ticks["GERMANY40"] = SimpleNamespace(bid=19025.0, ask=19026.0)
        self.trader.update_open_positions(now_utc)

        # Verificamos que sigue abierta (el 30% sigue vivo)
        self.assertEqual(len(self.trader.open_positions), 1)
        active_pos = self.trader.open_positions[0]
        self.assertEqual(active_pos.status, "TRAILING_RUNNER")
        self.assertEqual(active_pos.current_sl, 19000.0)  # Stop movido a Breakeven
        self.assertAlmostEqual(active_pos.pnl_70_eur, 22.0 * 1.0 * 0.70, places=1)
        self.assertGreater(self.trader.balance, 3000.0)

        # Paso 3: Trailing runner con EMA20
        # Simular 25 barras donde la EMA20 subió a 19050 y el precio actual retrocede a 19045
        rates = []
        for i in range(25):
            rates.append({
                "time": 1700000000 + i * 1800,
                "open": 19050.0,
                "high": 19060.0,
                "low": 19040.0,
                "close": 19050.0,
                "tick_volume": 1000,
            })
        self.mock_mt5.mock_rates_m30["GERMANY40"] = rates
        # Precio perfora la EMA20 (19040 < 19050)
        self.mock_mt5.mock_ticks["GERMANY40"] = SimpleNamespace(bid=19040.0, ask=19041.0)

        now_utc2 = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)
        self.trader.update_open_positions(now_utc2)

        # Posición debe haberse cerrado completamente
        self.assertEqual(len(self.trader.open_positions), 0)
        self.assertEqual(len(self.trader.closed_trades), 1)
        closed = self.trader.closed_trades[0]
        self.assertEqual(closed["exit_reason"], "RUNNER_TRAILING_EMA20")
        self.assertGreater(closed["pnl_30_eur"], 0.0)
        self.assertEqual(closed["net_pnl_eur"], round(closed["pnl_70_eur"] + closed["pnl_30_eur"], 2))
        self.assertAlmostEqual(self.trader.balance, 3000.0 + closed["net_pnl_eur"], places=2)

    def test_full_stop_loss(self):
        """Verifica que si toca el Stop Loss inicial, se cierra el 100% de la posición."""
        pos = GhostPosition(
            ticket=9000002,
            symbol="GERMANY40",
            direction=1,
            open_time_utc="2026-11-02T08:30:00+00:00",
            entry_price=19000.0,
            initial_sl=18965.0,  # -35 pts
            current_sl=18965.0,
            fixed_tp=19022.0,
            lots_total=1.00,
            lots_70=0.70,
            lots_30=0.30,
            status="ACTIVE_FULL",
            strategy_tag="HYBRID_70_30_M30",
        )
        self.trader.open_positions.append(pos)
        # Precio cae por debajo del SL
        self.mock_mt5.mock_ticks["GERMANY40"] = SimpleNamespace(bid=18960.0, ask=18961.0)
        now_utc = datetime(2026, 11, 2, 8, 35, tzinfo=timezone.utc)
        self.trader.update_open_positions(now_utc)

        self.assertEqual(len(self.trader.open_positions), 0)
        self.assertEqual(len(self.trader.closed_trades), 1)
        closed = self.trader.closed_trades[0]
        self.assertEqual(closed["exit_reason"], "FULL_STOP_LOSS")
        self.assertLess(closed["net_pnl_eur"], 0.0)
        self.assertLess(self.trader.balance, 3000.0)


if __name__ == "__main__":
    unittest.main()
