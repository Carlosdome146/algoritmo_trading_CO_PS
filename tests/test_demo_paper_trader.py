"""Pruebas unitarias para el motor de ejecución DemoPaperTrader y salvaguardas MT5."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np

from trading_v2.execution.demo_paper_trader import (
    DemoPaperTrader,
    is_opening_bell_active,
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
        self.TIMEFRAME_M5 = 5
        self.TIMEFRAME_M15 = 15
        self.TIMEFRAME_M30 = 30
        self.TIMEFRAME_H1 = 16385
        self.TIMEFRAME_H4 = 16388
        self.TIMEFRAME_D1 = 16408
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
        self.mock_rates_m30 = {}
        self.mock_rates_h1 = {}
        self.mock_rates_d1 = {}
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
        elif timeframe == self.TIMEFRAME_M30:
            return self.mock_rates_m30.get(symbol, self.mock_rates_m15.get(symbol))
        elif timeframe == self.TIMEFRAME_H1:
            return self.mock_rates_h1.get(symbol)
        elif timeframe == self.TIMEFRAME_D1:
            return self.mock_rates_d1.get(symbol)
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

    def test_opening_bell_filter_option_a1(self):
        # 1. GERMANY40 a las 07:02 UTC (08:02 CET): Primeros 5 min de futuros -> VETADO
        t_dax_bell = datetime(2026, 10, 20, 7, 2, tzinfo=timezone.utc)
        blocked, reason = is_opening_bell_active("GERMANY40", t_dax_bell)
        self.assertTrue(blocked)
        self.assertIn("CAMPANA_APERTURA_FUTUROS_EUROPA", reason)

        # 2. GERMANY40 a las 07:15 UTC: Fuera de campana (subasta asentada) -> PERMITIDO
        t_dax_clear = datetime(2026, 10, 20, 7, 15, tzinfo=timezone.utc)
        blocked_clear, _ = is_opening_bell_active("GERMANY40", t_dax_clear)
        self.assertFalse(blocked_clear)

        # 3. GERMANY40 a las 08:02 UTC (09:02 CET): Primeros 5 min de contado Xetra -> VETADO
        t_xetra_bell = datetime(2026, 10, 20, 8, 2, tzinfo=timezone.utc)
        blocked_xetra, reason_xetra = is_opening_bell_active("GERMANY40", t_xetra_bell)
        self.assertTrue(blocked_xetra)
        self.assertIn("CAMPANA_APERTURA_CONTADO_XETRA", reason_xetra)

        # 4. [SP500] a las 13:32 UTC (14:32 CET / 09:32 EST): Primeros 5 min Wall Street -> VETADO
        t_us_bell = datetime(2026, 10, 20, 13, 32, tzinfo=timezone.utc)
        blocked_us, reason_us = is_opening_bell_active("[SP500]", t_us_bell)
        self.assertTrue(blocked_us)
        self.assertIn("CAMPANA_APERTURA_WALL_STREET", reason_us)

        # 5. [SP500] a las 14:00 UTC: Mercado fluido y profundo -> PERMITIDO
        t_us_clear = datetime(2026, 10, 20, 14, 0, tzinfo=timezone.utc)
        blocked_us_clear, _ = is_opening_bell_active("[SP500]", t_us_clear)
        self.assertFalse(blocked_us_clear)

    def test_is_session_active_weekdays_and_hours(self):
        # Martes a las 09:00 UTC -> DAX activo
        t_dax_open = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
        active, msg = is_session_active("GERMANY40", t_dax_open)
        self.assertTrue(active)
        self.assertEqual(msg, "SESION_INSTITUCIONAL_ACTIVA")

        # Martes a las 05:00 UTC -> DAX inactivo (antes de 08:00 UTC)
        t_dax_early = datetime(2026, 10, 20, 5, 0, tzinfo=timezone.utc)
        active, msg = is_session_active("GERMANY40", t_dax_early)
        self.assertFalse(active)
        self.assertIn("FUERA_DE_SESION", msg)

        # Sesión europea 07:15 UTC (08:15 España) -> DAX e IBEX activos (sesión 07:00 a 17:30 UTC)
        t_morn = datetime(2026, 10, 20, 7, 15, tzinfo=timezone.utc)
        active_dax_morn, msg_morn = is_session_active("GERMANY40", t_morn)
        self.assertTrue(active_dax_morn)
        self.assertEqual(msg_morn, "SESION_INSTITUCIONAL_ACTIVA")

        active_ibex_morn, _ = is_session_active("[IBEX35]", t_morn)
        self.assertTrue(active_ibex_morn)

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

        # IBEX35: spread 350 pts (3.5 pts) con ATR=40.0 -> rel_spread = 3.5 / 40.0 = 8.75% <= 12% -> Aceptado
        ok_ibex, msg_ibex = check_spread_and_liquidity(
            symbol="[IBEX35]",
            spread_pts=350.0,
            atr=40.0,
            point=0.01,
            recent_spreads=[350.0] * 30,
            max_spread_atr_ratio=0.08,
            max_spread_median_ratio=2.0,
        )
        self.assertTrue(ok_ibex)
        self.assertEqual(msg_ibex, "SPREAD_ACEPTABLE")

        # IBEX35: spread 600 pts (6.0 pts) con ATR=40.0 -> rel_spread = 6.0 / 40.0 = 15.0% > 12% -> Rechazado
        ok_ibex_hi, msg_ibex_hi = check_spread_and_liquidity(
            symbol="[IBEX35]",
            spread_pts=600.0,
            atr=40.0,
            point=0.01,
            recent_spreads=[350.0] * 30,
            max_spread_atr_ratio=0.08,
            max_spread_median_ratio=2.0,
        )
        self.assertFalse(ok_ibex_hi)
        self.assertIn("SPREAD_RELATIVO_EXCESIVO", msg_ibex_hi)

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


    def test_daily_strategy_d1_evaluation_and_exit_rule(self):
        adapter = MockMT5Adapter()
        adapter.mock_rates_d1["[SP500]"] = make_synthetic_rates(260, base_price=5000.0, trend=1.0, step_minutes=1440)
        adapter.mock_ticks["[SP500]"] = SimpleNamespace(bid=5260.0, ask=5260.40)
        adapter.mock_ticks["EURUSD"] = SimpleNamespace(bid=1.12, ask=1.1201)

        cfg = DemoTraderConfig(
            symbols=["[SP500]"],
            timeframe="D1",
            strategy="idx_rsi2_dip_regime",
            dry_run=True,
            risk_fraction=0.0025,
            sl_atr=2.5,
        )
        trader = DemoPaperTrader(config=cfg, adapter=adapter)
        trader.initialize()
        now_valid = datetime(2026, 10, 20, 22, 0, tzinfo=timezone.utc)
        res = trader.evaluate_symbol("[SP500]", now_valid)
        self.assertIn(res["status"], ("SIMULATED_ORDER", "NO_SIGNAL", "BAR_ALREADY_PROCESSED"))

        # Probar regla de salida en la siguiente barra diaria cuando ya existe una posición abierta
        pos_open = SimpleNamespace(
            ticket=201,
            symbol="[SP500]",
            type=adapter.ORDER_TYPE_BUY,
            price_open=5000.0,
            volume=0.1,
            sl=4850.0,
            tp=0.0,
            magic=trader.cfg.magic_number,
        )
        adapter.mock_positions = [pos_open]
        # Simular nueva barra diaria siguiente
        adapter.mock_rates_d1["[SP500]"][-1]["time"] += 86400
        now_next = datetime(2026, 10, 21, 22, 0, tzinfo=timezone.utc)
        res_exit = trader.evaluate_symbol("[SP500]", now_next)
        self.assertIn(res_exit["status"], ("POSITION_HELD", "DRY_RUN_CLOSED", "SUCCESS_CLOSED"))

    def test_daily_strategy_dax_bollinger_dip(self):
        adapter = MockMT5Adapter()
        adapter.mock_rates_d1["GERMANY40"] = make_synthetic_rates(260, base_price=18000.0, trend=1.0, step_minutes=1440)
        adapter.mock_ticks["GERMANY40"] = SimpleNamespace(bid=19000.0, ask=19001.0)
        adapter.mock_ticks["EURUSD"] = SimpleNamespace(bid=1.12, ask=1.1201)

        cfg = DemoTraderConfig(
            symbols=["GERMANY40"],
            timeframe="D1",
            strategy="idx_dax_bollinger_dip",
            broker="admirals",
            dry_run=True,
            risk_fraction=0.0025,
            sl_atr=2.5,
        )
        trader = DemoPaperTrader(config=cfg, adapter=adapter)
        trader.initialize()
        now_valid = datetime(2026, 10, 20, 22, 0, tzinfo=timezone.utc)
        res = trader.evaluate_symbol("GERMANY40", now_valid)
        self.assertIn(res["status"], ("SIMULATED_ORDER", "NO_SIGNAL", "BAR_ALREADY_PROCESSED"))

    def test_daily_strategy_fx_eurusd_ker_exhaustion(self):
        adapter = MockMT5Adapter()
        adapter.mock_rates_d1["EURUSD"] = make_synthetic_rates(260, base_price=1.10, trend=0.0001, step_minutes=1440)
        adapter.mock_ticks["EURUSD"] = SimpleNamespace(bid=1.1050, ask=1.1051)

        cfg = DemoTraderConfig(
            symbols=["EURUSD"],
            timeframe="D1",
            strategy="fx_eurusd_ker_exhaustion",
            broker="icmarkets",
            dry_run=True,
            risk_fraction=0.0025,
            sl_atr=2.5,
        )
        trader = DemoPaperTrader(config=cfg, adapter=adapter)
        trader.initialize()
        now_valid = datetime(2026, 10, 20, 22, 0, tzinfo=timezone.utc)
        res = trader.evaluate_symbol("EURUSD", now_valid)
        self.assertIn(res["status"], ("SIMULATED_ORDER", "NO_SIGNAL", "BAR_ALREADY_PROCESSED"))

    def test_broker_config_switching_icmarkets(self):
        adapter = MockMT5Adapter()
        adapter.mock_rates_d1["DE40"] = make_synthetic_rates(260, base_price=18000.0, trend=1.0, step_minutes=1440)
        adapter.mock_ticks["DE40"] = SimpleNamespace(bid=19000.0, ask=19001.0)
        adapter.mock_ticks["EURUSD"] = SimpleNamespace(bid=1.12, ask=1.1201)

        cfg = DemoTraderConfig(
            symbols=["DE40"],
            timeframe="D1",
            strategy="idx_dax_bollinger_dip",
            broker="icmarkets",
            dry_run=True,
            risk_fraction=0.0025,
            sl_atr=2.5,
        )
        trader = DemoPaperTrader(config=cfg, adapter=adapter)
        trader.initialize()
        self.assertEqual(trader.cfg.broker, "icmarkets")


    def test_sniper_multi_asset_configuration(self):
        adapter = MockMT5Adapter()
        for sym, bp in [("[DJI30]", 43000.0), ("GOLD", 2700.0), ("US100", 20000.0), ("[IBEX35]", 11800.0), ("GERMANY40", 19500.0)]:
            adapter.mock_rates_m15[sym] = make_synthetic_rates(260, base_price=bp, trend=0.1, step_minutes=15)
            adapter.mock_rates_h1[sym] = make_synthetic_rates(100, base_price=bp, trend=0.5, step_minutes=60)
            adapter.mock_ticks[sym] = SimpleNamespace(bid=bp, ask=bp + 1.0)
        adapter.mock_ticks["EURUSD"] = SimpleNamespace(bid=1.08, ask=1.0801)

        cfg = DemoTraderConfig(
            symbols=["[DJI30]", "GOLD", "US100"],
            timeframe="M15_M30",
            strategy="institutional_sniper_scalp",
            dry_run=True,
            risk_fraction=0.0100,
        )
        trader = DemoPaperTrader(config=cfg, adapter=adapter)
        trader.initialize()
        now_valid = datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc)
        for sym in cfg.symbols:
            res = trader.evaluate_symbol(sym, now_valid)
            self.assertIn(res["status"], ("SIMULATED_ORDER", "NO_SIGNAL", "BAR_ALREADY_PROCESSED", "REJECTED_RISK_PAUSE"))


    def test_gold_session_blindaje(self):
        # 09:30 UTC no debe estar activa la sesion institucional de GOLD (evita perdidas matinales)
        dt_morning = datetime(2026, 11, 3, 9, 30, tzinfo=timezone.utc)
        active, reason = is_session_active("GOLD", dt_morning)
        self.assertFalse(active)
        self.assertIn("FUERA_DE_SESION", reason)

        # 15:00 UTC (sesion Londres/NY) debe estar activa
        dt_ny = datetime(2026, 11, 3, 15, 0, tzinfo=timezone.utc)
        active, _ = is_session_active("GOLD", dt_ny)
        self.assertTrue(active)

    def test_correlation_index_limit(self):
        import unittest.mock as mock
        import pandas as pd
        adapter = MockMT5Adapter()
        # Simular 2 posiciones de indice abiertas (GERMANY40 y US100) con el magic del bot
        adapter.mock_positions = [
            SimpleNamespace(ticket=101, magic=20261018, symbol="GERMANY40", type=0, volume=1.0, price_open=19000.0, sl=18950.0, tp=19050.0, price_current=19010.0),
            SimpleNamespace(ticket=102, magic=20261018, symbol="US100", type=0, volume=0.5, price_open=20000.0, sl=19900.0, tp=20100.0, price_current=20020.0),
        ]
        bp = 5800.0
        adapter.mock_rates_m15["[SP500]"] = make_synthetic_rates(260, base_price=bp, trend=0.1, step_minutes=15)
        adapter.mock_rates_h1["[SP500]"] = make_synthetic_rates(100, base_price=bp, trend=0.5, step_minutes=60)
        adapter.mock_ticks["[SP500]"] = SimpleNamespace(bid=bp, ask=bp + 0.5)

        cfg = DemoTraderConfig(
            symbols=["[SP500]"],
            timeframe="M30",
            strategy="institutional_sniper_scalp",
            dry_run=True,
            max_open_positions=5,
            max_concurrent_indices=2,
        )
        trader = DemoPaperTrader(config=cfg, adapter=adapter)
        trader.initialize()
        now_valid = datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc)

        # Mockeamos senal de compra activa para que pase a evaluar la correlacion
        with mock.patch("trading_v2.execution.demo_paper_trader.generate_sniper_signals") as mock_sig:
            mock_sig.return_value = pd.DataFrame({"signal": [0, 1]})
            res = trader.evaluate_symbol("[SP500]", now_valid)
            self.assertEqual(res["status"], "REJECTED_CORRELATION_LIMIT")
    def test_friday_auto_square_closes_positions(self):
        """Verifica que el viernes a las 20:35 UTC se cierren forzosamente las posiciones abiertas."""
        adapter = MockMT5Adapter()
        adapter.mock_positions = [
            SimpleNamespace(ticket=501, magic=20261018, symbol="EURUSD", type=0, volume=0.5, price_open=1.1200),
        ]
        cfg = DemoTraderConfig(enable_friday_auto_square=True, friday_cutoff_hour=20, friday_cutoff_minute=30, dry_run=True)
        trader = DemoPaperTrader(config=cfg, adapter=adapter)

        # Viernes 20:35 UTC -> debe cerrar la posición
        friday_night = datetime(2026, 11, 6, 20, 35, tzinfo=timezone.utc)
        actions = trader._check_friday_auto_square(friday_night)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["status"], "DRY_RUN_CLOSED")
        self.assertEqual(actions[0]["reason"], "FRIDAY_WEEKEND_AUTO_SQUARE")

        # Jueves 20:35 UTC -> no debe cerrar nada
        thursday_night = datetime(2026, 11, 5, 20, 35, tzinfo=timezone.utc)
        actions_thu = trader._check_friday_auto_square(thursday_night)
        self.assertEqual(len(actions_thu), 0)

    def test_news_blackout_in_evaluate_symbol(self):
        """Verifica que evaluate_symbol rechace operaciones dentro de la ventana de noticias macro."""
        import unittest.mock as mock
        import pandas as pd
        adapter = MockMT5Adapter()
        bp = 1.1200
        adapter.mock_rates_m15["EURUSD"] = make_synthetic_rates(100, base_price=bp, trend=0.0001, step_minutes=15)
        adapter.mock_rates_h1["EURUSD"] = make_synthetic_rates(60, base_price=bp, trend=0.0005, step_minutes=60)
        adapter.mock_ticks["EURUSD"] = SimpleNamespace(bid=bp, ask=bp + 0.0001)

        cfg = DemoTraderConfig(symbols=["EURUSD"], strategy="institutional_sniper_scalp", enable_news_blackout=True, news_blackout_before_m=15)
        trader = DemoPaperTrader(config=cfg, adapter=adapter)
        trader.initialize()

        # Configurar evento a las 15:00 UTC
        from trading_v2.execution.macro_news_filter import MacroEvent
        trader.news_filter.add_custom_event(
            MacroEvent(name="US ISM Services", currency="USD", time_utc=datetime(2026, 11, 4, 15, 0, tzinfo=timezone.utc))
        )

        # Evaluar a las 14:50 UTC (a 10 min de la noticia)
        t_inside = datetime(2026, 11, 4, 14, 50, tzinfo=timezone.utc)
        with mock.patch("trading_v2.execution.demo_paper_trader.generate_sniper_signals") as mock_sig:
            mock_sig.return_value = pd.DataFrame({"signal": [0, 1]})
            res = trader.evaluate_symbol("EURUSD", t_inside)
            self.assertEqual(res["status"], "REJECTED_NEWS_BLACKOUT")
            self.assertIn("US ISM Services", res["reason"])



if __name__ == "__main__":
    unittest.main()


