#!/usr/bin/env python3
"""Ejecutar investigacion ORB 15/30 M5 OFFLINE - no envia ordenes."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from trading_v2.research.orb_lab import run_zip


def main(argv=None):
    p=argparse.ArgumentParser(description="ORB M5 15/30min, investigacion offline Admirals DEMO")
    p.add_argument("--zip",default="admirals_orb_m5_local.zip")
    p.add_argument("--out",default="orb_m5_research_local_result.json")
    a=p.parse_args(argv)
    result=run_zip(a.zip)
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    print("ORB M5: SIN CONEXION MT5; SIN ORDENES.")
    for market, r in result["markets"].items():
        win=r.get("chosen")
        test=r.get("holdout") or {}
        print(market,r["decision"],
              "ORB",win["range_minutes"] if win else "none",
              "tipo",win["mode"] if win else "none",
              "ops_test",test.get("trades"),"PF",test.get("profit_factor"))
    print("Resultados:",Path(a.out).resolve())


if __name__=="__main__":
    main()
