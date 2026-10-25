#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Escáner Diario de Señales Cuantitativas (V3 Robust Daily Regime).

SOLO LECTURA / AUDITORÍA CAUSAL:
1. Conecta con MetaTrader 5 (exige cuenta DEMO).
2. Lee las últimas 250 barras D1 cerradas para los índices principales.
3. Evalúa la condición estructural alcista (Precio > SMA200), el régimen de volatilidad
   (ATR_Regime <= 1.80) y los gatillos de sobreventa institucional (RSI2 < 10, IBS < 0.20).
4. Informa con precisión milimétrica si hay señal para la apertura de la siguiente sesión,
   el Stop Loss de protección y el lotaje exacto según contract_specs.py.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# Asegurar path al raíz del proyecto
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trading_v2.backtesting.contract_specs import calculate_lot_size, get_contract_spec
from trading_v2.execution.demo_paper_trader import assert_demo_account, get_mt5_module
from trading_v2.research.regime_lab_v3 import add_indicators

SYMBOLS_TO_SCAN = [
    ("DAX40", "GERMANY40", "idx_dax_bollinger_dip"),
    ("SP500", "[SP500]", "idx_rsi2_dip_regime"),
    ("EURUSD", "EURUSD", "fx_eurusd_ker_exhaustion"),
    ("IBEX35", "[IBEX35]", "idx_ibex_bollinger_dip"),
]


def scan_markets(mt5, account_equity: float, risk_fraction: float = 0.0025, verbose: bool = True) -> list[dict]:
    results = []
    # Obtener cotización EURUSD para conversión USD -> EUR si aplica
    tick_eurusd = mt5.symbol_info_tick("EURUSD")
    eurusd_rate = float(tick_eurusd.bid) if tick_eurusd and tick_eurusd.bid > 0 else 1.12

    for market_label, symbol, strategy in SYMBOLS_TO_SCAN:
        spec = get_contract_spec(symbol)
        mt5.symbol_select(symbol, True)
        # 250 velas cerradas (start_pos=1 para excluir la vela de hoy si aún no ha cerrado)
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 1, 260)
        if rates is None or len(rates) < 220:
            results.append({
                "market": market_label, "symbol": symbol, "strategy": strategy,
                "status": "ERROR_DATOS_INSUFICIENTES",
            })
            continue

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.set_index("time", inplace=True)
        df.rename(
            columns={
                "open": "Open", "high": "High", "low": "Low",
                "close": "Close", "spread": "Spread", "tick_volume": "TickVolume",
            },
            inplace=True,
        )

        df = add_indicators(df)
        last = df.iloc[-1]
        last_dt = df.index[-1]

        close = float(last["Close"])
        sma200 = float(last["sma200"])
        sma5 = float(last["sma5"])
        rsi2 = float(last["rsi2"])
        ibs = float(last["ibs"])
        atr = float(last["atr20"])
        atr_regime = float(last["atr_regime"])

        trend_bullish = close > sma200
        vol_normal = atr_regime <= 1.80

        # Evaluación de gatillos según estrategia
        signal_active = False
        reason = []

        if not trend_bullish:
            reason.append(f"Precio ({close:.2f}) < SMA200 ({sma200:.2f}) [Tendencia bajista]")
        if not vol_normal:
            reason.append(f"Régimen ATR alto ({atr_regime:.2f} > 1.80) [Peligro de volatilidad]")

        if strategy == "idx_rsi2_dip_regime":
            dip_active = rsi2 < 10.0
            if dip_active:
                reason.append(f"RSI(2) en sobreventa extrema ({rsi2:.1f} < 10.0)")
            else:
                reason.append(f"RSI(2) neutral ({rsi2:.1f} >= 10.0)")
            signal_active = trend_bullish and vol_normal and dip_active
        elif strategy == "idx_rsi2_dip":
            dip_active = rsi2 < 10.0
            if dip_active:
                reason.append(f"RSI(2) en sobreventa extrema ({rsi2:.1f} < 10.0)")
            else:
                reason.append(f"RSI(2) neutral ({rsi2:.1f} >= 10.0)")
            signal_active = trend_bullish and dip_active
        elif strategy == "idx_ibs_dip":
            dip_active = ibs < 0.20
            if dip_active:
                reason.append(f"IBS en cierre de rango inferior ({ibs:.2f} < 0.20)")
            else:
                reason.append(f"IBS neutral ({ibs:.2f} >= 0.20)")
            signal_active = trend_bullish and dip_active
        elif strategy in ("idx_dax_bollinger_dip", "idx_ibex_bollinger_dip"):
            sigma_col = "bb_lower_20" if strategy == "idx_ibex_bollinger_dip" else "bb_lower_18"
            rsi_th = 10.0 if strategy == "idx_ibex_bollinger_dip" else 15.0
            sigma_label = "2.0σ" if strategy == "idx_ibex_bollinger_dip" else "1.8σ"
            bb_lower = float(last.get(sigma_col, close * 0.98))
            dip_active = (rsi2 < rsi_th) and (close <= bb_lower)
            if rsi2 < rsi_th:
                reason.append(f"RSI(2) en sobreventa ({rsi2:.1f} < {rsi_th:.1f})")
            else:
                reason.append(f"RSI(2) neutral ({rsi2:.1f} >= {rsi_th:.1f})")
            if close <= bb_lower:
                reason.append(f"Precio en agotamiento inferior Bollinger {sigma_label} ({close:.2f} <= {bb_lower:.2f})")
            else:
                reason.append(f"Precio dentro de bandas Bollinger ({close:.2f} > {bb_lower:.2f})")
            signal_active = trend_bullish and dip_active
        elif strategy == "fx_eurusd_ker_exhaustion":
            ker = float(last.get("ker10", 0.50))
            is_ranging = ker < 0.42
            bb_lo = float(last.get("bb_lower_20", close * 0.98))
            bb_up = float(last.get("bb_upper_20", close * 1.02))
            long_cond = is_ranging and (rsi2 < 8.0) and (close <= bb_lo)
            short_cond = is_ranging and (rsi2 > 92.0) and (close >= bb_up)
            if is_ranging:
                reason.append(f"Mercado en rango / no tendencial (KER10={ker:.2f} < 0.42)")
            else:
                reason.append(f"Mercado tendencial o ruidoso (KER10={ker:.2f} >= 0.42) [Entrada vetada]")
            if long_cond:
                reason.append(f"LONG: RSI2={rsi2:.1f} < 8.0 y Cierre <= Banda Inf 2.0σ ({close:.5f} <= {bb_lo:.5f})")
            elif short_cond:
                reason.append(f"SHORT: RSI2={rsi2:.1f} > 92.0 y Cierre >= Banda Sup 2.0σ ({close:.5f} >= {bb_up:.5f})")
            else:
                reason.append(f"Sin extremo de agotamiento en bandas 2.0σ (RSI2={rsi2:.1f})")
            signal_active = long_cond or short_cond

        # Dimensionamiento de lote si hubiera entrada
        stop_dist = 2.5 * atr
        estimated_sl = round(close - stop_dist, spec.digits)
        lot_res = calculate_lot_size(
            spec=spec,
            account_equity=account_equity,
            risk_fraction=risk_fraction,
            stop_distance_price=stop_dist,
            entry_price=close,
            eurusd_rate=eurusd_rate,
            leverage=100.0,
            account_currency="EUR",
        )

        results.append({
            "market": market_label,
            "symbol": symbol,
            "strategy": strategy,
            "last_bar_time": str(last_dt),
            "close": close,
            "sma200": sma200,
            "sma5": sma5,
            "dist_sma200_pct": round(100 * (close / sma200 - 1), 2),
            "rsi2": round(rsi2, 1),
            "ibs": round(ibs, 2),
            "atr20": round(atr, 2),
            "atr_regime": round(atr_regime, 2),
            "trend_bullish": trend_bullish,
            "vol_normal": vol_normal,
            "signal_active": signal_active,
            "reasons": reason,
            "recommended_lots": lot_res.lots if lot_res.status == "OK" else 0.0,
            "lot_status": lot_res.status,
            "risk_eur": lot_res.actual_risk_account_ccy,
            "estimated_sl": estimated_sl,
        })

    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description="Escáner Diario de Señales Cuantitativas V3")
    parser.add_argument("--risk-fraction", type=float, default=0.0025, help="Fracción de riesgo por operación (default: 0.25%%)")
    parser.add_argument("--terminal", help="Ruta a terminal64.exe si hay múltiples instancias")
    args = parser.parse_args(argv)

    mt5 = get_mt5_module()
    if mt5 is None:
        sys.exit("Error: MetaTrader5 no está instalado en este entorno Python.")

    if not (mt5.initialize(path=args.terminal) if args.terminal else mt5.initialize()):
        sys.exit(f"Error al conectar con MetaTrader 5: {mt5.last_error()}")

    try:
        acc = mt5.account_info()
        assert_demo_account(acc)
        equity = float(acc.equity)
        balance = float(acc.balance)
        currency = str(acc.currency)

        print("=" * 115)
        print(f"ESCÁNER DIARIO CUANTITATIVO V3 - ADMIRALS DEMO #{acc.login} ({acc.server})")
        print(f"Fecha UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} | Equity: {equity:.2f} {currency} | Riesgo por trade: {args.risk_fraction:.2%}")
        print("=" * 115)

        results = scan_markets(mt5, account_equity=equity, risk_fraction=args.risk_fraction)

        print(f"{'MERCADO':<10s} | {'SÍMBOLO':<10s} | {'ESTRATEGIA':<20s} | {'CIERRE':<9s} | {'SMA200':<9s} | {'RSI(2)':<6s} | {'IBS':<5s} | {'VOL REG':<7s} | {'SEÑAL':<12s} | {'LOTES':<6s}")
        print("-" * 115)

        active_signals = []
        for r in results:
            if r.get("status") == "ERROR_DATOS_INSUFICIENTES":
                print(f"{r['market']:<10s} | {r['symbol']:<10s} | DATOS INSUFICIENTES")
                continue

            sig_str = "[COMPRA]" if r["signal_active"] else "[ESPERAR]"
            print(
                f"{r['market']:<10s} | {r['symbol']:<10s} | {r['strategy']:<20s} | "
                f"{r['close']:<9.2f} | {r['sma200']:<9.2f} | {r['rsi2']:<6.1f} | "
                f"{r['ibs']:<5.2f} | {r['atr_regime']:<7.2f} | {sig_str:<12s} | {r['recommended_lots']:<6.2f}"
            )
            if r["signal_active"]:
                active_signals.append(r)

        print("=" * 115)

        # Comprobar si hay posiciones actualmente abiertas en MT5
        open_positions = mt5.positions_get()
        if open_positions:
            print("\nPOSICIONES ACTUALMENTE ABIERTAS EN BROKER:")
            for p in open_positions:
                side = "LONG" if p.type == 0 else "SHORT"
                print(f"  - Ticket #{p.ticket} | {p.symbol} | {side} | {p.volume} lotes | Open: {p.price_open} | Current: {p.price_current} | PnL: {p.profit:+.2f} EUR")
        else:
            print("\nPosiciones abiertas actualmente: 0")

        # Conclusiones operativas
        print("\nPLAN DE ACCION PARA LA SIGUIENTE SESION:")
        if active_signals:
            for s in active_signals:
                print(f"  * [EJECUTAR COMPRA] En {s['symbol']} con estrategia {s['strategy']}:")
                print(f"     - Entrar en Apertura de la siguiente sesion con {s['recommended_lots']} lotes (Riesgo: {s['risk_eur']:.2f} EUR).")
                print(f"     - Stop Loss catastrofico: {s['estimated_sl']:.2f} (-2.5 ATR).")
                print(f"     - Salida por regla: Cierre de vela por encima de SMA(5) ({s['sma5']:.2f}).")
        else:
            print("  * Ningun indice presenta sobreventa extrema hoy. No hay que operar forzadamente.")
            print("    El sistema preserva el capital y espera pacientemente el setup institucional.")
        print("=" * 115)

    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
