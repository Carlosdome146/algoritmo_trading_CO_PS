#!/usr/bin/env python3
"""Investiga M15 y M30 continuos, desde ZIP M5 existente, sin MT5/órdenes."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from trading_v2.research.continuous_intraday_lab import run_zip


def main(argv=None):
    p=argparse.ArgumentParser(description="Estudio offline intradia continuo M15/M30, NO ORB")
    p.add_argument("--zip",default="admirals_orb_m5_local.zip",
                   help="ZIP M5 Admirals DEMO ya exportado")
    p.add_argument("--out",default="intradia_m15_m30_local_result.json")
    args=p.parse_args(argv)
    res=run_zip(args.zip)
    Path(args.out).write_text(json.dumps(res,indent=2,ensure_ascii=False,
                                        allow_nan=False),encoding="utf-8")
    print("INTRADIA CONTINUO M15/M30: OFFLINE, SIN ORDENES.")
    for market,m in res["markets"].items():
        w=m.get("chosen")
        h=m.get("holdout")
        candidate=(f"{w['timeframe']} / {w['strategy']} / {w['horizon_minutes']}min "
                   f"/ ML {w['ml_threshold']}" if w else "ninguno")
        print(f"{market:10s} | {m['decision']:22s} | {candidate} | "
              f"test: {h.get('trades') if h else 'NO CONSULTADO'} trades")
    print("Informe:",Path(args.out).resolve())
    return 0


if __name__=="__main__":
    raise SystemExit(main())
