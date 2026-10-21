#!/usr/bin/env python3
"""Exportador M5 de indices para estudio ORB: Admirals DEMO, SOLO LECTURA.

No usa order_send, order_check ni modifica posiciones. Habilita en Market Watch
los simbolos requeridos con symbol_select; puede cambiar su visibilidad.
Se excluye la vela M5 en formación. El ZIP local no debe subirse a GitHub.
"""
from __future__ import annotations
import argparse
import json
import sys
import zipfile
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.exportar_historial_admirals_mt5 import read_history

MARKETS={"DAX40":"GERMANY40","SP500":"[SP500]","NASDAQ100":"US100","DOW30":"[DJI30]"}


def gather_orb(mt5, markets:tuple[str,...], bars:int):
    acc=mt5.account_info()
    if acc is None or getattr(acc,"trade_mode",None)!=mt5.ACCOUNT_TRADE_MODE_DEMO:
        raise RuntimeError("Cuenta ausente o NO DEMO: exportacion bloqueada")
    company=str(getattr(acc,"company","") or "")
    server=str(getattr(acc,"server","") or "")
    if "admir" not in (company+" "+server).lower():
        raise RuntimeError("Debe usar cuenta Admirals DEMO")
    manifest={
        "study":"ORB_M5_READ_ONLY_ADMIRALS_DEMO",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "account":{"demo":True,"company":company,"server":server,
                   "currency":str(getattr(acc,"currency",""))},
        "markets":{},
        "limitations":["M5 OHLC no prueba orden intrabar de TP/SL",
                       "Spread de barra puede no reflejar ask de ejecucion",
                       "No contiene ticks ni liquidaciones ni comisiones",
                       "No se ha enviado ninguna orden"],
    }
    files={}
    for market in markets:
        symbol=MARKETS[market]
        record={"symbol":symbol,"data":None}
        if mt5.symbol_info(symbol) is None:
            record["error"]="Simbolo no encontrado"
        elif not mt5.symbol_select(symbol,True):
            record["error"]="No fue posible habilitarlo en Market Watch"
        else:
            csv_data,stat=read_history(mt5,symbol,mt5.TIMEFRAME_M5,"M5",bars)
            record["data"]=stat
            if csv_data is not None:
                filename=f"ADMIRALS_{market}_M5.csv"
                files[filename]=csv_data
                record["file"]=filename
        manifest["markets"][market]=record
    return manifest,files


def main(argv=None):
    p=argparse.ArgumentParser(description="Exportar M5 ORB Admirals DEMO, solo lectura")
    p.add_argument("--terminal",help="Ruta terminal64.exe si hay varios MT5")
    p.add_argument("--bars",type=int,default=80000,help="M5 cerradas por activo (5000..100000)")
    p.add_argument("--markets",nargs="+",choices=list(MARKETS),default=["DAX40","SP500","NASDAQ100","DOW30"])
    p.add_argument("--out",default="admirals_orb_m5_local.zip")
    a=p.parse_args(argv)
    if not 5000<=a.bars<=100000:
        p.error("--bars debe estar entre 5000 y 100000")
    import MetaTrader5 as mt5
    if not (mt5.initialize(path=a.terminal) if a.terminal else mt5.initialize()):
        p.exit(2,f"Sin conexion MT5: {mt5.last_error()}\n")
    try:
        manifest,files=gather_orb(mt5,tuple(dict.fromkeys(a.markets)),a.bars)
    finally:
        mt5.shutdown()
    dest=Path(a.out)
    with zipfile.ZipFile(dest,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,blob in files.items():
            z.writestr(name,blob)
        z.writestr("orb_manifest.json",json.dumps(manifest,indent=2,ensure_ascii=False))
    for name,info in manifest["markets"].items():
        d=info.get("data") or {}
        print(name,":",d.get("received",0),"M5 |",d.get("first_bar_utc_interpretation"),"->",
              d.get("last_bar_utc_interpretation"),"|",info.get("error",""))
    print("Historicos ORB:",dest.resolve())
    if not files:
        p.exit(2,"No se exporto ningun mercado\n")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
