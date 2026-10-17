"""Simulador OFFLINE: señal al cierre i -> entrada a apertura i+1.

Importes USD hipotéticos normalizados a riesgo R. No se comprueban lotes,
margen, swaps ni condiciones de trading del broker.
OHLC tratado como precio medio con spread simétrico bid/ask.
"""
from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from .metrics import summarize

@dataclass(frozen=True)
class Config:
    initial_equity: float = 3000.0
    risk_fraction: float = .0025
    sl_atr: float = 1.2
    tp_atr: float = 1.8
    point: float = .01
    slippage_points: float = 2.0
    fixed_spread_points: float | None = None
    max_bars_held: int = 32

    def __post_init__(self):
        if self.initial_equity <= 0 or not 0 < self.risk_fraction <= .01:
            raise ValueError("Capital positivo y riesgo entre 0 y 1% requeridos")
        if min(self.sl_atr, self.tp_atr, self.point) <= 0 or self.slippage_points < 0:
            raise ValueError("ATR y point positivos; slippage no negativo")
        if self.fixed_spread_points is not None and self.fixed_spread_points < 0:
            raise ValueError("Spread negativo")
        if self.max_bars_held < 1:
            raise ValueError("max_bars_held debe ser positivo")

def run_backtest(bars: pd.DataFrame, cfg: Config) -> tuple[dict, list[dict]]:
    if len(bars) < 100:
        raise ValueError("Se requieren al menos 100 velas e indicadores calculados")
    if cfg.fixed_spread_points is None and "Spread" not in bars:
        raise ValueError("Se requiere Spread en CSV o fixed_spread_points explícito")
    capital = cfg.initial_equity
    peak = capital
    max_dd = 0.0
    trades: list[dict] = []
    i = 1
    while i < len(bars):
        # Señal de vela CERRADA i-1; ejecución como pronto en apertura i.
        signal = int(bars["signal"].iloc[i-1])
        atr = bars["atr"].iloc[i-1]
        if signal == 0 or pd.isna(atr) or float(atr) <= 0:
            i += 1
            continue
        spread_pts = cfg.fixed_spread_points if cfg.fixed_spread_points is not None else float(bars["Spread"].iloc[i])
        if pd.isna(spread_pts) or spread_pts < 0:
            i += 1
            continue
        spread_price = spread_pts * cfg.point
        slippage = cfg.slippage_points * cfg.point
        side = signal
        entry_time = str(bars.index[i])
        entry_mid = float(bars["Open"].iloc[i])
        entry = entry_mid + side*spread_price/2 + side*slippage
        stop_distance = cfg.sl_atr * float(atr)
        sl = entry - side*stop_distance
        tp = entry + side*cfg.tp_atr*float(atr)
        stake = capital * cfg.risk_fraction
        exit_idx = min(len(bars)-1, i + cfg.max_bars_held - 1)
        reason = "TIMEOUT"
        exit_executable = None
        for j in range(i, exit_idx+1):
            sp = cfg.fixed_spread_points if cfg.fixed_spread_points is not None else float(bars["Spread"].iloc[j])
            if pd.isna(sp) or sp < 0:
                raise ValueError(f"Spread inválido durante operación en vela {j}")
            spread_j = sp*cfg.point
            # LONG sale al bid; SHORT recompra al ask.
            op = float(bars["Open"].iloc[j]) - side*spread_j/2
            hi = float(bars["High"].iloc[j]) - side*spread_j/2
            lo = float(bars["Low"].iloc[j]) - side*spread_j/2
            # Gaps adversos: no fingir ejecución al precio del stop.
            if (side == 1 and op <= sl) or (side == -1 and op >= sl):
                exit_executable = op - side*slippage
                exit_idx = j
                reason = "SL_GAP"
                break
            hit_sl = lo <= sl if side == 1 else hi >= sl
            hit_tp = hi >= tp if side == 1 else lo <= tp
            if hit_sl:  # Si la vela toca TP y SL, asumimos primero SL.
                exit_executable = sl - side*slippage
                exit_idx = j
                reason = "SL" if not hit_tp else "SL_TP_SAME_BAR"
                break
            if hit_tp:
                exit_executable = tp - side*slippage
                exit_idx = j
                reason = "TP"
                break
        if exit_executable is None:
            j = exit_idx
            sp = cfg.fixed_spread_points if cfg.fixed_spread_points is not None else float(bars["Spread"].iloc[j])
            exit_executable = float(bars["Close"].iloc[j]) - side*sp*cfg.point/2 - side*slippage
        realized_R = side*(exit_executable-entry)/stop_distance
        pnl = stake*realized_R
        capital += pnl
        peak = max(peak, capital)
        max_dd = max(max_dd, (peak-capital)/peak)
        trades.append({
            "signal_at": str(bars.index[i-1]), "entry_at": entry_time,
            "exit_at": str(bars.index[exit_idx]),
            "direction": "LONG" if side == 1 else "SHORT",
            "reason": reason, "entry": round(entry,6),
            "exit": round(exit_executable,6),
            "stop": round(sl,6), "target": round(tp,6),
            "realized_R": round(realized_R,6), "pnl_usd": round(pnl,6)
        })
        # Sin posiciones solapadas, nueva señal después del cierre.
        i = exit_idx+1
    return summarize(trades, cfg.initial_equity, capital, max_dd), trades
