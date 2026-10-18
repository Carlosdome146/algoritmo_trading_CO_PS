#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Exporta histórico LARGO (D1 + H4) de Admirals DEMO en ZIP. SOLO LECTURA: NO opera.

Reutiliza las salvaguardas del exportador M15/H1 (cuenta DEMO + Admirals obligatoria)
y descarga el máximo de velas diarias y de 4 horas que tenga el terminal.
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.exportar_historial_admirals_mt5 import read_history  # noqa: E402

SYMBOLS_LONG = {
    "DAX40": "GERMANY40",
    "SP500": "[SP500]",
    "DOW30": "[DJI30]",
    "NASDAQ100": "US100",
    "NIKKEI225": "[JP225]",
    "GOLD": "GOLD",
    "EURUSD": "EURUSD",
}


def gather_long(mt5, d1_bars: int, h4_bars: int):
    a = mt5.account_info()
    if a is None:
        raise RuntimeError("Sin información de cuenta MT5")
    company = str(getattr(a, "company", "") or "")
    server = str(getattr(a, "server", "") or "")
    if getattr(a, "trade_mode", None) != mt5.ACCOUNT_TRADE_MODE_DEMO:
        raise RuntimeError("Cuenta NO DEMO. Por seguridad, exportación bloqueada")
    if "admir" not in (company + " " + server).lower():
        raise RuntimeError("Cuenta incorrecta: no se identifica como Admirals")
    report = {
        "type": "READ_ONLY_ADMIRALS_LONG_HISTORY_EXPORT",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "account": {
            "company": company, "server": server, "demo": True,
            "currency": str(getattr(a, "currency", "")),
            "leverage": int(getattr(a, "leverage", 0)),
            "balance": float(getattr(a, "balance", 0.0)),
        },
        "limitations": [
            "Velas D1/H4 del servidor Admirals: sin ticks intrabar",
            "Spread de barra indicativo; en tramos antiguos puede ser sintético/fijo",
            "Se excluye la vela en formación (posición 0)",
            "Ninguna orden enviada ni posición modificada",
        ],
        "symbols": {},
    }
    files = {}
    for market, symbol in SYMBOLS_LONG.items():
        meta = mt5.symbol_info(symbol)
        info = {"symbol": symbol, "market": market, "found": meta is not None, "frames": {}}
        if meta is None:
            report["symbols"][market] = info
            continue
        mt5.symbol_select(symbol, True)
        frames_to_fetch = []
        if d1_bars > 0:
            frames_to_fetch.append(("D1", mt5.TIMEFRAME_D1, d1_bars))
        if h4_bars > 0:
            frames_to_fetch.append(("H4", mt5.TIMEFRAME_H4, h4_bars))
        for label, tf, total in frames_to_fetch:
            content, stats = None, None
            req = total
            while req >= 500:
                content, stats = read_history(mt5, symbol, tf, label, req)
                if content is not None:
                    break
                req //= 2
            info["frames"][label] = stats
            if content is not None:
                fname = f"ADMIRALS_{market}_{label}.csv"
                files[fname] = content
                info["frames"][label]["csv_file"] = fname
        report["symbols"][market] = info
    return report, files


def main(argv=None):
    p = argparse.ArgumentParser(description="Exportación histórica larga D1/H4 Admirals DEMO (solo lectura)")
    p.add_argument("--terminal")
    p.add_argument("--d1-bars", type=int, default=3000)
    p.add_argument("--h4-bars", type=int, default=0)
    p.add_argument("--out", default="admirals_historial_largo_local.zip")
    args = p.parse_args(argv)
    import MetaTrader5 as mt5
    if not (mt5.initialize(path=args.terminal) if args.terminal else mt5.initialize()):
        p.exit(2, f"No se pudo iniciar MT5: {mt5.last_error()}\n")
    try:
        report, files = gather_long(mt5, args.d1_bars, args.h4_bars)
    except RuntimeError as exc:
        p.exit(2, f"BLOQUEADO: {exc}\n")
    finally:
        mt5.shutdown()
    dest = Path(args.out)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=7) as z:
        for fname, content in files.items():
            z.writestr(fname, content)
        z.writestr("admirals_manifest.json", json.dumps(report, ensure_ascii=False, indent=2))
    for market, info in report["symbols"].items():
        for tf, d in info["frames"].items():
            if d:
                print(f"{market:7s} {tf}: {d.get('received')} velas | {d.get('first_bar_utc_interpretation')} -> "
                      f"{d.get('last_bar_utc_interpretation')} | spread mediana {d.get('spread_median_positive_points')}")
    print("ZIP:", dest.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
