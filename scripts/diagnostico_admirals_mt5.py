#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Admirals MT5: inspección SOLO LECTURA. No envía órdenes ni modifica Market Watch.

python scripts/diagnostico_admirals_mt5.py
python scripts/diagnostico_admirals_mt5.py --terminal "C:\ruta\terminal64.exe"

No guarda login, titular, contraseñas, tokens ni rutas locales.
"""
from __future__ import annotations
import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

MARKETS = {
    "DAX40": (("DE40", "GER40", "DAX40", "GERMANY40", "DAX"), ("germany 40", "german 40", "dax 40")),
    "SP500": (("US500", "SP500", "SPX500", "USA500", "SPX"), ("s&p 500", "sp 500", "us 500")),
    "DOW30": (("US30", "DJI30", "DJ30", "DOW30", "WALLSTREET30", "DJI"), ("dow jones", "wall street 30")),
    "GOLD": (("XAUUSD", "GOLD", "XAUUSDPRO"), ("gold vs us dollar", "gold spot")),
    "EURUSD": (("EURUSD", "EURUSDPRO"), ("euro vs us dollar", "euro / us dollar")),
}
MODES = {0: "DISABLED", 1: "LONG_ONLY", 2: "SHORT_ONLY", 3: "CLOSE_ONLY", 4: "FULL"}

def number(x):
    if isinstance(x, (int, float)) and math.isfinite(float(x)):
        return x
    return None

def match(info, market):
    aliases, phrases = MARKETS[market]
    name = "".join(c for c in str(info.name).upper() if c.isalnum())
    desc = str(getattr(info, "description", "") or "").lower()
    path = str(getattr(info, "path", "") or "").lower()
    if any(x in (desc + " " + path) for x in ("etf", "exchange traded", "shares", "equity stock")):
        return 0, "ETF/acción; no sustituir por CFD"
    norm_aliases = ["".join(c for c in a.upper() if c.isalnum()) for a in aliases]
    if name in norm_aliases:
        return 100, "Nombre exacto; revisar contrato"
    if any(name.startswith(a) and len(name) <= len(a) + 5 for a in norm_aliases):
        return 75, "Posible sufijo del bróker; revisar contrato"
    if any(x in desc for x in phrases):
        return 50, "Descripción aproximada; revisar contrato"
    return 0, ""

def describe(mt5, info, score, match_reason):
    point = number(getattr(info, "point", None))
    tick = mt5.symbol_info_tick(info.name)
    bid = number(getattr(tick, "bid", None)) if tick else None
    ask = number(getattr(tick, "ask", None)) if tick else None
    epoch = number(getattr(tick, "time", None)) if tick else None
    mode = int(getattr(info, "trade_mode", -1))
    return {
        "symbol": info.name, "description": str(getattr(info, "description", "")),
        "path": str(getattr(info, "path", "")),
        "match_score": score, "match_reason": match_reason,
        "visible": bool(getattr(info, "visible", False)),
        "trade_mode": MODES.get(mode, f"UNKNOWN({mode})"),
        "buys_allowed_by_mode": mode in (1, 4),
        "sells_allowed_by_mode": mode in (2, 4),
        "point": point, "digits": number(getattr(info, "digits", None)),
        "tick_size": number(getattr(info, "trade_tick_size", None)),
        "tick_value_reported": number(getattr(info, "trade_tick_value", None)),
        "contract_size": number(getattr(info, "trade_contract_size", None)),
        "profit_currency": str(getattr(info, "currency_profit", "")),
        "margin_currency": str(getattr(info, "currency_margin", "")),
        "lot_min": number(getattr(info, "volume_min", None)),
        "lot_step": number(getattr(info, "volume_step", None)),
        "lot_max": number(getattr(info, "volume_max", None)),
        "stops_level_points": number(getattr(info, "trade_stops_level", None)),
        "freeze_level_points": number(getattr(info, "trade_freeze_level", None)),
        "calc_mode": number(getattr(info, "trade_calc_mode", None)),
        "swap_long": number(getattr(info, "swap_long", None)),
        "swap_short": number(getattr(info, "swap_short", None)),
        "swap_mode": number(getattr(info, "swap_mode", None)),
        "bid": bid, "ask": ask,
        "spread_points_reported": number(getattr(info, "spread", None)),
        "spread_points_tick": round((ask-bid)/point, 2) if point and ask is not None and bid is not None and ask >= bid else None,
        "tick_epoch_raw": epoch,
        "tick_utc_if_unix": datetime.fromtimestamp(epoch,timezone.utc).isoformat() if epoch else None,
        "tick_minus_pc_utc_seconds": round(epoch - datetime.now(timezone.utc).timestamp(),2) if epoch else None,
        "caveat": "Spread instantáneo; comisiones, sesiones y otros costes requieren tarifario y confirmación de entidad."
    }

def main():
    p=argparse.ArgumentParser(description="Inspección DEMO Admirals MT5: solo lectura")
    p.add_argument("--terminal",default=None,help="Ruta a terminal64.exe si hay varios MT5 instalados")
    p.add_argument("--out",default="diagnostico_admirals_local_result.json")
    args=p.parse_args()
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("Instala MetaTrader5: python -m pip install MetaTrader5")
        return 2
    if not (mt5.initialize(path=args.terminal) if args.terminal else mt5.initialize()):
        print("Error MT5:",mt5.last_error())
        return 2
    try:
        a=mt5.account_info()
        t=mt5.terminal_info()
        if a is None or t is None:
            print("Error consultando cuenta y terminal:",mt5.last_error())
            return 2
        company=str(getattr(a,"company","") or "")
        server=str(getattr(a,"server","") or "")
        is_demo=int(getattr(a,"trade_mode",-1))==mt5.ACCOUNT_TRADE_MODE_DEMO
        if not is_demo:
            print("BLOQUEADO: la cuenta actual NO es DEMO.")
            return 3
        if "admir" not in (company+" "+server).lower():
            print("BLOQUEADO: Python no está conectado a Admirals:",company,server)
            print("Cierra el otro terminal MT5 o indica --terminal ruta_al_terminal_admirals.exe")
            return 3
        symbols=mt5.symbols_get()
        if symbols is None:
            print("Error symbols_get:",mt5.last_error())
            return 2
        report={
            "type":"READ_ONLY_MT5_DIAGNOSTIC", "created_utc":datetime.now(timezone.utc).isoformat(),
            "account":{"company":company, "server":server, "demo":True,
                       "currency":str(getattr(a,"currency","")), "leverage":number(getattr(a,"leverage",None)),
                       "balance":number(getattr(a,"balance",None)),
                       "trading_account_allowed":bool(getattr(a,"trade_allowed",False)),
                       "trading_terminal_allowed":bool(getattr(t,"trade_allowed",False)),
                       "tradeapi_disabled":bool(getattr(t,"tradeapi_disabled",False))},
            "market_candidates":{},
            "warnings":["Nunca se han enviado órdenes.", "Los candidatos deben verificarse en MT5 manualmente.",
                        "FULL no implica mercado abierto ahora mismo.",
                        "Comisiones y tarifas no pueden inferirse de estos campos.",
                        "No incluye número de cuenta ni datos personales."]
        }
        print(f"MT5: {company} | {server} | DEMO | {a.currency} | 1:{a.leverage}")
        for market in MARKETS:
            ranked=[]
            for s in symbols:
                score,why=match(s,market)
                if score:
                    ranked.append((score,bool(getattr(s,"visible",False)),s,why))
            ranked.sort(key=lambda v:(v[0],v[1]),reverse=True)
            entries=[describe(mt5,s,score,why) for score,_,s,why in ranked[:8]]
            report["market_candidates"][market]=entries
            print(f"{market}: {len(ranked)} candidato(s)")
            for e in entries[:3]:
                print(f"  {e['symbol']:<16} {e['trade_mode']:<10} "
                      f"spread={e['spread_points_tick']} puntos | minimo={e['lot_min']} | step={e['lot_step']}")
        out=Path(args.out)
        out.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
        print("JSON guardado en:",out.resolve())
        print("SOLO LECTURA: ninguna orden enviada, ninguna posición modificada.")
        return 0
    finally:
        mt5.shutdown()

if __name__=="__main__":
    raise SystemExit(main())
