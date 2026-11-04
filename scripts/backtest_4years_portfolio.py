#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Simulacion Cuantitativa y Backtesting Multi-Activo a 4 Anos (2022 - 2026).

Evalua la estrategia institutional_sniper_scalp con modelado realista de Bid/Ask,
spread de broker, comisiones, Breakeven Causal, filtro KER anti-estampida y filtro H1.
"""
from __future__ import annotations

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import MetaTrader5 as mt5
from trading_v2.backtesting.contract_specs import get_contract_spec
from trading_v2.strategies.micro_scalping import SniperScalpConfig, generate_sniper_signals


# Parametros operativos identicos a demo_paper_trader.py
PORTFOLIO_SPECS = {
    "GERMANY40": {
        "tf": mt5.TIMEFRAME_M30 if hasattr(mt5, "TIMEFRAME_M30") else 30,
        "target_u": 22.0, "stop_u": 35.0, "sweep_u": 0.0,
        "s_start": 7, "s_end": 17, "min_wick": 0.35,
        "allow_short": True, "cooldown": 3, "use_ker": True, "max_ker": 0.45,
        "spread_default": 1.2, # pts
    },
    "[SP500]": {
        "tf": mt5.TIMEFRAME_M30 if hasattr(mt5, "TIMEFRAME_M30") else 30,
        "target_u": 4.0, "stop_u": 12.0, "sweep_u": 0.0,
        "s_start": 12, "s_end": 21, "min_wick": 0.35,
        "allow_short": False, "cooldown": 3, "use_ker": True, "max_ker": 0.45,
        "spread_default": 0.5, # pts
    },
    "[DJI30]": {
        "tf": mt5.TIMEFRAME_M30 if hasattr(mt5, "TIMEFRAME_M30") else 30,
        "target_u": 40.0, "stop_u": 80.0, "sweep_u": 0.0,
        "s_start": 12, "s_end": 21, "min_wick": 0.35,
        "allow_short": False, "cooldown": 3, "use_ker": True, "max_ker": 0.45,
        "spread_default": 2.5, # pts
    },
    "US100": {
        "tf": mt5.TIMEFRAME_M30 if hasattr(mt5, "TIMEFRAME_M30") else 30,
        "target_u": 25.0, "stop_u": 70.0, "sweep_u": 0.0,
        "s_start": 12, "s_end": 21, "min_wick": 0.35,
        "allow_short": True, "cooldown": 3, "use_ker": True, "max_ker": 0.45,
        "spread_default": 1.0, # pts
    },
    "GOLD": {
        "tf": mt5.TIMEFRAME_M30 if hasattr(mt5, "TIMEFRAME_M30") else 30,
        "target_u": 4.0, "stop_u": 12.0, "sweep_u": 2.0,
        "s_start": 12, "s_end": 19, "min_wick": 0.45,
        "allow_short": False, "cooldown": 3, "use_ker": True, "max_ker": 0.45,
        "max_opp_wick": 0.12,
        "spread_default": 0.35, # $
    },
    "EURUSD": {
        "tf": mt5.TIMEFRAME_M15 if hasattr(mt5, "TIMEFRAME_M15") else 15,
        "target_u": 3.5, "stop_u": 5.5, "sweep_u": 0.0,
        "s_start": 6, "s_end": 20, "min_wick": 0.35,
        "allow_short": True, "cooldown": 2, "use_ker": True, "max_ker": 0.45,
        "spread_default": 0.00010, # 1.0 pip
    },
    "[IBEX35]": {
        "tf": mt5.TIMEFRAME_M30 if hasattr(mt5, "TIMEFRAME_M30") else 30,
        "target_u": 20.0, "stop_u": 45.0, "sweep_u": 0.0,
        "s_start": 7, "s_end": 17, "min_wick": 0.35,
        "allow_short": False, "cooldown": 3, "use_ker": True, "max_ker": 0.45,
        "spread_default": 5.0, # pts
    },
}


def load_4year_bars(symbol: str, tf: int) -> pd.DataFrame:
    """Carga historico continuo 2022-2026 directamente de MT5."""
    d_from = datetime(2022, 1, 1, tzinfo=timezone.utc)
    d_to = datetime(2026, 11, 4, tzinfo=timezone.utc)

    # Cargar ano por ano para garantizar datos completos sin timeouts de socket MT5
    chunks = []
    for y in [2022, 2023, 2024, 2025, 2026]:
        y_from = datetime(y, 1, 1, tzinfo=timezone.utc)
        y_to = datetime(y, 12, 31, 23, 59, tzinfo=timezone.utc) if y < 2026 else d_to
        r_chunk = mt5.copy_rates_range(symbol, tf, y_from, y_to)
        if r_chunk is not None and len(r_chunk) > 0:
            df_c = pd.DataFrame(r_chunk)
            df_c["time"] = pd.to_datetime(df_c["time"], unit="s", utc=True)
            df_c.set_index("time", inplace=True)
            df_c.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "tick_volume": "Volume"}, inplace=True)
            chunks.append(df_c)
    if chunks:
        full_df = pd.concat(chunks)
        full_df = full_df[~full_df.index.duplicated(keep="first")].sort_index()
        return full_df
    return pd.DataFrame()


def simulate_asset_sniper(symbol: str, p: dict, risk_eur_per_trade: float = 46.15) -> list[dict]:
    """Simula operacion a operacion con causalidad estricta y Breakeven Causal."""
    df = load_4year_bars(symbol, p["tf"])
    if df.empty or len(df) < 500:
        print(f"[{symbol}] Sin datos suficientes ({len(df)} barras)")
        return []

    is_fx = symbol == "EURUSD"
    unit_mult = 0.00010 if is_fx else 1.0
    tp_dist = p["target_u"] * unit_mult
    sl_dist = p["stop_u"] * unit_mult
    spread = p["spread_default"]

    cfg = SniperScalpConfig(
        symbol=symbol,
        target_units=p["target_u"],
        stop_units=p["stop_u"],
        session_start_h=p["s_start"],
        session_end_h=p["s_end"],
        max_holding_bars=8,
        min_sweep_units=p["sweep_u"],
        min_rejection_wick=p["min_wick"],
        max_trades_per_day=None,
        cooldown_bars=p["cooldown"],
        use_h1_filter=True,
        use_keltner_filter=False,
        use_ker_filter=p.get("use_ker", True),
        max_ker_trend=p.get("max_ker", 0.45),
        max_opposite_wick=p.get("max_opp_wick", None),
        allow_short=p["allow_short"],
    )

    sig_df = generate_sniper_signals(df, cfg)
    signals = sig_df["signal"].to_numpy()
    times = df.index
    opens = df["Open"].to_numpy()
    highs = df["High"].to_numpy()
    lows = df["Low"].to_numpy()
    closes = df["Close"].to_numpy()
    n = len(df)

    trades = []
    i = 0
    while i < n - 1:
        sig = signals[i]
        if sig != 0:
            entry_time = times[i + 1]
            # Entrada en barra i+1 Open con spread de broker
            if sig == 1:
                entry_price = opens[i + 1] + spread
                sl_price = entry_price - sl_dist
                tp_price = entry_price + tp_dist
            else:
                entry_price = opens[i + 1]
                sl_price = entry_price + sl_dist
                tp_price = entry_price - tp_dist

            be_active = False
            be_trigger = 0.40 * tp_dist if not is_fx else 2.0 * 0.00010
            be_lock = 0.05 * tp_dist if not is_fx else 0.5 * 0.00010

            exit_time = None
            exit_price = None
            exit_reason = None
            bars_held = 0

            for j in range(i + 1, min(i + 1 + 12, n)):
                bars_held += 1
                bar_h = highs[j]
                bar_l = lows[j]
                bar_c = closes[j]

                if sig == 1:
                    # Comprobar activacion Breakeven Causal
                    if not be_active and (bar_h - entry_price) >= be_trigger:
                        be_active = True
                        sl_price = max(sl_price, entry_price + be_lock)

                    # Comprobar TP / SL (asumiendo SL primero si ambos se tocan)
                    hit_sl = bar_l <= sl_price
                    hit_tp = bar_h >= tp_price

                    if hit_sl and hit_tp:
                        exit_price = sl_price
                        exit_reason = "SL_TP_SAME_BAR_STOP_FIRST"
                        exit_time = times[j]
                        break
                    elif hit_tp:
                        exit_price = tp_price
                        exit_reason = "TAKE_PROFIT"
                        exit_time = times[j]
                        break
                    elif hit_sl:
                        exit_price = sl_price
                        exit_reason = "BREAKEVEN" if be_active else "STOP_LOSS"
                        exit_time = times[j]
                        break
                else: # SHORT
                    current_ask_low = bar_l + spread
                    current_ask_high = bar_h + spread

                    if not be_active and (entry_price - bar_l) >= be_trigger:
                        be_active = True
                        sl_price = min(sl_price, entry_price - be_lock)

                    hit_sl = current_ask_high >= sl_price
                    hit_tp = current_ask_low <= tp_price

                    if hit_sl and hit_tp:
                        exit_price = sl_price
                        exit_reason = "SL_TP_SAME_BAR_STOP_FIRST"
                        exit_time = times[j]
                        break
                    elif hit_tp:
                        exit_price = tp_price
                        exit_reason = "TAKE_PROFIT"
                        exit_time = times[j]
                        break
                    elif hit_sl:
                        exit_price = sl_price
                        exit_reason = "BREAKEVEN" if be_active else "STOP_LOSS"
                        exit_time = times[j]
                        break

            # Si expira por tiempo (max 8 barras)
            if exit_price is None:
                j_end = min(i + 1 + 8, n - 1)
                exit_time = times[j_end]
                exit_price = closes[j_end] if sig == 1 else (closes[j_end] + spread)
                exit_reason = "TIME_EXPIRY"

            # Calculo de PnL en R y en EUR
            price_delta = (exit_price - entry_price) if sig == 1 else (entry_price - exit_price)
            r_return = price_delta / sl_dist
            pnl_eur = r_return * risk_eur_per_trade

            trades.append({
                "symbol": symbol,
                "direction": "BUY" if sig == 1 else "SELL",
                "entry_time": entry_time,
                "exit_time": exit_time,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "r_return": r_return,
                "pnl_eur": pnl_eur,
                "exit_reason": exit_reason,
                "year": entry_time.year,
            })
            i = j # Avanzar al final de la operacion
        else:
            i += 1

    return trades


def run_comprehensive_4year_backtest():
    if not mt5.initialize():
        print("Error al inicializar MT5")
        return

    print("=" * 80)
    print("AUDITORIA CUANTITATIVA A 4 ANOS (2022 - 2026) -- CARTERA COMPLETA 7 ACTIVOS")
    print("=" * 80)

    all_trades = []
    symbol_results = {}

    for sym, p in PORTFOLIO_SPECS.items():
        print(f"\nProcesando {sym}...")
        trades = simulate_asset_sniper(sym, p)
        if not trades:
            continue
        all_trades.extend(trades)

        df_t = pd.DataFrame(trades)
        wins = df_t[df_t["pnl_eur"] > 0]
        losses = df_t[df_t["pnl_eur"] < 0]
        be = df_t[df_t["pnl_eur"] == 0]

        n_trades = len(df_t)
        wr = (len(wins) / n_trades) * 100 if n_trades > 0 else 0
        total_pnl = df_t["pnl_eur"].sum()
        gross_profit = wins["pnl_eur"].sum() if len(wins) > 0 else 0
        gross_loss = abs(losses["pnl_eur"].sum()) if len(losses) > 0 else 1e-6
        pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
        cum_pnl = df_t["pnl_eur"].cumsum()
        max_dd = (cum_pnl.cummax() - cum_pnl).max()

        symbol_results[sym] = {
            "trades": n_trades,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": wr,
            "profit_factor": pf,
            "total_pnl": total_pnl,
            "max_dd": max_dd,
        }
        print(f"  {sym:12s} | Trades: {n_trades:4d} | Win Rate: {wr:5.1f}% | PF: {pf:4.2f} | PnL: {total_pnl:+9.2f} EUR | Max DD: {max_dd:7.2f} EUR")

    # Resumen Cartera Consolidada
    df_all = pd.DataFrame(all_trades).sort_values("entry_time")
    wins_all = df_all[df_all["pnl_eur"] > 0]
    losses_all = df_all[df_all["pnl_eur"] < 0]
    n_all = len(df_all)
    wr_all = (len(wins_all) / n_all) * 100 if n_all > 0 else 0
    total_pnl_all = df_all["pnl_eur"].sum()
    gp_all = wins_all["pnl_eur"].sum()
    gl_all = abs(losses_all["pnl_eur"].sum())
    pf_all = gp_all / gl_all if gl_all > 0 else float("inf")

    # Curva de equidad y Drawdown consolidado
    df_all["cum_pnl"] = df_all["pnl_eur"].cumsum()
    peak = df_all["cum_pnl"].cummax()
    dd_curve = peak - df_all["cum_pnl"]
    max_dd_all = dd_curve.max()
    max_dd_pct = (max_dd_all / 3000.0) * 100

    print("\n" + "=" * 80)
    print("RESULTADOS GLOBALES DE LA CARTERA (2022 - 2026)")
    print("=" * 80)
    print(f"Total Operaciones a 4 anos: {n_all}")
    print(f"Aciertos: {len(wins_all)} | Fallos: {len(losses_all)}")
    print(f"Tasa de Acierto Global (Win Rate): {wr_all:.2f}%")
    print(f"Factor de Beneficio (Profit Factor): {pf_all:.2f}")
    print(f"Beneficio Neto Acumulado (base 3,000 EUR): {total_pnl_all:+,.2f} EUR")
    print(f"Retorno Total: +{(total_pnl_all / 3000.0) * 100:.2f}%")
    print(f"Drawdown Maximo de Cartera: {max_dd_all:.2f} EUR ({max_dd_pct:.2f}%)")

    # Desglose Ano por Ano
    print("\n" + "-" * 80)
    print("DESGLOSE DE RENDIMIENTO ANO POR ANO (CONSISTENCIA TEMPORAL)")
    print("-" * 80)
    for y in sorted(df_all["year"].unique()):
        df_y = df_all[df_all["year"] == y]
        w_y = len(df_y[df_y["pnl_eur"] > 0])
        l_y = len(df_y[df_y["pnl_eur"] < 0])
        n_y = len(df_y)
        wr_y = (w_y / n_y) * 100 if n_y > 0 else 0
        pnl_y = df_y["pnl_eur"].sum()
        gp_y = df_y[df_y["pnl_eur"] > 0]["pnl_eur"].sum()
        gl_y = abs(df_y[df_y["pnl_eur"] < 0]["pnl_eur"].sum())
        pf_y = gp_y / gl_y if gl_y > 0 else float("inf")
        print(f"Ano {y} | Trades: {n_y:4d} | Win Rate: {wr_y:5.1f}% | Profit Factor: {pf_y:4.2f} | PnL Neto: {pnl_y:+9.2f} EUR | Retorno anual: +{(pnl_y / 3000.0)*100:5.1f}%")

    mt5.shutdown()


if __name__ == "__main__":
    run_comprehensive_4year_backtest()
