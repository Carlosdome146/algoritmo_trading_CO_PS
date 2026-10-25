"""Motor de Backtesting Intradía — M15 / M30 (6 años, anti-lookahead).

Estándares de calidad:
- Datos directos de MetaTrader 5 (hasta 6 años de barras M15/M30).
- Entrada siempre en apertura de la barra SIGUIENTE a la señal (causalidad estricta).
- Spreads reales descontados en cada entrada y salida.
- Comisiones IC Markets Raw (modelo de costes más conservador).
- Métricas: WR, Profit Factor, MaxDD%, t-stat, Wilson Lower Bound, Sharpe mensual.
- Filtro de sesión de liquidez institucional (sin operar fuera de ventanas activas).
- Resultado: DataFrame de operaciones + dict de métricas + veredicto PASS/FAIL.

Criterio de aprobación: WR > 70% Y MaxDD% < 5% Y N >= 100 trades en 6 años.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Callable, Literal

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Constantes y configuración global
# ---------------------------------------------------------------------------

PASS_WR = 70.0          # Win rate mínimo para aprobar (%)
PASS_MAX_DD = 5.0       # Drawdown máximo tolerable (% del capital simulado)
MIN_TRADES = 100        # Mínimo de operaciones en 6 años para considerar estadístico
CAPITAL_BASE = 3000.0   # Capital de referencia para calcular DD en euros

# Ventanas de sesión institucional UTC (hora inicio, hora fin) — inclusive
SESSION_UTC: dict[str, tuple[int, int]] = {
    "GERMANY40":  (7,  17),
    "DE40":       (7,  17),
    "[SP500]":    (13, 21),
    "US500":      (13, 21),
    "US100":      (13, 21),
    "USTEC":      (13, 21),
    "[DJI30]":    (13, 21),
    "US30":       (13, 21),
    "EURUSD":     (7,  17),
    "GOLD":       (7,  20),
    "XAUUSD":     (7,  20),
}

# Costes en precio por lote (modelo IC Markets Raw — más conservador)
COST_PER_LOT: dict[str, float] = {
    "EURUSD":    0.000070,   # 0.7 pips round-trip (~7 USD/lote)
    "GERMANY40": 0.0,        # spread already in bars; ~1 pt indexed
    "[SP500]":   0.0,
    "US100":     0.0,
    "GOLD":      0.0,
    "XAUUSD":    0.0,
}

# Multiplicador de punto a precio para cada activo
POINT: dict[str, float] = {
    "EURUSD":    0.00001,
    "GERMANY40": 0.01,
    "DE40":      0.01,
    "[SP500]":   0.01,
    "US500":     0.01,
    "US100":     0.01,
    "USTEC":     0.01,
    "[DJI30]":   0.01,
    "US30":      0.01,
    "GOLD":      0.01,
    "XAUUSD":    0.01,
}


# ---------------------------------------------------------------------------
# Tipos de datos
# ---------------------------------------------------------------------------

@dataclass
class BacktestConfig:
    """Configuración completa de un backtest."""
    symbol: str
    timeframe: Literal["M15", "M30"]
    bars_back: int = 25000          # ~6 años en M15 ≈ 96k barras; 25k ≈ 2.6 años de barras activas
    risk_per_trade_pct: float = 0.5  # % de capital por operación (gestión monetaria)
    max_holding_bars: int = 16       # Time-stop: 16 barras M15 = 4 horas
    use_session_filter: bool = True  # Filtrar por ventana de liquidez institucional
    require_n: int = MIN_TRADES      # N mínimo de operaciones para veredicto válido


@dataclass
class TradeResult:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    symbol: str
    side: Literal["LONG", "SHORT"]
    entry_px: float
    exit_px: float
    sl: float
    tp: float
    r: float                    # Rendimiento en unidades de riesgo (R)
    pnl_eur: float              # PnL en EUR con tamaño fijo de 1 micro-lote
    reason: str                 # TP | STOP | TIMEOUT
    bars_held: int


@dataclass
class BacktestMetrics:
    """Métricas estadísticas completas de un backtest."""
    symbol: str
    timeframe: str
    strategy_name: str
    n_trades: int
    win_rate: float             # %
    profit_factor: float
    mean_r: float
    total_r: float
    max_dd_pct: float           # % del capital base
    sharpe_monthly: float
    t_stat: float
    wilson_lb_pct: float        # Lower bound del Wilson interval (95% CI)
    verdict: str                # PASS ✅ | FAIL ❌ | MARGINAL ⚠️
    fail_reasons: list[str] = field(default_factory=list)
    notes: str = ""

    def __str__(self) -> str:
        icon = {"PASS OK": "[PASS]", "FAIL XX": "[FAIL]", "MARGINAL ~": "[MARG]"}.get(self.verdict, "[?]")
        return (
            f"{icon} {self.strategy_name} | {self.symbol} {self.timeframe} | "
            f"N={self.n_trades} | WR={self.win_rate:.1f}% | PF={self.profit_factor:.2f} | "
            f"MaxDD={self.max_dd_pct:.2f}% | t={self.t_stat:.2f} | W-LB={self.wilson_lb_pct:.1f}%"
        )


# ---------------------------------------------------------------------------
# Utilidades estadísticas
# ---------------------------------------------------------------------------

def wilson_lower_bound(wins: int, n: int, z: float = 1.645) -> float:
    """Límite inferior del intervalo de Wilson al 90% de confianza."""
    if n == 0:
        return 0.0
    p = wins / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (centre - margin) / denom) * 100


def compute_metrics(trades_df: pd.DataFrame, symbol: str, tf: str, strategy: str) -> BacktestMetrics:
    """Calcula todas las métricas estadísticas a partir del DataFrame de operaciones."""
    n = len(trades_df)
    if n == 0:
        return BacktestMetrics(
            symbol=symbol, timeframe=tf, strategy_name=strategy,
            n_trades=0, win_rate=0, profit_factor=0, mean_r=0,
            total_r=0, max_dd_pct=0, sharpe_monthly=0, t_stat=0,
            wilson_lb_pct=0, verdict="FAIL ❌", fail_reasons=["Sin operaciones"],
        )

    r_arr = trades_df["r"].to_numpy(dtype=float)
    wins = int((r_arr > 0).sum())
    losses = int((r_arr <= 0).sum())
    wr = wins / n * 100

    gross_win = float(r_arr[r_arr > 0].sum()) if wins > 0 else 0.0
    gross_loss = float(abs(r_arr[r_arr <= 0].sum())) if losses > 0 else 1e-9
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")

    mean_r = float(r_arr.mean())
    std_r = float(r_arr.std(ddof=1)) if n > 1 else 0.0
    t_stat = (mean_r / (std_r / math.sqrt(n))) if std_r > 0 else 0.0

    # Drawdown en curva de R acumulada
    cum_r = np.cumsum(r_arr)
    running_max = np.maximum.accumulate(cum_r)
    dd_r = running_max - cum_r
    max_dd_r = float(dd_r.max()) if len(dd_r) > 0 else 0.0

    # Convertir DD en % del capital base (asumiendo 0.5% de riesgo por trade)
    risk_eur = CAPITAL_BASE * 0.005
    max_dd_pct = (max_dd_r * risk_eur / CAPITAL_BASE) * 100

    # Sharpe mensual (aproximación: agrupando PnL mensual)
    if "entry_time" in trades_df.columns:
        trades_df = trades_df.copy()
        # Convertir a UTC naive antes de to_period para evitar UserWarning de timezone
        trades_df["month"] = trades_df["entry_time"].dt.tz_localize(None).dt.to_period("M")
        monthly_r = trades_df.groupby("month")["r"].sum()
        if len(monthly_r) > 1:
            sharpe = float(monthly_r.mean() / monthly_r.std(ddof=1)) * math.sqrt(12)
        else:
            sharpe = 0.0
    else:
        sharpe = 0.0

    wilson_lb = wilson_lower_bound(wins, n)
    wilson_lb_pct = wilson_lb

    # Veredicto
    fail_reasons = []
    if wr < PASS_WR:
        fail_reasons.append(f"WR {wr:.1f}% < {PASS_WR}%")
    if max_dd_pct > PASS_MAX_DD:
        fail_reasons.append(f"MaxDD {max_dd_pct:.2f}% > {PASS_MAX_DD}%")
    if n < MIN_TRADES:
        fail_reasons.append(f"Solo {n} trades (mínimo {MIN_TRADES})")
    if t_stat < 1.5:
        fail_reasons.append(f"t-stat {t_stat:.2f} < 1.5 (señal estadística débil)")

    if not fail_reasons:
        verdict = "PASS OK"
    elif wr >= PASS_WR and max_dd_pct <= PASS_MAX_DD and n >= MIN_TRADES:
        verdict = "MARGINAL ~"
    else:
        verdict = "FAIL XX"

    return BacktestMetrics(
        symbol=symbol, timeframe=tf, strategy_name=strategy,
        n_trades=n, win_rate=wr, profit_factor=pf, mean_r=mean_r,
        total_r=float(cum_r[-1]) if len(cum_r) > 0 else 0.0,
        max_dd_pct=max_dd_pct, sharpe_monthly=sharpe,
        t_stat=t_stat, wilson_lb_pct=wilson_lb_pct,
        verdict=verdict, fail_reasons=fail_reasons,
    )


# ---------------------------------------------------------------------------
# Descarga de datos desde MT5
# ---------------------------------------------------------------------------

def fetch_bars(symbol: str, timeframe_str: str, bars_back: int) -> pd.DataFrame:
    """Descarga barras históricas de MT5 y las devuelve como DataFrame normalizado."""
    try:
        import MetaTrader5 as mt5
    except ImportError:
        raise RuntimeError("MetaTrader5 no está instalado. Instala con: pip install MetaTrader5")

    tf_map = {
        "M5":  mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1":  mt5.TIMEFRAME_H1,
        "H4":  mt5.TIMEFRAME_H4,
        "D1":  mt5.TIMEFRAME_D1,
    }
    tf = tf_map.get(timeframe_str.upper())
    if tf is None:
        raise ValueError(f"Timeframe desconocido: {timeframe_str}")

    if not mt5.initialize():
        raise RuntimeError(f"No se pudo conectar a MT5: {mt5.last_error()}")

    rates = mt5.copy_rates_from_pos(symbol, tf, 0, bars_back)
    if rates is None or len(rates) == 0:
        raise ValueError(f"Sin datos para {symbol} {timeframe_str}: {mt5.last_error()}")

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    df.sort_index(inplace=True)
    df = df[~df.index.duplicated(keep="first")]

    df.rename(columns={
        "open":       "Open",
        "high":       "High",
        "low":        "Low",
        "close":      "Close",
        "tick_volume": "TickVolume",
        "spread":     "Spread",
    }, inplace=True)

    # Filtrar solo los últimos 6 años
    cutoff = pd.Timestamp.now(tz="UTC") - pd.DateOffset(years=6)
    df = df[df.index >= cutoff]

    print(f"[DATA] {symbol} {timeframe_str}: {len(df):,} barras cargadas "
          f"({df.index[0].date()} -> {df.index[-1].date()})")
    return df


def add_h1_trend(df_m15: pd.DataFrame, symbol: str, bars_h1: int = 5000) -> pd.DataFrame:
    """Añade columna h1_trend (+1/-1) mediante merge causal con datos H1."""
    try:
        import MetaTrader5 as mt5
    except ImportError:
        df_m15 = df_m15.copy()
        df_m15["h1_trend"] = 0
        return df_m15

    rates_h1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, bars_h1)
    if rates_h1 is None or len(rates_h1) == 0:
        df_m15 = df_m15.copy()
        df_m15["h1_trend"] = 0
        return df_m15

    h1 = pd.DataFrame(rates_h1)
    h1["time"] = pd.to_datetime(h1["time"], unit="s", utc=True)
    h1.set_index("time", inplace=True)
    c_h1 = h1["close"]
    h1["ema20"] = c_h1.ewm(span=20, adjust=False).mean()
    h1["ema50"] = c_h1.ewm(span=50, adjust=False).mean()
    h1["h1_trend"] = np.where(h1["ema20"] > h1["ema50"], 1, -1)

    # Merge causal: la barra H1 que cierra en T está disponible para M15 en T+1h
    h1["close_time"] = h1.index + pd.Timedelta(hours=1)
    m15_times = pd.DataFrame({
        "m15_close": df_m15.index + pd.Timedelta(minutes=15),
        "orig_idx":  np.arange(len(df_m15)),
    }).sort_values("m15_close")

    aligned = pd.merge_asof(
        m15_times,
        h1[["close_time", "h1_trend"]].sort_values("close_time"),
        left_on="m15_close",
        right_on="close_time",
        direction="backward",
    ).sort_values("orig_idx")

    df_m15 = df_m15.copy()
    df_m15["h1_trend"] = aligned["h1_trend"].fillna(0).to_numpy()
    return df_m15


# ---------------------------------------------------------------------------
# Motor de simulación genérico
# ---------------------------------------------------------------------------

def add_base_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Añade indicadores técnicos base (ATR, RSI2, SMA, Bollinger) al DataFrame."""
    out = df.copy()
    c, h, l, o = out["Close"], out["High"], out["Low"], out["Open"]

    # ATR(14)
    prev_c = c.shift(1)
    tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    out["atr14"] = tr.rolling(14, min_periods=5).mean()

    # RSI(2) — sensible a extremos de corto plazo
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    out["rsi2"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))

    # RSI(14) — para tendencia media
    up14 = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    dn14 = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    out["rsi14"] = 100 - 100 / (1 + up14 / dn14.replace(0, np.nan))

    # Medias móviles
    out["sma20"]  = c.rolling(20, min_periods=10).mean()
    out["sma50"]  = c.rolling(50, min_periods=20).mean()
    out["sma200"] = c.rolling(200, min_periods=50).mean()
    out["ema20"]  = c.ewm(span=20, adjust=False).mean()
    out["ema50"]  = c.ewm(span=50, adjust=False).mean()

    # Bollinger Bands (20, 2.0σ)
    std20 = c.rolling(20, min_periods=10).std(ddof=0)
    out["bb_mid"] = out["sma20"]
    out["bb_up"]  = out["sma20"] + 2.0 * std20
    out["bb_lo"]  = out["sma20"] - 2.0 * std20

    # Mechas y CLV
    rng = (h - l).replace(0, np.nan)
    out["clv"]        = ((c - l) / rng).fillna(0.5)
    out["lower_wick"] = ((np.minimum(o, c) - l) / rng).fillna(0.0)
    out["upper_wick"] = ((h - np.maximum(o, c)) / rng).fillna(0.0)

    # Extremos de las últimas 4 barras (1 hora en M15 = Initial Balance)
    out["ib_high"] = h.shift(1).rolling(4, min_periods=2).max()
    out["ib_low"]  = l.shift(1).rolling(4, min_periods=2).min()

    # Hora UTC
    out["hour_utc"]   = out.index.hour
    out["minute_utc"] = out.index.minute
    out["weekday"]    = out.index.weekday  # 0=lunes, 4=viernes

    return out


def simulate_strategy(
    df: pd.DataFrame,
    symbol: str,
    signal_fn: Callable[[pd.DataFrame], np.ndarray],
    stop_atr: float = 1.5,
    tp_atr: float = 1.0,
    max_holding_bars: int = 16,
    use_session: bool = True,
    use_breakeven: bool = True,
    be_trigger_atr: float = 0.40,
    be_lock_atr: float = 0.05,
) -> pd.DataFrame:
    """
    Motor de simulación genérico anti-lookahead.

    Args:
        df: DataFrame con indicadores ya calculados (incluyendo 'atr14', 'Spread', etc.)
        symbol: Símbolo de mercado (para extraer costes y punto).
        signal_fn: Función que recibe df y devuelve array de señales (-1, 0, 1).
                   DEBE ser causal (no usar datos del futuro).
        stop_atr: Múltiplo de ATR para el Stop Loss.
        tp_atr: Múltiplo de ATR para el Take Profit.
        max_holding_bars: Time-stop en barras.
        use_session: Aplicar filtro de sesión institucional.
        use_breakeven: Activar breakeven automático.
        be_trigger_atr: Ganancia en ATR para activar breakeven.
        be_lock_atr: ATR de colchón sobre entrada en el breakeven.

    Returns:
        DataFrame con una fila por operación cerrada.
    """
    # Extraer parámetros por activo
    point = POINT.get(symbol, 0.01)
    comm = COST_PER_LOT.get(symbol, 0.0)
    session = SESSION_UTC.get(symbol, (0, 24)) if use_session else (0, 24)

    # Generar señales (causal: la señal de la barra i aplica a la barra i+1)
    signals = signal_fn(df)

    c_arr  = df["Close"].to_numpy(dtype=float)
    o_arr  = df["Open"].to_numpy(dtype=float)
    h_arr  = df["High"].to_numpy(dtype=float)
    l_arr  = df["Low"].to_numpy(dtype=float)
    spr    = df["Spread"].to_numpy(dtype=float) * point
    atr    = df["atr14"].to_numpy(dtype=float)
    hours  = df["hour_utc"].to_numpy(dtype=int)
    n      = len(df)
    idx    = df.index

    trades = []
    i = 50  # Warm-up de 50 barras

    while i < n - 1:
        sig = int(signals[i])
        if sig == 0:
            i += 1
            continue

        # Filtro de sesión
        if use_session and not (session[0] <= hours[i] <= session[1]):
            i += 1
            continue

        # No operar el viernes después de las 20h UTC (riesgo de weekend gap)
        if df.index[i].weekday() == 4 and hours[i] >= 20:
            i += 1
            continue

        # Filtro de spread excesivo (> 5% del ATR)
        cur_atr = atr[i]
        if not math.isfinite(cur_atr) or cur_atr <= 0:
            i += 1
            continue
        if spr[i] > 0.05 * cur_atr:
            i += 1
            continue

        # Entrada en apertura de barra siguiente (causal)
        k = i + 1
        side = sig  # +1 LONG, -1 SHORT

        entry = o_arr[k] + side * (spr[k] / 2.0)
        sl = entry - side * stop_atr * cur_atr
        tp = entry + side * tp_atr * cur_atr

        exit_px = None
        reason  = "TIMEOUT"
        j = k
        sl_current = sl  # SL puede moverse al breakeven

        for j in range(k, min(n, k + max_holding_bars)):
            bar_spr = spr[j]
            # Precios ejecutables (Bid para LONG, Ask para SHORT)
            eval_lo = l_arr[j] - (bar_spr / 2.0) if side == 1 else l_arr[j] + (bar_spr / 2.0)
            eval_hi = h_arr[j] + (bar_spr / 2.0) if side == -1 else h_arr[j] - (bar_spr / 2.0)

            hit_sl = (eval_lo <= sl_current) if side == 1 else (eval_hi >= sl_current)
            hit_tp = (eval_hi >= tp)         if side == 1 else (eval_lo <= tp)

            if hit_sl and hit_tp:
                exit_px = sl_current
                reason  = "STOP_CONSERVATIVE"
                break
            elif hit_sl:
                exit_px = sl_current
                reason  = "STOP"
                break
            elif hit_tp:
                exit_px = tp
                reason  = "TP"
                break

            # Breakeven automático
            if use_breakeven:
                unrealized = side * (c_arr[j] - entry)
                if unrealized >= be_trigger_atr * cur_atr:
                    sl_current = entry + side * be_lock_atr * cur_atr

        if exit_px is None:
            j = min(n - 1, k + max_holding_bars - 1)
            exit_px = c_arr[j] - side * (spr[j] / 2.0)
            reason  = "TIMEOUT"

        net_price = side * (exit_px - entry) - comm
        r = net_price / (stop_atr * cur_atr) if cur_atr > 0 else 0.0

        trades.append({
            "entry_time": idx[k],
            "exit_time":  idx[j],
            "symbol":     symbol,
            "side":       "LONG" if side == 1 else "SHORT",
            "entry_px":   entry,
            "exit_px":    exit_px,
            "sl":         sl,
            "tp":         tp,
            "r":          r,
            "pnl_eur":    net_price * 1000,   # aprox. 1 micro-lote en EUR
            "reason":     reason,
            "bars_held":  j - k + 1,
        })

        i = j + 1  # Sin solapamiento de posiciones

    return pd.DataFrame(trades)


# ---------------------------------------------------------------------------
# Runner principal de un backtest completo
# ---------------------------------------------------------------------------

def run_backtest(
    strategy_name: str,
    symbol: str,
    timeframe: str,
    signal_fn: Callable[[pd.DataFrame], np.ndarray],
    stop_atr: float = 1.5,
    tp_atr: float = 1.0,
    max_holding_bars: int = 16,
    use_session: bool = True,
    use_h1_trend: bool = False,
    bars_back: int = 25000,
    add_indicators_fn: Callable | None = None,
    notes: str = "",
) -> tuple[BacktestMetrics, pd.DataFrame]:
    """
    Ejecuta un backtest completo con descarga de datos y devuelve métricas + trades.

    Usage:
        def my_signal(df):
            # df tiene todos los indicadores base + h1_trend si use_h1_trend=True
            signals = np.zeros(len(df))
            # ... lógica de entrada ...
            return signals

        metrics, trades = run_backtest("MiEstrategia", "[SP500]", "M15", my_signal)
    """
    # 1. Descargar datos
    df = fetch_bars(symbol, timeframe, bars_back)

    # 2. Añadir indicadores base
    df = add_base_indicators(df)

    # 3. Añadir tendencia H1 si se requiere
    if use_h1_trend:
        df = add_h1_trend(df, symbol)

    # 4. Indicadores adicionales del usuario
    if add_indicators_fn is not None:
        df = add_indicators_fn(df)

    # 5. Simular
    trades_df = simulate_strategy(
        df=df,
        symbol=symbol,
        signal_fn=signal_fn,
        stop_atr=stop_atr,
        tp_atr=tp_atr,
        max_holding_bars=max_holding_bars,
        use_session=use_session,
    )

    # 6. Calcular métricas
    m = compute_metrics(trades_df, symbol, timeframe, strategy_name)
    m.notes = notes

    return m, trades_df
