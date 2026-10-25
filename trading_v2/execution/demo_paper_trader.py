"""Motor de ejecución y Paper-Trading en MetaTrader 5 (DEMO).

Cumple estrictamente los estándares cuantitativos y de seguridad V2:
1. BLOQUEO DEMO OBLIGATORIO: Solo opera si trade_mode == ACCOUNT_TRADE_MODE_DEMO (0).
2. MODO SIMULACIÓN POR DEFECTO: Requiere --live explícito para enviar órdenes al broker.
3. DETECCIÓN CAUSAL DE CIERRE M15: Solo evalúa al cierre de barra M15 (start_pos=1, nunca barra 0).
4. ALINEACIÓN CAUSAL H1: Solo utiliza barras H1 completamente cerradas para el filtro macro.
5. INTEGRACIÓN RISKPAUSE: Enfriamiento post-pérdida, parada tras 3 pérdidas o -1.5% diario sin auto-rearme.
6. DIMENSIONAMIENTO EXACTO: Uso de contract_specs.py y cross-check con mt5.order_calc_profit().
7. BREAKEVEN CAUSAL: Eleva SL a +0.05*ATR cuando la ganancia ejecutable (Bid/Ask) supera +0.40*ATR.
8. FILTROS DE SESIÓN Y LIQUIDEZ: Horarios institucionales y Spread/ATR <= 8% con detector de picos.
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import numpy as np
import pandas as pd

def get_mt5_module():
    """Importación perezosa (lazy) de MetaTrader5 para no contaminar entornos de investigación offline."""
    try:
        import MetaTrader5 as mt5
        return mt5
    except ImportError:
        return None

from trading_v2.backtesting.contract_specs import (
    ADMIRALS_SPECS,
    ContractSpec,
    LotCalculationResult,
    calculate_lot_size,
    get_contract_spec,
)
from trading_v2.research.regime_lab_v3 import (
    StrategySpec,
    add_indicators as add_daily_indicators,
    canonical_strategies,
    entry_exit_signals,
)
from trading_v2.research.risk_pause import RiskPause
from trading_v2.strategies.candidates import STRATEGIES, generate_signals
from trading_v2.strategies.precision_microstructure import (
    PRECISION_STRATEGIES,
    enrich_microstructure_features,
    generate_precision_signals,
)
from trading_v2.strategies.micro_scalping import (
    SniperScalpConfig,
    generate_sniper_signals,
)
from trading_v2.strategies.trend_following import add_indicators

V3_DAILY_STRATEGIES = (
    "idx_rsi2_dip_regime",
    "idx_rsi2_dip",
    "idx_ibs_dip",
    "turn_of_month",
    "tsmom",
    "idx_dax_bollinger_dip",
    "idx_ibex_bollinger_dip",
    "fx_eurusd_ker_exhaustion",
)

# Ventanas de liquidez institucional en UTC (lunes a viernes)
# Formato: (hora_inicio, minuto_inicio, hora_fin, minuto_fin)
SESSION_WINDOWS_UTC: dict[str, tuple[int, int, int, int]] = {
    "GERMANY40": (7, 0, 15, 30),
    "DE40": (7, 0, 15, 30),
    "[SP500]": (13, 30, 19, 30),
    "US500": (13, 30, 19, 30),
    "US100": (13, 30, 19, 30),
    "USTEC": (13, 30, 19, 30),
    "[DJI30]": (13, 30, 19, 30),
    "US30": (13, 30, 19, 30),
    "GOLD": (7, 0, 18, 0),
    "XAUUSD": (7, 0, 18, 0),
    "EURUSD": (7, 0, 18, 0),
    "[IBEX35]": (7, 0, 15, 30),
    "IBEX35": (7, 0, 15, 30),
    "SPAIN35": (7, 0, 15, 30),
}


def normalize_symbol_key(symbol: str) -> str:
    """Normaliza el símbolo eliminando corchetes y espacios para mapeo de sesión."""
    return symbol.replace("[", "").replace("]", "").strip().upper()


def is_session_active(symbol: str, dt_utc: datetime) -> tuple[bool, str]:
    """Verifica si el instante actual está dentro de la ventana de liquidez institucional."""
    if dt_utc.tzinfo is None:
        raise ValueError("Se requiere datetime aware en UTC")

    # Fin de semana: mercados cerrados
    if dt_utc.weekday() in (5, 6):  # 5=Sábado, 6=Domingo
        return False, "MERCADO_CERRADO_FIN_DE_SEMANA"

    sym_clean = normalize_symbol_key(symbol)
    matched_window = None
    for k, win in SESSION_WINDOWS_UTC.items():
        if normalize_symbol_key(k) == sym_clean:
            matched_window = win
            break

    if matched_window is None:
        # Si no tiene ventana específica, permitimos operar 24h en días laborables
        return True, "SESION_ESTANDAR_ACTIVA"

    h_start, m_start, h_end, m_end = matched_window
    start_minutes = h_start * 60 + m_start
    end_minutes = h_end * 60 + m_end
    current_minutes = dt_utc.hour * 60 + dt_utc.minute

    if start_minutes <= current_minutes < end_minutes:
        return True, "SESION_INSTITUCIONAL_ACTIVA"
    return False, f"FUERA_DE_SESION ({dt_utc.strftime('%H:%M')} UTC fuera de {h_start:02d}:{m_start:02d}-{h_end:02d}:{m_end:02d} UTC)"


def check_spread_and_liquidity(
    symbol: str,
    spread_pts: float,
    atr: float,
    point: float,
    recent_spreads: list[float] | None = None,
    max_spread_atr_ratio: float = 0.08,
    max_spread_median_ratio: float = 2.0,
) -> tuple[bool, str]:
    """Filtra entradas si el spread es excesivo relativo al ATR o respecto a su mediana reciente."""
    if atr <= 0 or point <= 0 or spread_pts < 0:
        return False, "PARAMETROS_INVALIDOS_SPREAD_ATR"

    spread_price = spread_pts * point
    rel_spread = spread_price / atr

    if rel_spread > max_spread_atr_ratio:
        return False, f"SPREAD_RELATIVO_EXCESIVO ({rel_spread:.1%} > {max_spread_atr_ratio:.1%} de ATR)"

    if recent_spreads and len(recent_spreads) >= 10:
        recent_arr = np.array(recent_spreads[-40:], dtype=float)
        med_spread = float(np.median(recent_arr))
        if med_spread > 0 and spread_pts > max_spread_median_ratio * med_spread:
            return False, f"PICO_DE_SPREAD_DETECTADO ({spread_pts:.1f} pts > {max_spread_median_ratio:.1f}x mediana {med_spread:.1f} pts)"

    return True, "SPREAD_ACEPTABLE"


def assert_demo_account(account_info: Any) -> None:
    """Valida terminantemente que la cuenta conectada sea de tipo DEMO.
    
    En MetaTrader 5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_CONTEST = 1
    ACCOUNT_TRADE_MODE_REAL = 2
    """
    if account_info is None:
        raise RuntimeError("No se pudo obtener información de la cuenta en MT5 (account_info es None).")

    trade_mode = getattr(account_info, "trade_mode", None)
    if trade_mode != 0:
        login = getattr(account_info, "login", "desconocido")
        server = getattr(account_info, "server", "desconocido")
        raise RuntimeError(
            f"BLOQUEO DE SEGURIDAD CRÍTICO: La cuenta {login} en el servidor '{server}' "
            f"tiene trade_mode={trade_mode} (no es DEMO). Solo se permite operar en modo DEMO (trade_mode=0)."
        )


class MT5Adapter:
    """Adaptador de operaciones MT5 con soporte para mocking en pruebas unitarias."""

    def __init__(self, backend=None):
        if backend is None:
            backend = get_mt5_module()
            if backend is None:
                raise ImportError("MetaTrader5 no está instalado en este entorno.")
        self.backend = backend

    def initialize(self) -> bool:
        return bool(self.backend.initialize())

    def shutdown(self) -> None:
        self.backend.shutdown()

    def account_info(self) -> Any:
        return self.backend.account_info()

    def copy_rates_from_pos(self, symbol: str, timeframe: int, start_pos: int, count: int) -> np.ndarray | None:
        return self.backend.copy_rates_from_pos(symbol, timeframe, start_pos, count)

    def symbol_info_tick(self, symbol: str) -> Any:
        return self.backend.symbol_info_tick(symbol)

    def symbol_info(self, symbol: str) -> Any:
        return self.backend.symbol_info(symbol)

    def order_calc_profit(self, action: int, symbol: str, volume: float, price_open: float, price_close: float) -> float | None:
        return self.backend.order_calc_profit(action, symbol, volume, price_open, price_close)

    def order_calc_margin(self, action: int, symbol: str, volume: float, price: float) -> float | None:
        return self.backend.order_calc_margin(action, symbol, volume, price)

    def positions_get(self, symbol: str | None = None) -> tuple | None:
        if symbol is not None:
            return self.backend.positions_get(symbol=symbol)
        return self.backend.positions_get()

    def history_deals_get(self, date_from: Any, date_to: Any) -> tuple | None:
        return self.backend.history_deals_get(date_from, date_to)

    def order_send(self, request: dict) -> Any:
        return self.backend.order_send(request)

    @property
    def TIMEFRAME_M5(self) -> int:
        return getattr(self.backend, "TIMEFRAME_M5", 5)

    @property
    def TIMEFRAME_M15(self) -> int:
        return getattr(self.backend, "TIMEFRAME_M15", 15)

    @property
    def TIMEFRAME_H1(self) -> int:
        return getattr(self.backend, "TIMEFRAME_H1", 16385)

    @property
    def TIMEFRAME_H4(self) -> int:
        return getattr(self.backend, "TIMEFRAME_H4", 16388)

    @property
    def TIMEFRAME_D1(self) -> int:
        return getattr(self.backend, "TIMEFRAME_D1", 16408)

    @property
    def ORDER_TYPE_BUY(self) -> int:
        return getattr(self.backend, "ORDER_TYPE_BUY", 0)

    @property
    def ORDER_TYPE_SELL(self) -> int:
        return getattr(self.backend, "ORDER_TYPE_SELL", 1)

    @property
    def TRADE_ACTION_DEAL(self) -> int:
        return getattr(self.backend, "TRADE_ACTION_DEAL", 1)

    @property
    def TRADE_ACTION_SLTP(self) -> int:
        return getattr(self.backend, "TRADE_ACTION_SLTP", 6)

    @property
    def ORDER_FILLING_IOC(self) -> int:
        return getattr(self.backend, "ORDER_FILLING_IOC", 2)

    @property
    def ORDER_FILLING_FOK(self) -> int:
        return getattr(self.backend, "ORDER_FILLING_FOK", 1)

    @property
    def ORDER_FILLING_RETURN(self) -> int:
        return getattr(self.backend, "ORDER_FILLING_RETURN", 0)

    @property
    def ORDER_TIME_GTC(self) -> int:
        return getattr(self.backend, "ORDER_TIME_GTC", 0)

    @property
    def TRADE_RETCODE_DONE(self) -> int:
        return getattr(self.backend, "TRADE_RETCODE_DONE", 10009)


@dataclass
class DemoTraderConfig:
    symbols: list[str] = field(
        default_factory=lambda: ["GERMANY40", "[SP500]", "[DJI30]", "GOLD", "EURUSD"]
    )
    risk_fraction: float = 0.0025  # 0.25% por operación
    sl_atr: float = 1.20
    tp_atr: float = 0.55
    be_trigger_atr: float = 0.40  # Nivel para activar Breakeven
    be_lock_atr: float = 0.05    # Nivel donde se coloca el SL (+0.05*ATR cubre spread)
    max_spread_atr_ratio: float = 0.08  # Máximo spread <= 8% de ATR
    max_spread_median_ratio: float = 2.0  # Bloqueo si spread > 2x mediana
    strategy: str = "ema_rsi_baseline"
    broker: str = "admirals"  # "admirals" o "icmarkets"
    poll_seconds: float = 15.0
    max_open_positions: int = 2
    magic_number: int = 20261018
    dry_run: bool = True
    cooldown_minutes: int = 60
    max_consecutive_losses: int = 2
    max_daily_loss_fraction: float = 0.015  # -1.5% de pérdida diaria máxima
    timeframe: str = "M15"  # "M5", "M15" o "D1"


class DemoPaperTrader:
    """Ejecutor cuantitativo M15 con salvaguardas DEMO, causalidad y RiskPause."""

    def __init__(
        self,
        config: DemoTraderConfig | None = None,
        adapter: Any = None,
        logger: Callable[[str], None] | None = None,
    ):
        self.cfg = config or DemoTraderConfig()
        self.adapter = adapter if adapter is not None else MT5Adapter()
        self.log = logger or (lambda msg: print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}] {msg}"))

        self.risk_pause: RiskPause | None = None
        self.last_m15_bar_time: dict[str, int] = {}
        self.recent_spreads: dict[str, list[float]] = {s: [] for s in self.cfg.symbols}
        self.latest_atr: dict[str, float] = {}
        self.processed_deal_tickets: set[int] = set()

    def initialize(self) -> bool:
        """Inicializa conexión MT5, verifica cuenta DEMO y arranca RiskPause."""
        self.log("Iniciando conexión con MetaTrader 5...")
        if not self.adapter.initialize():
            self.log("ERROR: Fallo al conectar con MetaTrader 5.")
            return False

        acc = self.adapter.account_info()
        assert_demo_account(acc)

        mode_desc = "SIMULACIÓN DRY-RUN (Sin órdenes reales)" if self.cfg.dry_run else "LIVE DEMO (Enviando órdenes reales al broker)"
        self.log(
            f"Conectado a cuenta DEMO #{acc.login} ({acc.server}) | "
            f"Balance: {acc.balance:.2f} {acc.currency} | Equity: {acc.equity:.2f} {acc.currency} | "
            f"Modo: {mode_desc}"
        )

        # Inicializar RiskPause con el capital de referencia actual
        self.risk_pause = RiskPause(
            cooldown_minutes=self.cfg.cooldown_minutes,
            max_consecutive_losses=self.cfg.max_consecutive_losses,
            max_daily_loss_fraction=self.cfg.max_daily_loss_fraction,
            reference_equity=acc.equity,
        )

        # Cargar historial de deals de hoy para reconstruir estado si hubo reinicio
        self._sync_deals_history(datetime.now(timezone.utc), initial_sync=True)
        return True

    def _sync_deals_history(self, now_utc: datetime, initial_sync: bool = False) -> list[dict]:
        """Sincroniza deals cerrados desde MT5 e informa a RiskPause."""
        if self.risk_pause is None:
            return []

        start_of_day = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        deals = self.adapter.history_deals_get(start_of_day, now_utc)
        if not deals:
            return []

        registered = []
        for d in deals:
            ticket = getattr(d, "ticket", 0)
            if ticket in self.processed_deal_tickets:
                continue

            entry_type = getattr(d, "entry", None)
            # En MT5: 1 = DEAL_ENTRY_OUT, 2 = DEAL_ENTRY_INOUT, 3 = DEAL_ENTRY_OUT_BY
            if entry_type in (1, 2, 3):
                profit = float(getattr(d, "profit", 0.0))
                swap = float(getattr(d, "swap", 0.0))
                commission = float(getattr(d, "commission", 0.0))
                net_pnl = profit + swap + commission

                deal_time_ts = getattr(d, "time", int(now_utc.timestamp()))
                deal_dt = datetime.fromtimestamp(deal_time_ts, tz=timezone.utc)

                try:
                    self.risk_pause.register_closed_trade(net_pnl, deal_dt)
                    registered.append({
                        "ticket": ticket,
                        "pnl": net_pnl,
                        "time": deal_dt.isoformat(),
                        "symbol": getattr(d, "symbol", "UNKNOWN"),
                    })
                    if not initial_sync:
                        self.log(
                            f"[RiskPause] Operación cerrada #{ticket} con PnL={net_pnl:+.2f} EUR. "
                            f"Pérdidas consecutivas: {self.risk_pause.consecutive_losses}, "
                            f"PnL del día: {self.risk_pause.daily_pnl:+.2f} EUR"
                        )
                except RuntimeError as err:
                    self.log(f"[RiskPause ALERTA CRÍTICA]: {err}")

            self.processed_deal_tickets.add(ticket)

        return registered

    def get_eurusd_rate(self) -> float:
        """Obtiene la tasa actual de EURUSD para conversión de beneficios USD -> EUR."""
        tick = self.adapter.symbol_info_tick("EURUSD")
        if tick and getattr(tick, "bid", 0.0) > 0:
            return float(tick.bid)
        return 1.12  # Fallback seguro para auditoría offline

    def check_and_apply_causal_breakeven(self) -> list[dict]:
        """Aplica Breakeven Causal a posiciones abiertas:
        
        Si ganancia ejecutable (Bid en LONG, Ask en SHORT) >= +0.40 * ATR,
        el Stop Loss se eleva a Entrada +/- 0.05 * ATR (cubriendo spread).
        """
        positions = self.adapter.positions_get()
        if not positions:
            return []

        actions = []
        for pos in positions:
            magic = getattr(pos, "magic", 0)
            if magic != self.cfg.magic_number:
                continue

            symbol = getattr(pos, "symbol", "")
            try:
                spec = get_contract_spec(symbol, broker=self.cfg.broker)
            except KeyError:
                continue

            atr = self.latest_atr.get(symbol, 0.0)
            if atr <= 0:
                continue

            pos_type = getattr(pos, "type", -1)
            price_open = float(getattr(pos, "price_open", 0.0))
            current_sl = float(getattr(pos, "sl", 0.0))
            ticket = getattr(pos, "ticket", 0)

            tick = self.adapter.symbol_info_tick(symbol)
            if not tick:
                continue

            # Para BUY (0), precio ejecutable de salida es BID
            if pos_type == self.adapter.ORDER_TYPE_BUY:
                current_bid = float(getattr(tick, "bid", 0.0))
                profit_distance = current_bid - price_open
                be_trigger_dist = self.cfg.be_trigger_atr * atr

                if profit_distance >= be_trigger_dist:
                    target_sl = round(price_open + self.cfg.be_lock_atr * atr, spec.digits)
                    # Solo mover si el SL actual es inferior al nuevo target
                    if current_sl < target_sl:
                        act = self._execute_modify_sl(pos, target_sl, "LONG_BREAKEVEN")
                        actions.append(act)

            # Para SELL (1), precio ejecutable de salida es ASK
            elif pos_type == self.adapter.ORDER_TYPE_SELL:
                current_ask = float(getattr(tick, "ask", 0.0))
                profit_distance = price_open - current_ask
                be_trigger_dist = self.cfg.be_trigger_atr * atr

                if profit_distance >= be_trigger_dist:
                    target_sl = round(price_open - self.cfg.be_lock_atr * atr, spec.digits)
                    # Solo mover si el SL actual es 0 o superior al nuevo target
                    if current_sl == 0.0 or current_sl > target_sl:
                        act = self._execute_modify_sl(pos, target_sl, "SHORT_BREAKEVEN")
                        actions.append(act)

        return actions

    def _execute_modify_sl(self, pos: Any, new_sl: float, reason: str) -> dict:
        ticket = getattr(pos, "ticket", 0)
        symbol = getattr(pos, "symbol", "")
        old_sl = getattr(pos, "sl", 0.0)
        tp = getattr(pos, "tp", 0.0)

        self.log(
            f"[BREAKEVEN] Ajustando Stop Loss en {symbol} (Ticket #{ticket}): "
            f"{old_sl} -> {new_sl} ({reason})"
        )

        if self.cfg.dry_run:
            return {"status": "DRY_RUN_MODIFIED", "ticket": ticket, "new_sl": new_sl, "reason": reason}

        req = {
            "action": self.adapter.TRADE_ACTION_SLTP,
            "position": ticket,
            "symbol": symbol,
            "sl": new_sl,
            "tp": tp,
        }
        res = self.adapter.order_send(req)
        retcode = getattr(res, "retcode", None)
        if retcode == self.adapter.TRADE_RETCODE_DONE:
            self.log(f"[BREAKEVEN OK] SL actualizado con éxito en broker para ticket #{ticket}.")
            return {"status": "SUCCESS", "ticket": ticket, "new_sl": new_sl}
        else:
            err = getattr(res, "comment", "Error desconocido")
            self.log(f"[BREAKEVEN ERROR] Fallo al actualizar SL en ticket #{ticket}: {err} (retcode={retcode})")
            return {"status": "FAILED", "ticket": ticket, "error": err}

    def _build_dataframe_from_rates(self, rates: np.ndarray) -> pd.DataFrame:
        """Convierte array de rates de MT5 a DataFrame indexado en UTC."""
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.set_index("time", inplace=True)
        df.rename(
            columns={
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "spread": "Spread",
                "tick_volume": "TickVolume",
            },
            inplace=True,
        )
        return df

    def _compute_causal_h1_direction(self, m15_close_dt: datetime, h1_df: pd.DataFrame) -> int:
        """Determina la tendencia H1 únicamente a partir de barras H1 cerradas al momento del cierre M15."""
        h1 = h1_df.copy()
        h1["ema20"] = h1["Close"].ewm(span=20, adjust=False).mean()
        h1["ema50"] = h1["Close"].ewm(span=50, adjust=False).mean()
        h1["close_time"] = h1.index + pd.to_timedelta(1, unit="h")

        # Filtrar barras H1 cerradas estrictamente antes o en el momento del cierre de la vela M15
        valid_h1 = h1[h1["close_time"] <= m15_close_dt]
        if valid_h1.empty:
            return 0

        latest = valid_h1.iloc[-1]
        if latest["ema20"] > latest["ema50"]:
            return 1
        elif latest["ema20"] < latest["ema50"]:
            return -1
        return 0

    def evaluate_symbol(self, symbol: str, now_utc: datetime) -> dict:
        """Evalúa un símbolo al cierre de su vela (M15 o D1) cumpliendo causalidad y filtros de riesgo."""
        if self.cfg.timeframe == "D1":
            return self.evaluate_daily_symbol(symbol, now_utc)

        spec = get_contract_spec(symbol, broker=self.cfg.broker)

        # 1. Copiar últimas 100 barras intradía CERRADAS (M5 o M15)
        tf_code = self.adapter.TIMEFRAME_M5 if self.cfg.timeframe == "M5" else self.adapter.TIMEFRAME_M15
        m15_rates = self.adapter.copy_rates_from_pos(symbol, tf_code, 1, 100)
        if m15_rates is None or len(m15_rates) < 65:
            return {"status": "INSUFFICIENT_M15_DATA", "symbol": symbol}

        last_bar_time = int(m15_rates["time"][-1])
        if self.last_m15_bar_time.get(symbol) == last_bar_time:
            # Esta barra cerrada ya fue procesada, esperar la siguiente vela
            return {"status": "BAR_ALREADY_PROCESSED", "symbol": symbol}

        # 2. Copiar últimas 60 barras H1 CERRADAS para el filtro macro
        h1_rates = self.adapter.copy_rates_from_pos(symbol, self.adapter.TIMEFRAME_H1, 1, 60)
        if h1_rates is None or len(h1_rates) < 55:
            return {"status": "INSUFFICIENT_H1_DATA", "symbol": symbol}

        m15_df = self._build_dataframe_from_rates(m15_rates)
        h1_df = self._build_dataframe_from_rates(h1_rates)

        # Guardar historial de spread para detector de anomalías
        last_spread_pts = float(m15_df["Spread"].iloc[-1])
        self.recent_spreads[symbol].append(last_spread_pts)
        if len(self.recent_spreads[symbol]) > 100:
            self.recent_spreads[symbol].pop(0)

        # 3. Cálculo de indicadores causales en M15
        m15_df = add_indicators(m15_df)
        atr = float(m15_df["atr"].iloc[-1])
        self.latest_atr[symbol] = atr

        # Fecha de cierre de la barra M15 evaluada
        m15_close_dt = m15_df.index[-1] + pd.to_timedelta(15, unit="m")

        # 4. Alinear tendencia H1 de forma estrictamente causal
        h1_dir = self._compute_causal_h1_direction(m15_close_dt, h1_df)
        m15_df["h1_direction"] = h1_dir

        # 5. Generar señal según estrategia configurada
        if self.cfg.strategy == "ema_rsi_baseline":
            # Baseline con filtro H1 cerrado
            c = m15_df["Close"].iloc[-1]
            e20 = m15_df["ema20"].iloc[-1]
            e50 = m15_df["ema50"].iloc[-1]
            rsi = m15_df["rsi"].iloc[-1]
            atr_r = m15_df["atr_ratio"].iloc[-1]
            sig = 0
            if (e20 > e50) and (c > e50) and (42 <= rsi <= 68) and (atr_r >= 0.82) and (h1_dir == 1):
                sig = 1
            elif (e20 < e50) and (c < e50) and (32 <= rsi <= 58) and (atr_r >= 0.82) and (h1_dir == -1):
                sig = -1
        elif self.cfg.strategy == "institutional_sniper_scalp":
            cfg_sniper = SniperScalpConfig(
                symbol=symbol,
                target_units=2.5 if symbol == "EURUSD" else (15.0 if "GERMANY" in symbol else 4.5),
                stop_units=5.0 if symbol == "EURUSD" else (25.0 if "GERMANY" in symbol else 7.5),
                session_start_h=7,
                session_end_h=17,
                max_holding_bars=4,
                min_sweep_units=1.5 if symbol == "EURUSD" else (8.0 if "GERMANY" in symbol else 2.5),
                min_rejection_wick=0.35,
                use_h1_filter=False,
            )
            signals_df = generate_sniper_signals(m15_df, cfg_sniper)
            sig = int(signals_df["signal"].iloc[-1])
        elif self.cfg.strategy in PRECISION_STRATEGIES:
            enriched_df = enrich_microstructure_features(m15_df, h1_df, spec.point)
            signals_df = generate_precision_signals(enriched_df, self.cfg.strategy, spec.point)
            sig = int(signals_df["signal"].iloc[-1])
        else:
            m15_df["signal"] = 0
            signals_df = generate_signals(m15_df, self.cfg.strategy, spec.point)
            sig = int(signals_df["signal"].iloc[-1])

        # Marcar barra como procesada
        self.last_m15_bar_time[symbol] = last_bar_time

        if sig == 0:
            return {"status": "NO_SIGNAL", "symbol": symbol, "h1_dir": h1_dir, "atr": atr}

        # 6. Filtro de Sesión y Liquidez Institucional
        session_ok, session_msg = is_session_active(symbol, now_utc)
        if not session_ok:
            self.log(f"[{symbol}] Señal descartada: {session_msg}")
            return {"status": "REJECTED_SESSION", "symbol": symbol, "reason": session_msg}

        spread_ok, spread_msg = check_spread_and_liquidity(
            symbol=symbol,
            spread_pts=last_spread_pts,
            atr=atr,
            point=spec.point,
            recent_spreads=self.recent_spreads[symbol],
            max_spread_atr_ratio=self.cfg.max_spread_atr_ratio,
            max_spread_median_ratio=self.cfg.max_spread_median_ratio,
        )
        if not spread_ok:
            self.log(f"[{symbol}] Señal descartada por spread: {spread_msg}")
            return {"status": "REJECTED_SPREAD", "symbol": symbol, "reason": spread_msg}

        # 7. Filtro de RiskPause
        if self.risk_pause:
            can_trade, pause_reason = self.risk_pause.can_open_new_trade(now_utc)
            if not can_trade:
                self.log(f"[{symbol}] Bloqueo de riesgo activo: {pause_reason}")
                return {"status": "REJECTED_RISK_PAUSE", "symbol": symbol, "reason": pause_reason}

        # 8. Comprobar límite de posiciones abiertas simultáneas
        current_positions = self.adapter.positions_get()
        our_positions = [p for p in (current_positions or []) if getattr(p, "magic", 0) == self.cfg.magic_number]
        if len(our_positions) >= self.cfg.max_open_positions:
            self.log(f"[{symbol}] Límite de posiciones abiertas alcanzado ({len(our_positions)}/{self.cfg.max_open_positions})")
            return {"status": "REJECTED_MAX_POSITIONS", "symbol": symbol}

        # Ya hay posición abierta en este mismo símbolo?
        if any(getattr(p, "symbol", "") == symbol for p in our_positions):
            return {"status": "REJECTED_EXISTING_SYMBOL_POSITION", "symbol": symbol}

        # 9. Obtener tick actual para precio de entrada exacto
        tick = self.adapter.symbol_info_tick(symbol)
        if not tick:
            return {"status": "FAILED_NO_TICK", "symbol": symbol}

        entry_price = float(tick.ask) if sig == 1 else float(tick.bid)
        stop_dist_price = self.cfg.sl_atr * atr
        sl_price = round(entry_price - sig * stop_dist_price, spec.digits)
        tp_price = round(entry_price + sig * self.cfg.tp_atr * atr, spec.digits)

        # 10. Dimensionamiento de lotes cuantitativo
        acc = self.adapter.account_info()
        assert_demo_account(acc)
        eurusd_rate = self.get_eurusd_rate()

        lot_res = calculate_lot_size(
            spec=spec,
            account_equity=acc.equity,
            risk_fraction=self.cfg.risk_fraction,
            stop_distance_price=stop_dist_price,
            entry_price=entry_price,
            eurusd_rate=eurusd_rate,
            leverage=getattr(acc, "leverage", 100.0),
            account_currency=acc.currency,
        )

        if lot_res.status != "OK":
            self.log(f"[{symbol}] Rechazo de lotaje: {lot_res.reason} (lots={lot_res.lots})")
            return {"status": lot_res.status, "symbol": symbol, "reason": lot_res.reason}

        # 11. Cross-check con mt5.order_calc_profit()
        order_type = self.adapter.ORDER_TYPE_BUY if sig == 1 else self.adapter.ORDER_TYPE_SELL
        broker_profit = self.adapter.order_calc_profit(order_type, symbol, lot_res.lots, entry_price, sl_price)

        if broker_profit is not None:
            broker_loss = abs(float(broker_profit))
            max_tolerated_risk = lot_res.risk_budget_account_ccy * 1.05
            if broker_loss > max_tolerated_risk:
                msg = f"Pérdida calculada por broker ({broker_loss:.2f} {acc.currency}) excede presupuesto ({lot_res.risk_budget_account_ccy:.2f} {acc.currency})"
                self.log(f"[{symbol}] BLOQUEO: {msg}")
                return {"status": "REJECTED_BROKER_PROFIT_EXCEEDED", "symbol": symbol, "reason": msg}

        # 12. Cross-check de margen requerido
        req_margin = self.adapter.order_calc_margin(order_type, symbol, lot_res.lots, entry_price)
        if req_margin is not None and req_margin > acc.margin_free:
            msg = f"Margen requerido ({req_margin:.2f} {acc.currency}) supera margen libre ({acc.margin_free:.2f} {acc.currency})"
            self.log(f"[{symbol}] BLOQUEO: {msg}")
            return {"status": "REJECTED_INSUFFICIENT_MARGIN", "symbol": symbol, "reason": msg}

        # 13. Ejecución de la orden (Simulación o Live en DEMO)
        direction_str = "LONG" if sig == 1 else "SHORT"
        self.log(
            f"🎯 [DISPARO M15 {direction_str} en {symbol}] Lotes: {lot_res.lots} | "
            f"Entrada: {entry_price:.{spec.digits}f} | SL: {sl_price:.{spec.digits}f} | TP: {tp_price:.{spec.digits}f} | "
            f"Riesgo: {lot_res.actual_risk_account_ccy:.2f} {acc.currency} (Presupuesto: {lot_res.risk_budget_account_ccy:.2f} {acc.currency})"
        )

        if self.cfg.dry_run:
            self.log(f"[DRY-RUN] Orden simulada registrada con éxito para {symbol}.")
            return {
                "status": "SIMULATED_ORDER",
                "symbol": symbol,
                "direction": direction_str,
                "lots": lot_res.lots,
                "entry": entry_price,
                "sl": sl_price,
                "tp": tp_price,
            }

        # Ejecución real en cuenta DEMO
        assert_demo_account(acc)
        sym_info = self.adapter.symbol_info(symbol)
        filling = self.adapter.ORDER_FILLING_IOC
        if sym_info and hasattr(sym_info, "filling_mode"):
            if sym_info.filling_mode & 2:
                filling = self.adapter.ORDER_FILLING_IOC
            elif sym_info.filling_mode & 1:
                filling = self.adapter.ORDER_FILLING_FOK
            else:
                filling = self.adapter.ORDER_FILLING_RETURN

        trade_request = {
            "action": self.adapter.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot_res.lots,
            "type": order_type,
            "price": entry_price,
            "sl": sl_price,
            "tp": tp_price,
            "deviation": 20,
            "magic": self.cfg.magic_number,
            "comment": f"V2_M15_{direction_str}",
            "type_time": self.adapter.ORDER_TIME_GTC,
            "type_filling": filling,
        }

        order_res = self.adapter.order_send(trade_request)
        retcode = getattr(order_res, "retcode", None)
        if retcode == self.adapter.TRADE_RETCODE_DONE:
            order_ticket = getattr(order_res, "order", getattr(order_res, "deal", 0))
            self.log(f"[ORDEN EJECUTADA EN DEMO] {symbol} Ticket #{order_ticket} a {entry_price}")
            return {
                "status": "LIVE_ORDER_EXECUTED",
                "symbol": symbol,
                "ticket": order_ticket,
                "direction": direction_str,
                "lots": lot_res.lots,
            }
        else:
            err_comment = getattr(order_res, "comment", "Desconocido")
            self.log(f"[ERROR MT5] Fallo al enviar orden en {symbol}: {err_comment} (retcode={retcode})")
            return {
                "status": "ORDER_SEND_ERROR",
                "symbol": symbol,
                "retcode": retcode,
                "comment": err_comment,
            }

    def _close_position(self, pos: Any, reason: str) -> dict:
        ticket = getattr(pos, "ticket", 0)
        symbol = getattr(pos, "symbol", "")
        volume = float(getattr(pos, "volume", 0.0))
        pos_type = getattr(pos, "type", 0)

        self.log(f"[CIERRE POSICIÓN] Ticket #{ticket} en {symbol} ({reason})")
        if self.cfg.dry_run:
            return {"status": "DRY_RUN_CLOSED", "ticket": ticket, "symbol": symbol, "reason": reason}

        tick = self.adapter.symbol_info_tick(symbol)
        close_price = float(tick.bid) if pos_type == self.adapter.ORDER_TYPE_BUY else float(tick.ask)
        close_action = (
            self.adapter.ORDER_TYPE_SELL if pos_type == self.adapter.ORDER_TYPE_BUY else self.adapter.ORDER_TYPE_BUY
        )

        req = {
            "action": self.adapter.TRADE_ACTION_DEAL,
            "position": ticket,
            "symbol": symbol,
            "volume": volume,
            "type": close_action,
            "price": close_price,
            "deviation": 20,
            "magic": self.cfg.magic_number,
            "comment": f"Close {reason}",
            "type_time": self.adapter.ORDER_TIME_GTC,
            "type_filling": self.adapter.ORDER_FILLING_IOC,
        }
        res = self.adapter.order_send(req)
        retcode = getattr(res, "retcode", None)
        if retcode == self.adapter.TRADE_RETCODE_DONE:
            self.log(f"[CIERRE OK] Posición #{ticket} cerrada en broker.")
            return {"status": "SUCCESS_CLOSED", "ticket": ticket, "symbol": symbol}
        err = getattr(res, "comment", "Error al cerrar")
        return {"status": "FAILED_CLOSE", "ticket": ticket, "error": err}

    def evaluate_daily_symbol(self, symbol: str, now_utc: datetime) -> dict:
        """Evalúa un símbolo en marco temporal Diario (D1) según las estrategias robustas V3."""
        spec = get_contract_spec(symbol, broker=self.cfg.broker)

        # 1. Copiar 250 barras D1 cerradas (start_pos=1 para asegurar que la vela de hoy no ha cerrado)
        d1_rates = self.adapter.copy_rates_from_pos(symbol, self.adapter.TIMEFRAME_D1, 1, 260)
        if d1_rates is None or len(d1_rates) < 220:
            return {"status": "INSUFFICIENT_D1_DATA", "symbol": symbol}

        last_bar_time = int(d1_rates["time"][-1])
        if self.last_m15_bar_time.get(symbol) == last_bar_time:
            return {"status": "BAR_ALREADY_PROCESSED", "symbol": symbol}

        d1_df = self._build_dataframe_from_rates(d1_rates)
        d1_df = add_daily_indicators(d1_df)

        # Historial de spreads
        last_spread_pts = float(d1_df["Spread"].iloc[-1])
        self.recent_spreads[symbol].append(last_spread_pts)
        if len(self.recent_spreads[symbol]) > 100:
            self.recent_spreads[symbol].pop(0)

        atr = float(d1_df["atr20"].iloc[-1])
        self.latest_atr[symbol] = atr

        # Comprobar si ya tenemos posición abierta en este símbolo con nuestro magic_number
        current_positions = self.adapter.positions_get()
        our_positions = [p for p in (current_positions or []) if getattr(p, "magic", 0) == self.cfg.magic_number]
        sym_positions = [p for p in our_positions if getattr(p, "symbol", "") == symbol]

        # Estrategia V3 canónica
        s_spec = None
        for cs in canonical_strategies():
            if cs.name == self.cfg.strategy:
                s_spec = cs
                break
        if s_spec is None:
            s_spec = StrategySpec(
                self.cfg.strategy,
                (symbol,),
                "long",
                {"sma": 200, "rsi_th": 10},
                stop_atr=self.cfg.sl_atr,
                max_bars=10,
                regime_cap=1.8 if "regime" in self.cfg.strategy else None,
            )

        entry_sig_series, exit_rule_series = entry_exit_signals(d1_df, s_spec)
        sig = int(entry_sig_series.iloc[-1])
        exit_rule_active = bool(exit_rule_series.iloc[-1])

        # 2. Si ya hay posición abierta, verificar regla de salida al cierre (ej. Close > SMA5)
        if sym_positions:
            pos = sym_positions[0]
            should_exit = exit_rule_active
            if self.cfg.strategy.startswith("fx_"):
                is_long = getattr(pos, "type", 0) == 0
                c_last = float(d1_df["Close"].iloc[-1])
                sma5_last = float(d1_df["sma5"].iloc[-1])
                should_exit = (c_last > sma5_last) if is_long else (c_last < sma5_last)
            if should_exit:
                self.log(
                    f"[{symbol}] Regla de salida D1 activada "
                    f"(Close={d1_df['Close'].iloc[-1]:.2f} > SMA5={d1_df['sma5'].iloc[-1]:.2f}). "
                    f"Cerrando posición ticket #{pos.ticket}..."
                )
                return self._close_position(pos, reason="DAILY_RULE_EXIT_SMA5")
            return {"status": "POSITION_HELD", "symbol": symbol, "ticket": pos.ticket, "exit_rule": False}

        # Marcar barra como procesada si no hay señal o se rechaza
        self.last_m15_bar_time[symbol] = last_bar_time

        if sig == 0:
            self.log(
                f"[{symbol}] Evaluación D1 ({self.cfg.strategy}): Sin señal "
                f"(Close={d1_df['Close'].iloc[-1]:.2f}, SMA200={d1_df['sma200'].iloc[-1]:.2f}, "
                f"RSI2={d1_df['rsi2'].iloc[-1]:.1f}, IBS={d1_df['ibs'].iloc[-1]:.2f})"
            )
            return {
                "status": "NO_SIGNAL",
                "symbol": symbol,
                "atr": atr,
                "rsi2": float(d1_df["rsi2"].iloc[-1]),
                "timeframe": "D1",
            }

        # 3. Filtros de liquidez y RiskPause
        spread_ok, spread_msg = check_spread_and_liquidity(
            symbol=symbol,
            spread_pts=last_spread_pts,
            atr=atr,
            point=spec.point,
            recent_spreads=self.recent_spreads[symbol],
            max_spread_atr_ratio=self.cfg.max_spread_atr_ratio,
            max_spread_median_ratio=self.cfg.max_spread_median_ratio,
        )
        if not spread_ok:
            return {"status": "REJECTED_SPREAD", "symbol": symbol, "reason": spread_msg}

        if self.risk_pause:
            can_trade, pause_reason = self.risk_pause.can_open_new_trade(now_utc)
            if not can_trade:
                return {"status": "REJECTED_RISK_PAUSE", "symbol": symbol, "reason": pause_reason}

        if len(our_positions) >= self.cfg.max_open_positions:
            return {"status": "REJECTED_MAX_POSITIONS", "symbol": symbol}

        # 4. Obtener tick actual y dimensionar
        tick = self.adapter.symbol_info_tick(symbol)
        if not tick:
            return {"status": "FAILED_NO_TICK", "symbol": symbol}

        entry_price = float(tick.ask) if sig == 1 else float(tick.bid)
        stop_dist_price = self.cfg.sl_atr * atr
        sl_price = round(entry_price - sig * stop_dist_price, spec.digits)
        tp_price = 0.0  # En D1 la salida es por regla SMA5 al cierre de barra

        acc = self.adapter.account_info()
        assert_demo_account(acc)
        eurusd_rate = self.get_eurusd_rate()

        lot_res = calculate_lot_size(
            spec=spec,
            account_equity=acc.equity,
            risk_fraction=self.cfg.risk_fraction,
            stop_distance_price=stop_dist_price,
            entry_price=entry_price,
            eurusd_rate=eurusd_rate,
            leverage=getattr(acc, "leverage", 100.0),
            account_currency=acc.currency,
        )
        if lot_res.status != "OK":
            return {"status": lot_res.status, "symbol": symbol, "reason": lot_res.reason}

        direction_str = "LONG" if sig == 1 else "SHORT"
        self.log(
            f"[DISPARO D1 {direction_str} en {symbol} ({self.cfg.strategy})] Lotes: {lot_res.lots} | "
            f"Entrada: {entry_price:.{spec.digits}f} | SL: {sl_price:.{spec.digits}f} | "
            f"Riesgo: {lot_res.actual_risk_account_ccy:.2f} {acc.currency}"
        )
        if self.cfg.dry_run:
            return {
                "status": "SIMULATED_ORDER",
                "symbol": symbol,
                "direction": direction_str,
                "lots": lot_res.lots,
                "entry": entry_price,
                "sl": sl_price,
                "tp": tp_price,
                "timeframe": "D1",
            }

        sym_info = self.adapter.symbol_info(symbol)
        filling = self.adapter.ORDER_FILLING_IOC
        if sym_info and hasattr(sym_info, "filling_mode"):
            if sym_info.filling_mode & 2:
                filling = self.adapter.ORDER_FILLING_IOC
            elif sym_info.filling_mode & 1:
                filling = self.adapter.ORDER_FILLING_FOK
            else:
                filling = self.adapter.ORDER_FILLING_RETURN

        trade_request = {
            "action": self.adapter.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot_res.lots,
            "type": self.adapter.ORDER_TYPE_BUY if sig == 1 else self.adapter.ORDER_TYPE_SELL,
            "price": entry_price,
            "sl": sl_price,
            "tp": tp_price,
            "deviation": 20,
            "magic": self.cfg.magic_number,
            "comment": f"V3_D1_{direction_str}",
            "type_time": self.adapter.ORDER_TIME_GTC,
            "type_filling": filling,
        }
        order_res = self.adapter.order_send(trade_request)
        retcode = getattr(order_res, "retcode", None)
        if retcode == self.adapter.TRADE_RETCODE_DONE:
            order_ticket = getattr(order_res, "order", getattr(order_res, "deal", 0))
            self.log(f"[ORDEN D1 EJECUTADA EN DEMO] {symbol} Ticket #{order_ticket} a {entry_price}")
            return {
                "status": "LIVE_ORDER_EXECUTED",
                "symbol": symbol,
                "ticket": order_ticket,
                "direction": direction_str,
                "lots": lot_res.lots,
            }
        else:
            err_comment = getattr(order_res, "comment", "Desconocido")
            self.log(f"[ERROR MT5] Fallo al enviar orden D1 en {symbol}: {err_comment} (retcode={retcode})")
            return {
                "status": "ORDER_SEND_ERROR",
                "symbol": symbol,
                "retcode": retcode,
                "comment": err_comment,
            }

    def run_cycle(self) -> dict:
        """Ejecuta un ciclo completo de escaneo: sincronización deals, breakeven y evaluación."""
        now_utc = datetime.now(timezone.utc)
        deals_closed = self._sync_deals_history(now_utc)
        be_actions = self.check_and_apply_causal_breakeven()

        evaluations = {}
        for sym in self.cfg.symbols:
            evaluations[sym] = self.evaluate_symbol(sym, now_utc)

        return {
            "timestamp": now_utc.isoformat(),
            "deals_closed": deals_closed,
            "breakeven_actions": be_actions,
            "evaluations": evaluations,
        }

    def run(self, once: bool = False) -> None:
        """Bucle principal de ejecución."""
        if not self.initialize():
            return

        self.log(f"Iniciando escaneo periódico cada {self.cfg.poll_seconds:.1f} segundos (Presiona Ctrl+C para detener)...")
        try:
            while True:
                self.run_cycle()
                if once:
                    break
                time.sleep(self.cfg.poll_seconds)
        except KeyboardInterrupt:
            self.log("Detención solicitada por el usuario.")
        finally:
            self.adapter.shutdown()
            self.log("Conexión con MetaTrader 5 cerrada de forma segura.")


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ejecutor Paper-Trading V2 para MetaTrader 5 (DEMO ONLY)."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Habilita el envío real de órdenes a la cuenta DEMO (por defecto opera en DRY-RUN).",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["GERMANY40", "[SP500]", "[DJI30]", "GOLD", "EURUSD"],
        help="Lista de símbolos a monitorizar.",
    )
    parser.add_argument(
        "--risk-fraction",
        type=float,
        default=0.0025,
        help="Fracción de riesgo por operación (default: 0.0025 = 0.25%%).",
    )
    parser.add_argument(
        "--sl-atr",
        type=float,
        default=1.20,
        help="Multiplicador de ATR para Stop Loss (default: 1.20).",
    )
    parser.add_argument(
        "--tp-atr",
        type=float,
        default=0.55,
        help="Multiplicador de ATR para Take Profit (default: 0.55).",
    )
    parser.add_argument(
        "--be-trigger-atr",
        type=float,
        default=0.40,
        help="Multiplicador de ATR de ganancia para activar Breakeven causal (default: 0.40).",
    )
    parser.add_argument(
        "--be-lock-atr",
        type=float,
        default=0.05,
        help="Multiplicador de ATR sobre entrada para fijar nuevo SL (default: 0.05).",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="M15",
        choices=["M5", "M15", "D1"],
        help="Marco temporal de ejecución (default: M15).",
    )
    parser.add_argument(
        "--strategy",
        type=str,
        default="adr_exhaustion_fade",
        choices=list(STRATEGIES) + list(PRECISION_STRATEGIES) + list(V3_DAILY_STRATEGIES) + ["institutional_sniper_scalp"],
        help="Estrategia a ejecutar.",
    )
    parser.add_argument(
        "--broker",
        type=str,
        default="admirals",
        choices=["admirals", "icmarkets"],
        help="Perfil contractual del bróker: 'admirals' o 'icmarkets' (default: admirals).",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=15.0,
        help="Intervalo de sondeo en segundos (default: 15.0).",
    )
    parser.add_argument(
        "--max-positions",
        type=int,
        default=2,
        help="Máximo de posiciones simultáneas abiertas por el bot.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        default=False,
        help="Ejecuta un único ciclo de evaluación y termina (útil para auditorías y tests).",
    )
    return parser.parse_args(args)


def main():
    args = parse_args()
    config = DemoTraderConfig(
        symbols=args.symbols,
        timeframe=args.timeframe,
        risk_fraction=args.risk_fraction,
        sl_atr=args.sl_atr,
        tp_atr=args.tp_atr,
        be_trigger_atr=args.be_trigger_atr,
        be_lock_atr=args.be_lock_atr,
        strategy=args.strategy,
        broker=args.broker,
        poll_seconds=args.poll_seconds,
        max_open_positions=args.max_positions,
        dry_run=not args.live,
    )

    trader = DemoPaperTrader(config=config)
    trader.run(once=args.once)


if __name__ == "__main__":
    main()
