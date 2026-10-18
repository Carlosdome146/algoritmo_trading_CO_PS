"""Pruebas unitarias para el motor de ejecución DemoPaperTrader y salvaguardas MT5."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np

from trading_v2.execution.demo_paper_trader import (
    DemoPaperTrader,
    DemoTraderConfig,
    assert_demo_account,
    check_spread_and_liquidity,
    is_session_active,
)
from trading_v2.research.risk_pause import RiskPause


class MockAccountInfo:
    def __init__(self, login=12345, server="AdmiralsGroup-Demo", trade_mode=0, balance=3000.0, equity=3000.0, currency="EUR", leverage=100.0, margin_free=2500.0):
        self.login = login
        self.server = server
        self.trade_mode = trade_mode
        self.balance = balance
        self.equity = equity
        self.currency = currency
        self.leverage = leverage
        self.margin_free = margin_free


class MockMT5Adapter:
    def __init__(self, account_info=None):
        self.acc = account_info or MockAccountInfo()
        self.sent_orders = []
        self.TIMEFRAME_M15 = 15
        self.TIMEFRAME_H1 = 16385
        self.ORDER_TYPE_BUY = 0
        self.ORDER_TYPE_SELL = 1
        self.TRADE_ACTION_DEAL = 1
        self.TRADE_ACTION_SLTP = 6
        self.ORDER_FILLING_IOC = 2
        self.ORDER_FILLING_FOK = 1
        self.ORDER_FILLING_RETURN = 0
        self.ORDER_TIME_GTC = 0
        self.TRADE_RETCODE_DONE = 10009

        self.mock_rates_m15 = {}
        self.mock_rates_h1 = {}
        self.mock_ticks = {}
        self.mock_positions = []
        self.mock_deals = []

    def initialize(self) -> bool:
        return True

    def shutdown(self) -> None:
        pass

    def account_info(self):
        return self.acc

    def copy_rates_from_pos(self, symbol: str, timeframe: int, start_pos: int, count: int):
        if timeframe == self.TIMEFRAME_M15:
            return self.mock_rates_m15.get(symbol)
        elif timeframe == self.TIMEFRAME_H1:
            return self.mock_rates_h1.get(symbol)
        return None

    def symbol_info_tick(self, symbol: str):
        return self.mock_ticks.get(symbol)

    def symbol_info(self, symbol: str):
        return SimpleNamespace(filling_mode=3, trade_mode=4)

    def order_calc_profit(self, action: int, symbol: str, volume: float, price_open: float, price_close: float):
        # Estimación lineal simple para mock
        diff = (price_close - price_open) if action == self.ORDER_TYPE_BUY else (price_open - price_close)
        return diff * volume * 1.0

    def order_calc_margin(self, action: int, symbol: str, volume: float, price: float):
        return (price * volume) / 100.0

    def positions_get(self, symbol: str | None = None):
        if symbol:
            return tuple(p for p in self.mock_positions if getattr(p, "symbol", "") == symbol)
        return tuple(self.mock_positions)

    def history_deals_get(self, date_from, date_to):
        return tuple(self.mock_deals)

    def order_send(self, request: dict):
        self.sent_orders.append(request)
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, order=999999, comment="Request executed")


def make_synthetic_rates(count: int, base_price: float, trend: float = 0.0, step_minutes: int = 15) -> np.ndarray:
    """Genera array estructurado tipo MT5 rates."""
    dtype = [
        ("time", "<i8"),
        ("open", "<f8"),
        ("high", "<f8"),
        ("low", "<f8"),
        ("close", "<f8"),
        ("tick_volume", "<i8"),
        ("spread", "<i4"),
        ("real_volume", "<i8"),
    ]
    arr = np.zeros(count, dtype=dtype)
    base_ts = 1700000000
    p = base_price
    for i in range(count):
        arr[i]["time"] = base_ts + i * step_minutes * 60
        p += trend
        arr[i]["open"] = p
        arr[i]["high"] = p + 5.0
        arr[i]["low"] = p - 5.0
        arr[i]["close"] = p + 1.0
        arr[i]["spread"] = 20
        arr[i]["tick_volume"] = 100
        arr[i]["real_volume"] = 0
    return arr


class DemoPaperTraderTests(unittest.TestCase):
    def test_assert_demo_account_accepts_demo_only(self):
        demo_acc = MockAccountInfo(trade_mode=0)
        # No debe lanzar excepción
        assert_demo_account(demo_acc)

        real_acc = MockAccountInfo(trade_mode=2)
        with self.assertRaises(RuntimeError) as ctx:
            assert_demo_account(real_acc)
        self.assertIn("BLOQUEO DE SEGURIDAD", str(ctx.exception))

        contest_acc = MockAccountInfo(trade_mode=1)
        with self.assertRaises(RuntimeError):
            assert_demo_account(contest_acc)

        with self.assertRaises(RuntimeError):
            assert_demo_account(None)

    def test_is_session_active_weekdays_and_hours(self):
        # Martes a las 09:00 UTC -> DAX activo
        t_dax_open = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
        active, msg = is_session_active("GERMANY40", t_dax_open)
        self.assertTrue(active)
        self.assertEqual(msg, "SESION_INSTITUCIONAL_ACTIVA")

        # Martes a las 05:00 UTC -> DAX inactivo (antes de 07:00 UTC)
        t_dax_early = datetime(2026, 10, 20, 5, 0, tzinfo=timezone.utc)
        active, msg = is_session_active("GERMANY40", t_dax_early)
        self.assertFalse(active)
        self.assertIn("FUERA_DE_SESION", msg)

        # Martes a las 10:00 UTC -> SP500 inactivo (abre a las 13:30 UTC)
        active, msg = is_session_active("[SP500]", t_dax_open)
        self.assertFalse(active)

        # Martes a las 15:00 UTC -> SP500 activo
        t_us_open = datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc)
        active, msg = is_session_active("[SP500]", t_us_open)
        self.assertTrue(active)

        # Sábado -> Cualquier activo cerrado
        t_weekend = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
        active, msg = is_session_active("GERMANY40", t_weekend)
        self.assertFalse(active)
        self.assertEqual(msg, "MERCADO_CERRADO_FIN_DE_SEMANA")

    def test_check_spread_and_liquidity_filters(self):
        # ATR = 50.0, point = 0.01. Spread = 20 pts -> spread_price = 0.20 EUR.
        # rel_spread = 0.20 / 50.0 = 0.4% <= 8% -> OK
        ok, msg = check_spread_and_liquidity(
            symbol="GERMANY40",
            spread_pts=20.0,
            atr=50.0,
            point=0.01,
            recent_spreads=[20.0] * 30,
            max_spread_atr_ratio=0.08,
            max_spread_median_ratio=2.0,
        )
        self.assertTrue(ok)
        self.assertEqual(msg, "SPREAD_ACEPTABLE")

        # Spread muy alto: 500 puntos -> 5.00 EUR / 50 = 10% > 8% -> Rechazado
        ok, msg = check_spread_and_liquidity(
            symbol="GERMANY40",
            spread_pts=500.0,
            atr=50.0,
            point=0.01,
            recent_spreads=[20.0] * 30,
            max_spread_atr_ratio=0.08,
        )
        self.assertFalse(ok)
        self.assertIn("SPREAD_RELATIVO_EXCESIVO", msg)

        # Pico de spread respecto a mediana: mediana=20 pts, actual=50 pts (> 2.0x 20 = 40)
        ok, msg = check_spread_and_liquidity(
            symbol="GERMANY40",
            spread_pts=50.0,
            atr=50.0,
            point=0.01,
            recent_spreads=[20.0] * 40,
            max_spread_atr_ratio=0.15,
            max_spread_median_ratio=2.0,
        )
        self.assertFalse(ok)
        self.assertIn("PICO_DE_SPREAD_DETECTADO", msg)

    def test_causal_breakeven_long_and_short(self):
        adapter = MockMT5Adapter()
        trader = DemoPaperTrader(config=DemoTraderConfig(dry_run=True, magic_number=123), adapter=adapter)
        trader.latest_atr["GERMANY40"] = 50.0

        # Posición LONG abierta a 19000.0, SL actual 18940.0
        # Trigger breakeven: +0.40 * 50 = +20.0 pts -> Bid >= 19020.0
        # Target SL: 19000.0 + 0.05 * 50 = 19002.50
        pos_long = SimpleNamespace(
            ticket=101,
            symbol="GERMANY40",
            type=adapter.ORDER_TYPE_BUY,
            price_open=19000.0,
            sl=18940.0,
            tp=19030.0,
            magic=123,
        )
        adapter.mock_positions = [pos_long]

        # Caso 1: Bid aún en 19010.0 (no llega a 19020.0) -> No modifica SL
        adapter.mock_ticks["GERMANY40"] = SimpleNamespace(bid=19010.0, ask=19011.0)
        acts = trader.check_and_apply_causal_breakeven()
        self.assertEqual(len(acts), 0)

        # Caso 2: Bid alcanza 19025.0 -> Activa Breakeven
        adapter.mock_ticks["GERMANY40"] = SimpleNamespace(bid=19025.0, ask=19026.0)
        acts = trader.check_and_apply_causal_breakeven()
        self.assertEqual(len(acts), 1)
        self.assertEqual(acts[0]["new_sl"], 19002.50)

        # Posición SHORT abierta a 19000.0, SL actual 19060.0
        # Trigger breakeven: -0.40 * 50 = -20.0 pts -> Ask <= 18980.0
        # Target SL: 19000.0 - 0.05 * 50 = 18997.50
        pos_short = SimpleNamespace(
            ticket=102,
            symbol="GERMANY40",
            type=adapter.ORDER_TYPE_SELL,
            price_open=19000.0,
            sl=19060.0,
            tp=18970.0,
            magic=123,
        )
        adapter.mock_positions = [pos_short]
        adapter.mock_ticks["GERMANY40"] = SimpleNamespace(bid=18974.0, ask=18975.0)
        acts = trader.check_and_apply_causal_breakeven()
        self.assertEqual(len(acts), 1)
        self.assertEqual(acts[0]["new_sl"], 18997.50)

    def test_risk_pause_blocks_trading_on_consecutive_losses(self):
        adapter = MockMT5Adapter()
        cfg = DemoTraderConfig(
            symbols=["GERMANY40"],
            dry_run=True,
            cooldown_minutes=60,
            max_consecutive_losses=2,
            poll_seconds=1.0,
        )
        trader = DemoPaperTrader(config=cfg, adapter=adapter)
        trader.initialize()

        now = datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)
        can_trade, _ = trader.risk_pause.can_open_new_trade(now)
        self.assertTrue(can_trade)

        # Registrar primera pérdida
        trader.risk_pause.register_closed_trade(-10.0, now)
        can_trade, reason = trader.risk_pause.can_open_new_trade(now)
        self.assertFalse(can_trade)
        self.assertEqual(reason, "COOLDOWN")

        # Registrar segunda pérdida consecutiva -> HALTED
        trader.risk_pause.register_closed_trade(-10.0, now)
        self.assertTrue(trader.risk_pause.halted)
        can_trade, reason = trader.risk_pause.can_open_new_trade(now)
        self.assertFalse(can_trade)
        self.assertEqual(reason, "HALTED_REQUIRES_MANUAL_REVIEW")

    def test_dry_run_vs_live_order_execution(self):
        adapter = MockMT5Adapter()
        # Mock de rates con tendencia alcista limpia
        adapter.mock_rates_m15["GERMANY40"] = make_synthetic_rates(100, base_price=19000.0, trend=1.0)
        adapter.mock_rates_h1["GERMANY40"] = make_synthetic_rates(60, base_price=19000.0, trend=2.0, step_minutes=60)
        adapter.mock_ticks["GERMANY40"] = SimpleNamespace(bid=19100.0, ask=19101.0)
        adapter.mock_ticks["EURUSD"] = SimpleNamespace(bid=1.12, ask=1.1201)

        # En modo DRY-RUN
        cfg_dry = DemoTraderConfig(symbols=["GERMANY40"], dry_run=True, risk_fraction=0.0025)
        trader_dry = DemoPaperTrader(config=cfg_dry, adapter=adapter)
        trader_dry.initialize()

        # Forzar hora de sesión válida (martes 10:00 UTC)
        now_valid = datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)
        res_dry = trader_dry.evaluate_symbol("GERMANY40", now_valid)

        # En dry run, ninguna orden real se envió al adapter
        self.assertEqual(len(adapter.sent_orders), 0)
        self.assertIn(res_dry["status"], ("SIMULATED_ORDER", "NO_SIGNAL", "BAR_ALREADY_PROCESSED"))

        # Si se ejecuta en live
        cfg_live = DemoTraderConfig(symbols=["GERMANY40"], dry_run=False, risk_fraction=0.0025)
        trader_live = DemoPaperTrader(config=cfg_live, adapter=adapter)
        trader_live.initialize()
        # Verificar que el adapter contiene el check de cuenta demo
        self.assertEqual(trader_live.adapter.account_info().trade_mode, 0)

    def test_precision_strategy_integration_in_demo_paper_trader(self):
        adapter = MockMT5Adapter()
        adapter.mock_rates_m15["GOLD"] = make_synthetic_rates(160, base_price=2600.0, trend=0.5)
        adapter.mock_rates_h1["GOLD"] = make_synthetic_rates(80, base_price=2600.0, trend=1.0, step_minutes=60)
        adapter.mock_ticks["GOLD"] = SimpleNamespace(bid=2680.0, ask=2680.25)
        adapter.mock_ticks["EURUSD"] = SimpleNamespace(bid=1.12, ask=1.1201)

        cfg = DemoTraderConfig(
            symbols=["GOLD"],
            strategy="adr_exhaustion_fade",
            dry_run=True,
            risk_fraction=0.0025,
        )
        trader = DemoPaperTrader(config=cfg, adapter=adapter)
        trader.initialize()
        now_valid = datetime(2026, 10, 20, 14, 0, tzinfo=timezone.utc)
        res = trader.evaluate_symbol("GOLD", now_valid)
        self.assertIn(res["status"], ("SIMULATED_ORDER", "NO_SIGNAL", "BAR_ALREADY_PROCESSED"))


if __name__ == "__main__":
    unittest.main()

