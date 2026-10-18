#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Exporta históricos de Admirals DEMO en ZIP. SOLO LECTURA: NO opera."""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import statistics
import zipfile
from datetime import datetime, timezone
from pathlib import Path

SYMBOLS = {
    "DAX40": "GERMANY40",
    "SP500": "[SP500]",
    "DOW30": "[DJI30]",
    "GOLD": "GOLD",
    "EURUSD": "EURUSD",
}


def utc_iso(epoch):
    try:
        return datetime.fromtimestamp(int(epoch), timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError, TypeError):
        return None


def read_history(mt5, symbol, timeframe, timeframe_name, count):
    # Índice 0 = barra actual/posiblemente en formación. Excluir por seguridad.
    rows = mt5.copy_rates_from_pos(symbol, timeframe, 1, count)
    if rows is None:
        return None, {"error": str(mt5.last_error()), "requested": count}
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(("Time", "Open", "High", "Low", "Close", "TickVolume", "Spread", "RealVolume"))
    n = 0
    prev = None
    duplications = 0
    reverse = 0
    invalid_prices = 0
    spreads = []
    spread_zeros = 0
    first_time = last_time = None
    for bar in rows:
        raw_time = int(bar["time"])
        if prev is not None:
            if raw_time == prev:
                duplications += 1
            if raw_time < prev:
                reverse += 1
        prev = raw_time
        if first_time is None:
            first_time = raw_time
        last_time = raw_time
        o, h, l, c = (float(bar[key]) for key in ("open", "high", "low", "close"))
        if not all(math.isfinite(x) and x > 0 for x in (o, h, l, c)) or h < max(o, c, l) or l > min(o, c):
            invalid_prices += 1
        spread = int(bar["spread"])
        if spread > 0:
            spreads.append(spread)
        elif spread == 0:
            spread_zeros += 1
        writer.writerow((
            datetime.fromtimestamp(raw_time, timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            o, h, l, c, int(bar["tick_volume"]), spread, int(bar["real_volume"]),
        ))
        n += 1
    stats = {
        "timeframe": timeframe_name, "requested": count, "received": n,
        "first_bar_utc_interpretation": utc_iso(first_time),
        "last_bar_utc_interpretation": utc_iso(last_time),
        "duplicates": duplications, "out_of_order": reverse, "invalid_ohlc": invalid_prices,
        "spread_zero_bars": spread_zeros, "spread_positive_bars": len(spreads),
        "spread_median_positive_points": statistics.median(spreads) if spreads else None,
        "spread_min_positive_points": min(spreads) if spreads else None,
        "spread_max_positive_points": max(spreads) if spreads else None,
        "warnings": [],
    }
    if n < 500:
        stats["warnings"].append("Menos de 500 velas; insuficiente para entrenamiento fiable")
    if n < count:
        stats["warnings"].append("El terminal devolvió menos barras: revisar Máx. barras en gráfico y disponibilidad")
    if invalid_prices or duplications or reverse:
        stats["warnings"].append("Histórico con anomalías: NO entrenar hasta resolverlas")
    if n and spread_zeros / n >= .5:
        stats["warnings"].append("Muchos spreads históricos 0: NO interpretarlos como operaciones sin coste")
    return out.getvalue(), stats


def gather(mt5, m15_bars, h1_bars):
    a = mt5.account_info()
    if a is None:
        raise RuntimeError("Sin información de cuenta MT5")
    company = str(getattr(a, "company", "") or "")
    server = str(getattr(a, "server", "") or "")
    if getattr(a, "trade_mode", None) != mt5.ACCOUNT_TRADE_MODE_DEMO:
        raise RuntimeError("Cuenta NO DEMO. Por seguridad, exportación bloqueada")
    if "admir" not in (company + " " + server).lower():
        raise RuntimeError("Cuenta incorrecta: no se identifica como Admirals (posible MetaQuotes)")
    report = {
        "type": "READ_ONLY_ADMIRALS_HISTORICAL_EXPORT",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "account": {
            "company": company, "server": server, "demo": True,
            "currency": str(getattr(a, "currency", "")),
            "leverage": int(getattr(a, "leverage", 0)),
            "balance": float(getattr(a, "balance", 0.)),
        },
        "limitations": [
            "Solo velas históricas MT5: sin ticks intrabar para saber el orden TP/SL",
            "Hora convertida desde epoch MT5 a UTC; offset del broker sin corregir",
            "Spread de barra indicativo: NO incluye comisión, slippage real ni swaps",
            "La cotización actual podría estar desactualizada durante el fin de semana",
            "Se excluye posición 0 (barra vigente o última del servidor)",
            "Ninguna orden enviada ni posición modificada",
        ],
        "symbols": {},
    }
    files = {}
    for market, symbol in SYMBOLS.items():
        meta = mt5.symbol_info(symbol)
        info = {"symbol": symbol, "market": market, "found": meta is not None, "frames": {}}
        if meta is None:
            info["warning"] = "Símbolo no disponible. Comprueba conexión y Observación del mercado"
            report["symbols"][market] = info
            continue
        info.update({
            "visible": bool(getattr(meta, "visible", False)),
            "trade_mode": int(getattr(meta, "trade_mode", -1)),
            "min_lot": float(getattr(meta, "volume_min", 0)),
            "lot_step": float(getattr(meta, "volume_step", 0)),
            "point": float(getattr(meta, "point", 0)),
            "tick_size": float(getattr(meta, "trade_tick_size", 0)),
            "contract_size": float(getattr(meta, "trade_contract_size", 0)),
            "currency_profit": str(getattr(meta, "currency_profit", "")),
            "path": str(getattr(meta, "path", "")),
        })
        tick = mt5.symbol_info_tick(symbol)
        if tick is not None and getattr(tick, "time", 0):
            info["last_tick_utc_interpretation"] = utc_iso(tick.time)
            info["last_tick_age_seconds_at_export"] = int(
                datetime.now(timezone.utc).timestamp() - tick.time
            )
        for label, tf, total in (
            ("M15", mt5.TIMEFRAME_M15, m15_bars),
            ("H1", mt5.TIMEFRAME_H1, h1_bars),
        ):
            content, stats = read_history(mt5, symbol, tf, label, total)
            info["frames"][label] = stats
            if content is not None:
                filename = f"ADMIRALS_{market}_{label}.csv"
                files[filename] = content
                info["frames"][label]["csv_file"] = filename
        report["symbols"][market] = info
    return report, files


def main(argv=None):
    p = argparse.ArgumentParser(description="Exportación histórica MT5 Admirals DEMO, solo lectura")
    p.add_argument("--terminal", help="Ruta a terminal64.exe Admirals si hay varios MT5")
    p.add_argument("--m15-bars", type=int, default=50000, help="Barras M15 a solicitar (defecto: 50.000+)")
    p.add_argument("--h1-bars", type=int, default=15000, help="Barras H1 a solicitar (defecto: 15.000+)")
    p.add_argument("--out", default="admirals_historial_local.zip")
    args = p.parse_args(argv)
    if not 500 <= args.m15_bars <= 100000 or not 500 <= args.h1_bars <= 100000:
        p.error("Solicita entre 500 y 100000 velas por marco temporal")
    try:
        import MetaTrader5 as mt5
    except ImportError:
        p.exit(2, "Instala MetaTrader5: python -m pip install MetaTrader5\n")
    if not (mt5.initialize(path=args.terminal) if args.terminal else mt5.initialize()):
        p.exit(2, f"No se pudo iniciar MT5: {mt5.last_error()}\n")
    try:
        report, files = gather(mt5, args.m15_bars, args.h1_bars)
    except RuntimeError as exc:
        p.exit(2, f"BLOQUEADO: {exc}\n")
    finally:
        mt5.shutdown()
    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=7) as archive:
        for filename, content in files.items():
            archive.writestr(filename, content)
        archive.writestr("admirals_manifest.json", json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Cuenta DEMO: {report['account']['company']} / {report['account']['server']} / "
          f"{report['account']['balance']} {report['account']['currency']} / 1:{report['account']['leverage']}")
    for market, info in report["symbols"].items():
        fs = info["frames"]
        print(market, info["symbol"], " | ".join(
            f"{tf}: {d.get('received', 0)} velas, spread mediana positiva {d.get('spread_median_positive_points')} puntos"
            for tf, d in fs.items()
        ))
    print("ZIP:", dest.resolve())
    print("SOLO LECTURA. Comparte el ZIP en este chat; NO lo subas al repositorio público.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
