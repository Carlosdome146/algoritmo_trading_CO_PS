#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Preflight de trading algorítmico MT5: SÓLO LECTURA.

Diseñado para la fase 1 del rediseño del robot. Verifica los 5 activos,
modos de negociación, desajustes temporales H1/M15, alternativas de símbolos
(que el usuario debe validar manualmente) y riesgo del lote mínimo.

No contiene order_send, no modifica Market Watch, órdenes ni posiciones.

Uso: python mt5_v2_preflight_seguro.py
Opcional: python mt5_v2_preflight_seguro.py --riesgo 0.005
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SYMBOLS = ("DE40", "US500", "US30", "XAUUSD", "EURUSD")
MODE = {0: "DISABLED", 1: "LONG_ONLY", 2: "SHORT_ONLY", 3: "CLOSE_ONLY", 4: "FULL"}
ALIAS_WORDS = {
    "DE40": ("de40", "ger40", "dax40", "dax 40", "germany 40", "german 40", "germany40"),
    "US500": ("us500", "sp500", "spx500", "s&p 500", "s&p500", "us spx 500", "usa500"),
    "US30": ("us30", "dow jones", "wall street 30", "wallstreet30", "dj30", "dow30"),
}


def utc_epoch(epoch):
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat() if epoch is not None else None


def fetch_bars(mt5, sym: str, timeframe: int, count: int, start: int = 0):
    rows = mt5.copy_rates_from_pos(sym, timeframe, start, count)
    if rows is None or len(rows) < count:
        return None, str(mt5.last_error())
    return rows, None


def atr_closed(mt5, sym):
    # A diferencia del bot original, omite la vela 0 aún en formación.
    rows, err = fetch_bars(mt5, sym, mt5.TIMEFRAME_M15, 100, 1)
    if rows is None:
        return None, err
    previous = None
    trs = []
    for row in rows:
        high, low, close = float(row["high"]), float(row["low"]), float(row["close"])
        tr = high - low if previous is None else max(high-low, abs(high-previous), abs(low-previous))
        trs.append(tr)
        previous = close
    if len(trs) < 15:
        return None, "Muy pocas velas cerradas"
    atr = sum(trs[-14:]) / 14
    return atr if atr > 0 else None, None if atr > 0 else "ATR no positivo"


def floor_volume(raw: float, vmin: float, vmax: float, step: float):
    if not all(math.isfinite(v) for v in (raw, vmin, vmax, step)) or step <= 0 or vmin <= 0:
        return None
    if raw < vmin - 1e-10:
        return None  # Es indispensable RECHAZAR, no forzar volume_min.
    steps = max(0, math.floor((min(raw, vmax) - vmin) / step + 1e-8))
    return round(vmin + steps * step, 8)


def estimate_risk(mt5, symbol, info, tick, atr, risk_fraction, account):
    if atr is None or not math.isfinite(atr) or atr <= 0:
        return {"error": "ATR M15 cerrado no disponible"}
    if info.trade_mode not in (mt5.SYMBOL_TRADE_MODE_LONGONLY, mt5.SYMBOL_TRADE_MODE_FULL):
        return {"error": "Símbolo no disponible para abrir COMPRAS"}
    entry = float(tick.ask)
    sl = entry - 1.2 * atr
    minimum = float(info.volume_min)
    money = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, symbol, minimum, entry, sl)
    if money is None or money >= 0:
        return {"error": "order_calc_profit no permite estimar la pérdida", "last_error": str(mt5.last_error())}
    budget = float(account.equity) * risk_fraction
    min_loss = abs(float(money))
    estimate = {
        "cuenta_divisa": str(account.currency), "fraccion_riesgo": risk_fraction,
        "presupuesto_perdida": round(budget, 2), "atr_m15_cerrado": round(atr, 8),
        "sl_distancia_precio_ejemplo": round(1.2 * atr, 8),
        "volumen_minimo": minimum, "perdida_min_lote_estimada": round(min_loss, 2),
        "nota": "Estimación a SL sin comisiones, swaps ni deslizamientos. No se envían órdenes."
    }
    raw = minimum * budget / min_loss
    volume = floor_volume(raw, minimum, float(info.volume_max), float(info.volume_step))
    if volume is None:
        estimate["volumen_compatible_con_riesgo"] = None
        estimate["motivo"] = "El lote mínimo supera el presupuesto de riesgo"
        return estimate
    # Confirma el riesgo con la API y nunca eleva el volumen hasta el mínimo.
    while volume is not None:
        result = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, symbol, volume, entry, sl)
        if result is None:
            estimate["error"] = "Fallo al validar el riesgo de volumen calculado"
            estimate["last_error"] = str(mt5.last_error())
            return estimate
        loss = abs(float(result))
        if loss <= budget + 1e-6:
            estimate["volumen_compatible_con_riesgo"] = volume
            estimate["perdida_estimacion_al_stop"] = round(loss, 2)
            return estimate
        volume = floor_volume(volume - float(info.volume_step), minimum,
                              float(info.volume_max), float(info.volume_step))
    estimate["volumen_compatible_con_riesgo"] = None
    estimate["motivo"] = "Ningún volumen autorizado encaja con el riesgo"
    return estimate


def inspect_asset(mt5, sym, now, account, risk_fraction):
    row = {"symbol": sym}
    info = mt5.symbol_info(sym)
    if info is None:
        return dict(row, error="Símbolo inexistente para esta cuenta", last_error=str(mt5.last_error()))
    row["trade_mode"] = MODE.get(int(info.trade_mode), str(info.trade_mode))
    row["puede_comprar_por_trade_mode"] = bool(int(info.trade_mode) in (1, 4))
    row["puede_vender_por_trade_mode"] = bool(int(info.trade_mode) in (2, 4))
    row["visible"] = bool(info.visible)
    tick = mt5.symbol_info_tick(sym)
    if tick is None or float(tick.bid) <= 0 or float(tick.ask) <= 0:
        return dict(row, error="Sin cotización BID/ASK utilizable")
    row["precio_bid"] = float(tick.bid)
    row["precio_ask"] = float(tick.ask)
    row["spread_precio"] = round(float(tick.ask - tick.bid), 8)
    row["tick_epoch"] = int(tick.time)
    row["tick_hora_si_utc"] = utc_epoch(int(tick.time))
    row["desfase_tick_vs_reloj_s"] = round(int(tick.time) - now, 2)
    row["advertencia_hora"] = ("Timestamps incompatibles con UTC del sistema; no convertir manualmente "
                                "hasta confirmar el origen del desplazamiento") if abs(int(tick.time) - now) > 300 else None
    row["velas"] = {}
    for label, tf, seconds in (("H1", mt5.TIMEFRAME_H1, 3600), ("M15", mt5.TIMEFRAME_M15, 900)):
        bars, err = fetch_bars(mt5, sym, tf, 3, 0)
        if bars is None:
            row["velas"][label] = {"error": err}
            continue
        last = int(bars[-1]["time"])
        diff = int(tick.time) - last
        # El control RELATIVO usa la misma escala que el feed del bróker.
        row["velas"][label] = {
            "ultima_barra_actual_epoch": last,
            "ultima_barra_actual_si_utc": utc_epoch(last),
            "segundos_tick_menos_apertura_barra_actual": diff,
            "cronologia_compatible": bool(-120 <= diff <= seconds + 300),
            "ultima_barra_cerrada_epoch": int(bars[-2]["time"]),
        }
    h1 = row["velas"].get("H1", {})
    m15 = row["velas"].get("M15", {})
    row["datos_temporales_coherentes"] = bool(h1.get("cronologia_compatible") and m15.get("cronologia_compatible"))
    atr, err = atr_closed(mt5, sym)
    row["riesgo_compra_ejemplo"] = (estimate_risk(mt5, sym, info, tick, atr, risk_fraction, account)
                                    if row["datos_temporales_coherentes"] else
                                    {"error": "No se calcula riesgo operativo con series H1/M15 incoherentes"})
    if err:
        row["error_atr"] = err
    row["apto_para_estudiar_estrategia"] = bool(
        row["datos_temporales_coherentes"]
        and row["puede_comprar_por_trade_mode"]
        and abs(row["desfase_tick_vs_reloj_s"]) <= 300
    )
    # Nota: apto PARA ESTUDIAR, nunca equivalente a candidato de trading.
    return row


def find_possible_aliases(mt5):
    all_symbols = mt5.symbols_get()
    if all_symbols is None:
        return {"error": str(mt5.last_error())}
    found = {}
    for primary, words in ALIAS_WORDS.items():
        matches = []
        for item in all_symbols:
            hay = f"{item.name} {getattr(item, 'description', '')}".lower()
            if any(w in hay for w in words):
                matches.append({
                    "nombre": str(item.name),
                    "descripcion": str(getattr(item, 'description', '')),
                    "trade_mode": MODE.get(int(item.trade_mode), str(item.trade_mode)),
                    "visible": bool(item.visible),
                })
        # Preferir símbolos FULL, pero NO seleccionarlos automáticamente.
        matches.sort(key=lambda r: (r["trade_mode"] != "FULL", r["nombre"]))
        found[primary] = matches[:40]
    return found


def main():
    parser = argparse.ArgumentParser(description="Preflight seguro MT5 (sin órdenes)")
    parser.add_argument("--riesgo", type=float, default=0.005,
                        help="Fracción de equity usada sólo para estimar pérdida (por defecto 0.005 = 0,5%%)")
    args = parser.parse_args()
    if not math.isfinite(args.riesgo) or not (0 < args.riesgo <= 0.01):
        parser.error("--riesgo debe estar entre 0 y 0.01 (máximo 1%% para estimación)")
    try:
        import MetaTrader5 as mt5
    except ImportError:
        raise SystemExit("Instala MetaTrader5 en el mismo entorno Python de tu robot")
    if not mt5.initialize():
        raise SystemExit(f"No se ha podido inicializar MT5: {mt5.last_error()}")
    try:
        account, terminal = mt5.account_info(), mt5.terminal_info()
        if account is None or terminal is None:
            raise SystemExit("No se pueden leer los permisos de cuenta/terminal")
        if int(account.trade_mode) != int(mt5.ACCOUNT_TRADE_MODE_DEMO):
            raise SystemExit("Por seguridad, este preflight sólo se ejecuta conectado a cuenta DEMO")
        now = time.time()
        output = {
            "script": "MT5 v2 preflight seguro, solo lectura",
            "hora_utc_pc": datetime.now(timezone.utc).isoformat(),
            "cuenta_demo": True,
            "trading_cuenta_permitido": bool(account.trade_allowed),
            "trading_terminal_permitido": bool(terminal.trade_allowed),
            "api_trading_deshabilitada": bool(terminal.tradeapi_disabled),
            "riesgo_ejemplo": args.riesgo,
            "sin_operaciones": True,
            "mercados": [inspect_asset(mt5, sym, now, account, args.riesgo) for sym in SYMBOLS],
            "posibles_simbolos_alternativos": find_possible_aliases(mt5),
        }
    finally:
        mt5.shutdown()
    destination = Path(__file__).with_name("mt5_v2_preflight_resultado.json")
    destination.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print("PREFLIGHT MT5 V2 — SOLO LECTURA. No envía órdenes.")
    for item in output["mercados"]:
        v = item.get("velas", {})
        age = v.get("H1", {}).get("segundos_tick_menos_apertura_barra_actual")
        reason = item.get("riesgo_compra_ejemplo", {})
        print(f"{item['symbol']:<7} {item.get('trade_mode', 'ERROR'):<12} "
              f"H1 actual vs tick={age if age is not None else 'N/D'}s "
              f"coherente={item.get('datos_temporales_coherentes', False)} "
              f"min_lote_riesgo={reason.get('perdida_min_lote_estimada', 'N/D')} "
              f"volumen_ejemplo={reason.get('volumen_compatible_con_riesgo')}")
    print("Alternativas a revisar manualmente para los índices (sin cambiarlas automáticamente):")
    aliases = output.get("posibles_simbolos_alternativos", {})
    for index in ALIAS_WORDS:
        found = [a for a in aliases.get(index, []) if a["trade_mode"] == "FULL"]
        print(f"  {index}: " + (", ".join(a["nombre"] for a in found[:12]) or "ninguna FULL encontrada"))
    print(f"Informe completo: {destination}")


if __name__ == "__main__":
    main()
