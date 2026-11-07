"""Operador Fantasma de Trading Simulado en Sombra (Ghost Shadow Paper Trader).

Ejecuta en paralelo a la cuenta real en MetaTrader 5 sin interferir ni enviar
órdenes al bróker (Modo Solo Lectura). Permite evaluar en directo la Arquitectura Híbrida:
1. Índices (DAX, S&P 500, Nasdaq, Dow) y ORO en M30:
   - Salida Híbrida 70/30:
     - 70% de la posición se cierra en el TP rápido (asegura tasa de acierto > 75%).
     - El Stop Loss se mueve a Breakeven.
     - 30% restante corre como 'Runner' persiguiendo la tendencia detrás de la media EMA20.
2. Divisas (EURUSD) en H1:
   - Estrategia de Reversión a la Media en H1 (Bollinger 2.5σ + RSI(2) + KER10).
   - TP: +40 pips | SL: -35 pips (elimina fricción del spread en M15).

Persistencia atómica en `data/ghost_trader_state.json` para consulta en tiempo real desde el Dashboard.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from trading_v2.backtesting.contract_specs import ContractSpec, calculate_lot_size, get_contract_spec
from trading_v2.execution.demo_paper_trader import (
    SESSION_WINDOWS_UTC,
    is_opening_bell_active,
    is_session_active,
    normalize_symbol_key,
)
from trading_v2.execution.macro_news_filter import MacroNewsFilter
from trading_v2.strategies.micro_scalping import (
    SniperScalpConfig,
    compute_sniper_indicators,
    generate_sniper_signals,
)


@dataclass
class GhostPosition:
    ticket: int
    symbol: str
    direction: int  # 1 = BUY / LONG, -1 = SELL / SHORT
    open_time_utc: str
    entry_price: float
    initial_sl: float
    current_sl: float
    fixed_tp: float
    lots_total: float
    lots_70: float
    lots_30: float
    status: str  # "ACTIVE_FULL", "TRANCHE_70_CLOSED", "TRAILING_RUNNER", "CLOSED"
    pnl_70_eur: float = 0.0
    pnl_30_eur: float = 0.0
    exit_price_70: float | None = None
    exit_price_30: float | None = None
    exit_time_utc: str | None = None
    exit_reason: str | None = None
    net_pnl_eur: float = 0.0
    current_floating_pnl_eur: float = 0.0
    strategy_tag: str = "HYBRID_70_30_M30"


@dataclass
class GhostTraderConfig:
    symbols: list[str] = field(
        default_factory=lambda: ["GERMANY40", "[SP500]", "US100", "[DJI30]", "GOLD", "[IBEX35]", "EURUSD"]
    )
    initial_capital: float = 3000.00
    risk_fraction: float = 0.0100  # 1.00% por trade
    runner_ratio: float = 0.30     # 30% runner, 70% TP rápido
    poll_seconds: float = 15.0
    state_file: Path = Path("data/ghost_trader_state.json")
    enable_news_blackout: bool = True
    enable_opening_bell_filter: bool = True


class GhostShadowTrader:
    """Motor autónomo de trading simulado en sombra para pruebas A/B en vivo."""

    def __init__(self, config: GhostTraderConfig | None = None, mt5_backend: Any = None):
        self.cfg = config or GhostTraderConfig()
        self.backend = mt5_backend
        self.balance: float = self.cfg.initial_capital
        self.equity: float = self.cfg.initial_capital
        self.open_positions: list[GhostPosition] = []
        self.closed_trades: list[dict] = []
        self.next_ticket: int = 9000001
        self.last_traded_bar_time: dict[str, int] = {}
        self.news_filter = MacroNewsFilter()
        self._load_state()

    def _safe_log(self, msg: str) -> None:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        print(f"[{ts}] [FANTASMA-70/30] {msg}", flush=True)

    def initialize_backend(self) -> bool:
        if self.backend is None:
            try:
                import MetaTrader5 as mt5_mod
                self.backend = mt5_mod
            except ImportError:
                self._safe_log("ERROR: MetaTrader 5 no está instalado en este entorno.")
                return False

        if not self.backend.initialize():
            self._safe_log("ERROR: Fallo al inicializar MetaTrader 5.")
            return False

        self._safe_log(
            f"Conectado a MT5 (Modo Fantasma Solo Lectura) | Capital Virtual Base: {self.balance:.2f} EUR"
        )
        return True

    def _save_state(self) -> None:
        try:
            self.cfg.state_file.parent.mkdir(parents=True, exist_ok=True)
            wins = sum(1 for t in self.closed_trades if t.get("net_pnl_eur", 0.0) > 0)
            losses = sum(1 for t in self.closed_trades if t.get("net_pnl_eur", 0.0) < 0)
            tot = len(self.closed_trades)
            wr = (wins / tot * 100) if tot > 0 else 0.0

            gross_win = sum(t.get("net_pnl_eur", 0.0) for t in self.closed_trades if t.get("net_pnl_eur", 0.0) > 0)
            gross_loss = abs(sum(t.get("net_pnl_eur", 0.0) for t in self.closed_trades if t.get("net_pnl_eur", 0.0) < 0))
            pf = (gross_win / gross_loss) if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0)

            data = {
                "version": "1.0",
                "strategy_name": "hybrid_runner_70_30_and_h1_forex",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "virtual_initial_capital": self.cfg.initial_capital,
                "virtual_balance": round(self.balance, 2),
                "virtual_equity": round(self.equity, 2),
                "total_trades": tot,
                "wins": wins,
                "losses": losses,
                "win_rate": round(wr, 1),
                "profit_factor": round(pf, 2),
                "net_pnl_eur": round(self.balance - self.cfg.initial_capital, 2),
                "open_positions": [asdict(p) for p in self.open_positions],
                "closed_trades": self.closed_trades[-100:],  # Últimos 100 trades
                "last_traded_bar_time": self.last_traded_bar_time,
                "next_ticket": self.next_ticket,
            }

            temp_file = self.cfg.state_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(temp_file, self.cfg.state_file)
        except Exception as e:
            self._safe_log(f"Error al guardar estado: {e}")

    def _load_state(self) -> None:
        try:
            if self.cfg.state_file.exists():
                with open(self.cfg.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.balance = float(data.get("virtual_balance", self.cfg.initial_capital))
                self.equity = float(data.get("virtual_equity", self.balance))
                self.next_ticket = int(data.get("next_ticket", 9000001))
                self.last_traded_bar_time = data.get("last_traded_bar_time", {})
                self.closed_trades = data.get("closed_trades", [])
                
                open_raw = data.get("open_positions", [])
                self.open_positions = [GhostPosition(**p) for p in open_raw]
                self._safe_log(
                    f"Estado cargado: Balance={self.balance:.2f}€ | Trades={len(self.closed_trades)} | Posiciones Abiertas={len(self.open_positions)}"
                )
        except Exception as e:
            self._safe_log(f"Error al cargar estado previo: {e}")

    def get_eurusd_rate(self) -> float:
        try:
            tick = self.backend.symbol_info_tick("EURUSD")
            if tick and tick.bid > 0:
                return float(tick.bid)
        except Exception:
            pass
        return 1.1200

    def evaluate_h1_forex(self, symbol: str, now_utc: datetime) -> None:
        """Estrategia H1 Mean Reversion para Forex (EURUSD): TP +40 pips / SL -35 pips."""
        # Verificar si ya hay posición abierta en este símbolo
        if any(p.symbol == symbol for p in self.open_positions):
            return

        rates = self.backend.copy_rates_from_pos(symbol, self.backend.TIMEFRAME_H1, 1, 40)
        if rates is None or len(rates) < 30:
            return

        last_bar_time = int(rates[-1]["time"])
        if self.last_traded_bar_time.get(symbol) == last_bar_time:
            return

        df = pd.DataFrame(rates)
        c = df["close"]
        sma20 = c.rolling(20).mean()
        std20 = c.rolling(20).std()
        bb_hi = sma20 + 2.5 * std20
        bb_lo = sma20 - 2.5 * std20

        delta = c.diff()
        up = delta.clip(lower=0)
        down = -delta.clip(upper=0)
        rs = up.rolling(2).mean() / down.rolling(2).mean().replace(0, np.nan)
        rsi2 = 100 - (100 / (1 + rs))

        direction = (c - c.shift(10)).abs()
        volatility = c.diff().abs().rolling(10).sum()
        ker10 = direction / volatility.replace(0, np.nan)

        last_c = c.iloc[-1]
        last_rsi = rsi2.iloc[-1]
        last_ker = ker10.iloc[-1]

        sig = 0
        if last_c < bb_lo.iloc[-1] and last_rsi < 10.0 and last_ker < 0.40:
            sig = 1
        elif last_c > bb_hi.iloc[-1] and last_rsi > 90.0 and last_ker < 0.40:
            sig = -1

        if sig == 0:
            return

        tick = self.backend.symbol_info_tick(symbol)
        if not tick:
            return

        entry_px = float(tick.ask) if sig == 1 else float(tick.bid)
        sl_pips = 35.0
        tp_pips = 40.0
        unit_m = 0.00010

        sl_price_dist = sl_pips * unit_m
        initial_sl = entry_px - sig * sl_price_dist
        fixed_tp = entry_px + sig * (tp_pips * unit_m)

        spec = get_contract_spec(symbol, broker="admirals")
        eurusd_rate = self.get_eurusd_rate()
        lot_res = calculate_lot_size(
            spec=spec,
            account_equity=self.balance,
            risk_fraction=self.cfg.risk_fraction,
            stop_distance_price=sl_price_dist,
            entry_price=entry_px,
            eurusd_rate=eurusd_rate,
        )

        if lot_res.lots <= 0:
            return

        pos = GhostPosition(
            ticket=self.next_ticket,
            symbol=symbol,
            direction=sig,
            open_time_utc=now_utc.isoformat(),
            entry_price=entry_px,
            initial_sl=initial_sl,
            current_sl=initial_sl,
            fixed_tp=fixed_tp,
            lots_total=lot_res.lots,
            lots_70=lot_res.lots,  # 100% de la posición en el swing
            lots_30=0.0,
            status="ACTIVE_FULL",
            strategy_tag="FOREX_H1_SWING",
        )
        self.next_ticket += 1
        self.open_positions.append(pos)
        self.last_traded_bar_time[symbol] = last_bar_time
        dir_str = "COMPRA (LONG)" if sig == 1 else "VENTA (SHORT)"
        self._safe_log(
            f"🎯 [NUEVO TRADE FANTASMA] {symbol} {dir_str} {lot_res.lots} lotes a {entry_px:.5f} | TP={fixed_tp:.5f} (+40 pips) | SL={initial_sl:.5f} (-35 pips)"
        )
        self._save_state()

    def evaluate_m30_hybrid(self, symbol: str, now_utc: datetime) -> None:
        """Estrategia Híbrida 70/30 para Índices y Oro en M30."""
        if any(p.symbol == symbol for p in self.open_positions):
            return

        # 1. Filtros de sesión y de campana de apertura (Opción A1)
        session_ok, _ = is_session_active(symbol, now_utc)
        if not session_ok:
            return

        if self.cfg.enable_opening_bell_filter:
            bell_blocked, _ = is_opening_bell_active(symbol, now_utc)
            if bell_blocked:
                return

        if self.cfg.enable_news_blackout:
            news_blocked, _ = self.news_filter.is_blackout_active(symbol, now_utc)
            if news_blocked:
                return

        tf = self.backend.TIMEFRAME_M15 if "IBEX" in symbol else self.backend.TIMEFRAME_M30
        rates = self.backend.copy_rates_from_pos(symbol, tf, 1, 60)
        if rates is None or len(rates) < 40:
            return

        last_bar_time = int(rates[-1]["time"])
        if self.last_traded_bar_time.get(symbol) == last_bar_time:
            return

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.set_index("time", inplace=True)
        df.rename(
            columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "tick_volume": "Volume"},
            inplace=True,
        )

        is_dax = "GERMANY" in symbol or "DE40" in symbol
        is_sp = "SP500" in symbol or "US500" in symbol
        is_nasdaq = "US100" in symbol or "USTEC" in symbol
        is_dji = "DJI" in symbol or "US30" in symbol
        is_gold = "GOLD" in symbol or "XAU" in symbol
        is_ibex = "IBEX" in symbol

        if is_dax:
            target_u, stop_u, s_start, s_end, allow_s, min_w = 22.0, 35.0, 7, 17, True, 0.35
            max_opp = None
        elif is_sp:
            target_u, stop_u, s_start, s_end, allow_s, min_w = 4.0, 12.0, 13, 21, False, 0.35
            max_opp = None
        elif is_nasdaq:
            target_u, stop_u, s_start, s_end, allow_s, min_w = 25.0, 70.0, 13, 21, False, 0.35
            max_opp = None
        elif is_dji:
            target_u, stop_u, s_start, s_end, allow_s, min_w = 40.0, 80.0, 13, 21, False, 0.35
            max_opp = None
        elif is_gold:
            target_u, stop_u, s_start, s_end, allow_s, min_w = 4.0, 12.0, 13, 19, False, 0.45
            max_opp = 0.12
        elif is_ibex:
            target_u, stop_u, s_start, s_end, allow_s, min_w = 20.0, 45.0, 7, 17, False, 0.35
            max_opp = None
        else:
            return

        cfg = SniperScalpConfig(
            symbol=symbol,
            target_units=target_u,
            stop_units=stop_u,
            session_start_h=s_start,
            session_end_h=s_end,
            min_rejection_wick=min_w,
            max_opposite_wick=max_opp,
            use_h1_filter=True,
            use_ker_filter=True,
            max_ker_trend=0.45,
            cooldown_bars=2,
            use_climax_filter=True,
            allow_short=allow_s,
        )

        sig_df = generate_sniper_signals(df, cfg)
        sig = int(sig_df["signal"].iloc[-1])

        if sig == 0:
            return

        tick = self.backend.symbol_info_tick(symbol)
        if not tick:
            return

        entry_px = float(tick.ask) if sig == 1 else float(tick.bid)
        spec = get_contract_spec(symbol, broker="admirals")
        eurusd_rate = self.get_eurusd_rate()

        lot_res = calculate_lot_size(
            spec=spec,
            account_equity=self.balance,
            risk_fraction=self.cfg.risk_fraction,
            stop_distance_price=stop_u,
            entry_price=entry_px,
            eurusd_rate=eurusd_rate,
        )

        lots_total = lot_res.lots
        if lots_total <= 0:
            return
        lots_30 = round(lots_total * self.cfg.runner_ratio, 2)
        if lots_30 < spec.lot_min:
            lots_30 = spec.lot_min
        lots_70 = round(lots_total - lots_30, 2)
        if lots_70 < spec.lot_min:
            lots_70 = spec.lot_min
            lots_total = round(lots_70 + lots_30, 2)

        initial_sl = round(entry_px - sig * stop_u, spec.digits)
        fixed_tp = round(entry_px + sig * target_u, spec.digits)

        if lot_res.lots <= 0:
            return

        pos = GhostPosition(
            ticket=self.next_ticket,
            symbol=symbol,
            direction=sig,
            open_time_utc=now_utc.isoformat(),
            entry_price=entry_px,
            initial_sl=initial_sl,
            current_sl=initial_sl,
            fixed_tp=fixed_tp,
            lots_total=lots_total,
            lots_70=lots_70,
            lots_30=lots_30,
            status="ACTIVE_FULL",
            strategy_tag="HYBRID_70_30_M30",
        )
        self.next_ticket += 1
        self.open_positions.append(pos)
        self.last_traded_bar_time[symbol] = last_bar_time
        dir_str = "COMPRA (LONG)" if sig == 1 else "VENTA (SHORT)"
        self._safe_log(
            f"🎯 [NUEVO TRADE HÍBRIDO FANTASMA] {symbol} {dir_str} {lots_total} lotes (70%={lots_70}, 30%={lots_30}) a {entry_px} | TP Fijo={fixed_tp} (+{target_u}) | SL={initial_sl} (-{stop_u})"
        )
        self._save_state()

    def update_open_positions(self, now_utc: datetime) -> None:
        """Monitorea cotizaciones en tiempo real, ejecuta salidas parciales y gestiona el trailing stop del 30%."""
        if not self.open_positions:
            self.equity = self.balance
            return

        eurusd_rate = self.get_eurusd_rate()
        still_open: list[GhostPosition] = []
        total_floating = 0.0

        for pos in self.open_positions:
            tick = self.backend.symbol_info_tick(pos.symbol)
            if not tick:
                still_open.append(pos)
                continue

            bid = float(tick.bid)
            ask = float(tick.ask)
            curr_px = bid if pos.direction == 1 else ask
            spec = get_contract_spec(pos.symbol, broker="admirals")

            # Cálculo de PnL flotante
            point_diff = (curr_px - pos.entry_price) if pos.direction == 1 else (pos.entry_price - curr_px)
            pts = point_diff / spec.point
            pts_val = spec.contract_size * spec.point
            active_lots = pos.lots_30 if pos.status == "TRAILING_RUNNER" else pos.lots_total
            if "EUR" in spec.profit_currency:
                floating_eur = pts * pts_val * active_lots
            else:
                floating_eur = (pts * pts_val * active_lots) / eurusd_rate

            pos.current_floating_pnl_eur = round(floating_eur, 2)
            total_floating += floating_eur

            # Caso 1: Swing Forex H1
            if pos.strategy_tag == "FOREX_H1_SWING":
                tp_hit = (curr_px >= pos.fixed_tp) if pos.direction == 1 else (curr_px <= pos.fixed_tp)
                sl_hit = (curr_px <= pos.current_sl) if pos.direction == 1 else (curr_px >= pos.current_sl)

                if tp_hit:
                    pos.status = "CLOSED"
                    pos.exit_reason = "TAKE_PROFIT_H1"
                    pos.exit_price_70 = pos.fixed_tp
                    pos.exit_time_utc = now_utc.isoformat()
                    pos.net_pnl_eur = round(floating_eur, 2)
                    self.balance += pos.net_pnl_eur
                    self.closed_trades.append(asdict(pos))
                    self._safe_log(
                        f"✅ [CIERRE FOREX TP] {pos.symbol} Ticket #{pos.ticket} alcanzó TP (+40 pips). PnL: +{pos.net_pnl_eur:.2f} €"
                    )
                    continue
                elif sl_hit:
                    pos.status = "CLOSED"
                    pos.exit_reason = "STOP_LOSS_H1"
                    pos.exit_price_70 = pos.current_sl
                    pos.exit_time_utc = now_utc.isoformat()
                    pos.net_pnl_eur = round(floating_eur, 2)
                    self.balance += pos.net_pnl_eur
                    self.closed_trades.append(asdict(pos))
                    self._safe_log(
                        f"🛑 [CIERRE FOREX SL] {pos.symbol} Ticket #{pos.ticket} tocó SL (-35 pips). PnL: {pos.net_pnl_eur:.2f} €"
                    )
                    continue
                else:
                    still_open.append(pos)
                    continue

            # Caso 2: Arquitectura Híbrida 70/30 (Índices y Oro)
            if pos.status == "ACTIVE_FULL":
                # Comprobar si toca el SL inicial (Pérdida total del 1%)
                sl_hit = (curr_px <= pos.current_sl) if pos.direction == 1 else (curr_px >= pos.current_sl)
                if sl_hit:
                    pos.status = "CLOSED"
                    pos.exit_reason = "FULL_STOP_LOSS"
                    pos.exit_price_70 = pos.current_sl
                    pos.exit_price_30 = pos.current_sl
                    pos.exit_time_utc = now_utc.isoformat()
                    pos.net_pnl_eur = round(floating_eur, 2)
                    self.balance += pos.net_pnl_eur
                    self.closed_trades.append(asdict(pos))
                    self._safe_log(
                        f"🛑 [SL COMPLETO] {pos.symbol} Ticket #{pos.ticket} tocó SL inicial. PnL: {pos.net_pnl_eur:.2f} €"
                    )
                    continue

                # Comprobar si toca el TP del 70%
                tp_hit = (curr_px >= pos.fixed_tp) if pos.direction == 1 else (curr_px <= pos.fixed_tp)
                if tp_hit:
                    # Cerrar 70% de la posición y cobrar
                    fixed_diff = (pos.fixed_tp - pos.entry_price) if pos.direction == 1 else (pos.entry_price - pos.fixed_tp)
                    gain_70 = (fixed_diff / spec.point) * pts_val * pos.lots_70
                    if "EUR" not in spec.profit_currency:
                        gain_70 /= eurusd_rate
                    pnl_70 = round(gain_70, 2)
                    pos.pnl_70_eur = pnl_70
                    pos.exit_price_70 = pos.fixed_tp
                    pos.status = "TRAILING_RUNNER"
                    # Mover Stop Loss de la posición restante a Breakeven
                    pos.current_sl = pos.entry_price
                    self.balance += pnl_70
                    self._safe_log(
                        f"💰 [PARCIAL 70% COBRADO] {pos.symbol} Ticket #{pos.ticket} alcanzó TP fijo. +{pnl_70:.2f} € asegurados. Activando 30% Runner Trailing EMA20..."
                    )
                    still_open.append(pos)
                    continue
                else:
                    still_open.append(pos)
                    continue

            elif pos.status == "TRAILING_RUNNER":
                # 30% Runner persiguiendo la media móvil EMA20 en M30
                tf = self.backend.TIMEFRAME_M15 if "IBEX" in pos.symbol else self.backend.TIMEFRAME_M30
                rates = self.backend.copy_rates_from_pos(pos.symbol, tf, 1, 25)
                if rates is not None and len(rates) >= 20:
                    c_arr = pd.Series([r["close"] for r in rates])
                    ema20 = float(c_arr.ewm(span=20, adjust=False).mean().iloc[-1])

                    # Trailing dinámico:
                    if pos.direction == 1:
                        if ema20 > pos.current_sl:
                            pos.current_sl = round(ema20, spec.digits)
                        # Salida si el precio perfora el Stop Trailing o la EMA20
                        if curr_px <= pos.current_sl:
                            pos.status = "CLOSED"
                            pos.exit_reason = "RUNNER_TRAILING_EMA20"
                            pos.exit_price_30 = curr_px
                            pos.exit_time_utc = now_utc.isoformat()
                            diff_30 = (curr_px - pos.entry_price) / spec.point
                            gain_30 = (diff_30 * spec.contract_size * spec.point * pos.lots_30)
                            if "EUR" not in spec.profit_currency:
                                gain_30 /= eurusd_rate
                            pos.pnl_30_eur = round(gain_30, 2)
                            pos.net_pnl_eur = round(pos.pnl_70_eur + pos.pnl_30_eur, 2)
                            self.balance += pos.pnl_30_eur
                            self.closed_trades.append(asdict(pos))
                            self._safe_log(
                                f"🏁 [RUNNER 30% CERRADO] {pos.symbol} Ticket #{pos.ticket} cerró tras cruce EMA20 a {curr_px}. PnL Runner: {pos.pnl_30_eur:+.2f} € | PnL Total Trade: {pos.net_pnl_eur:+.2f} €"
                            )
                            continue
                    else:  # SHORT
                        if ema20 < pos.current_sl:
                            pos.current_sl = round(ema20, spec.digits)
                        if curr_px >= pos.current_sl:
                            pos.status = "CLOSED"
                            pos.exit_reason = "RUNNER_TRAILING_EMA20"
                            pos.exit_price_30 = curr_px
                            pos.exit_time_utc = now_utc.isoformat()
                            diff_30 = (pos.entry_price - curr_px) / spec.point
                            gain_30 = (diff_30 * spec.contract_size * spec.point * pos.lots_30)
                            if "EUR" not in spec.profit_currency:
                                gain_30 /= eurusd_rate
                            pos.pnl_30_eur = round(gain_30, 2)
                            pos.net_pnl_eur = round(pos.pnl_70_eur + pos.pnl_30_eur, 2)
                            self.balance += pos.pnl_30_eur
                            self.closed_trades.append(asdict(pos))
                            self._safe_log(
                                f"🏁 [RUNNER 30% CERRADO] {pos.symbol} Ticket #{pos.ticket} cerró tras cruce EMA20 a {curr_px}. PnL Runner: {pos.pnl_30_eur:+.2f} € | PnL Total Trade: {pos.net_pnl_eur:+.2f} €"
                            )
                            continue

                still_open.append(pos)

        self.open_positions = still_open
        self.equity = round(self.balance + total_floating, 2)
        self._save_state()

    def run_cycle(self) -> None:
        """Ejecuta un ciclo completo de escaneo y gestión de posiciones virtuales."""
        now_utc = datetime.now(timezone.utc)
        self.update_open_positions(now_utc)

        for sym in self.cfg.symbols:
            if "EURUSD" in sym:
                self.evaluate_h1_forex(sym, now_utc)
            else:
                self.evaluate_m30_hybrid(sym, now_utc)

        self._save_state()

    def run_forever(self) -> None:
        """Bucle infinito de escaneo desatendido para el Operador Fantasma."""
        self._safe_log("Iniciando escaneo continuo del Operador Fantasma...")
        try:
            while True:
                self.run_cycle()
                time.sleep(self.cfg.poll_seconds)
        except KeyboardInterrupt:
            self._safe_log("Detención manual por usuario.")
        except Exception as e:
            self._safe_log(f"Error fatal en Operador Fantasma: {e}")


def main():
    trader = GhostShadowTrader()
    if not trader.initialize_backend():
        sys.exit(1)
    trader.run_forever()


if __name__ == "__main__":
    main()
