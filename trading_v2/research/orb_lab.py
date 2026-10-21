"""Investigacion ORB M5 (15/30m), validacion temporal y ejecucion BID/ASK OFFLINE.

No importa MetaTrader5 ni envia ordenes. El entrenamiento inicial consiste en
seleccionar modelos/parametros EXCLUSIVAMENTE en las ventanas pasadas y dos
bloques de validacion, nunca en el holdout final. ML vendra despues de
obtener muestras suficientes y confirmar una ventaja neta.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from io import BytesIO
from pathlib import Path
import json
import zipfile
import math
import numpy as np
import pandas as pd

from trading_v2.strategies.orb import ORBConfig,SESSIONS,validate_m5,generate_orb_signals
from scripts.investigar_admirals_v2 import metrics


SYMBOLS={"DAX40":("GERMANY40",.01),"SP500":("[SP500]",.01),
         "NASDAQ100":("US100",.01),"DOW30":("[DJI30]",.01)}
RANGE_MINUTES=(15,30)
ENTRY_MODES=("breakout","retest")
TP_ATR=(1.0,1.5)
HOLD_BARS=18  # 90 minutos maximo; no se mantienen posiciones overnight


@dataclass(frozen=True)
class ORBLabConfig:
    equity:float=3000.0
    risk_fraction:float=.0025
    stop_atr:float=1.0
    slippage_spread_fraction:float=.5
    min_validation_trades:int=10
    min_test_trades:int=15
    min_pf:float=1.10
    min_expectancy_r:float=.02

    def __post_init__(self):
        if self.equity<=0 or not 0<self.risk_fraction<=.01:
            raise ValueError("Riesgo/capital fuera de limites")
        if self.stop_atr<=0 or self.slippage_spread_fraction<0:
            raise ValueError("STOP/slippage invalidos")
        if self.min_validation_trades<=0 or self.min_test_trades<=0:
            raise ValueError("Muestras minimas invalidas")


def read_m5(z:zipfile.ZipFile,market:str)->pd.DataFrame:
    data=z.read(f"ADMIRALS_{market}_M5.csv")
    df=pd.read_csv(BytesIO(data))
    df["Time"]=pd.to_datetime(df.Time,utc=True,errors="raise")
    df=df.set_index("Time")
    # Rechazo de datos dudosos: cero de spread en cualquier barra es inseguro
    return validate_m5(df)


def _intraday_event(b:pd.DataFrame,i:int,side:int,point:float,tp_atr:float,cfg:ORBLabConfig):
    """La señal se conoce al cierre i; entrada solo en apertura i+1.

    OHLC bid asumido: LONG entra ask, sale bid; SHORT entra bid, sale ask.
    Comision y swaps no incluidos: NO es resultado real negociable.
    """
    idx=b.index
    if i+1>=len(b) or idx[i+1]-idx[i]!=pd.Timedelta(minutes=5):
        return None
    sess=b["orb_session"].iloc[i]
    if pd.isna(sess):
        return None
    sess_limit=sess+pd.Timedelta(hours=6)  # cerrar antes de la tarde/cierre de cash
    if idx[i+1]>=sess_limit:
        return None
    atr=float(b["atr14"].iloc[i])
    if not np.isfinite(atr) or atr<=0:
        return None
    stopdist=cfg.stop_atr*atr
    entry_spr=float(b.Spread.iloc[i+1])*point
    entry_bid=float(b.Open.iloc[i+1])
    entry=entry_bid+(entry_spr if side==1 else 0)+side*cfg.slippage_spread_fraction*entry_spr
    stop=entry-side*stopdist
    target=entry+side*tp_atr*atr
    horizon_end=min(len(b)-1,i+HOLD_BARS)
    exit_price=None;reason="TIMEOUT";end_i=i+1
    for j in range(i+1,horizon_end+1):
        if j>i+1 and idx[j]-idx[j-1]!=pd.Timedelta(minutes=5):
            # Hueco imprevisto: salida en la primera apertura disponible.
            spr=float(b.Spread.iloc[j])*point
            ex=float(b.Open.iloc[j])+(spr if side==-1 else 0)
            exit_price=ex-side*spr*cfg.slippage_spread_fraction
            reason="DATA_GAP_EXIT";end_i=j
            break
        if idx[j]>=sess_limit:
            spr=float(b.Spread.iloc[j])*point
            ex=float(b.Open.iloc[j])+(spr if side==-1 else 0)
            exit_price=ex-side*spr*cfg.slippage_spread_fraction
            reason="SESSION_EXIT";end_i=j
            break
        spr=float(b.Spread.iloc[j])*point
        open_ex=float(b.Open.iloc[j])+(spr if side==-1 else 0)
        hi_ex=float(b.High.iloc[j])+(spr if side==-1 else 0)
        lo_ex=float(b.Low.iloc[j])+(spr if side==-1 else 0)
        slip=cfg.slippage_spread_fraction*spr
        gap_hit= (open_ex<=stop if side==1 else open_ex>=stop)
        if gap_hit:
            exit_price=open_ex-side*slip;reason="GAP_STOP";end_i=j;break
        stop_hit=(lo_ex<=stop if side==1 else hi_ex>=stop)
        tp_hit=(hi_ex>=target if side==1 else lo_ex<=target)
        if stop_hit or tp_hit:
            exit_price=(stop if stop_hit else target)-side*slip
            reason=("BOTH_ASSUME_STOP" if stop_hit and tp_hit else ("STOP" if stop_hit else "TARGET"))
            end_i=j
            break
        end_i=j
    if exit_price is None:
        spr=float(b.Spread.iloc[end_i])*point
        exit_price=float(b.Close.iloc[end_i])+(spr if side==-1 else 0)-side*spr*cfg.slippage_spread_fraction
    rr=side*(exit_price-entry)/stopdist
    return {"signal_i":i,"exit_i":end_i,"session":str(sess),
            "entry":str(idx[i+1]),"exit":str(idx[end_i]),
            "r":float(rr),"reason":reason,"side":"LONG" if side==1 else "SHORT"}


def trade_events(b:pd.DataFrame,point:float,tp_atr:float,cfg:ORBLabConfig):
    """Eventos sin solapamiento por mercado; no fuerza X trades por dia."""
    events=[];next_allowed=0
    for i in range(len(b)-1):
        side=int(b.signal.iloc[i])
        if side==0 or i<next_allowed:
            continue
        e=_intraday_event(b,i,side,point,tp_atr,cfg)
        if e is not None:
            events.append(e)
            next_allowed=e["exit_i"]+1
    return events


def event_metrics(events:list[dict],cfg:ORBLabConfig):
    balance=cfg.equity;ts=[]
    for ev in events:
        p=balance*cfg.risk_fraction*ev["r"]
        ts.append({"pnl":p,"r":ev["r"],"reason":ev["reason"]})
        balance+=p
    return metrics(ts,cfg.equity)


def _acceptable(m,cfg,n):
    return (m["trades"]>=n and m["profit_factor"] is not None
            and m["profit_factor"]>=cfg.min_pf
            and m["mean_r"] is not None and m["mean_r"]>=cfg.min_expectancy_r)


def split_sessions(b:pd.DataFrame,symbol:str):
    """Dividir por SESIONES COMPLETAS locales, evitando fugas de operaciones."""
    # Solo contar sesiones con ORB completo, no sabados/dom.
    active=b.loc[b.orb_ready,"orb_session"].dropna().unique()
    days=sorted(pd.to_datetime(active,utc=True))
    if len(days)<100:
        raise ValueError("Se necesitan >=100 sesiones ORB M5 completas por simbolo")
    n=len(days)
    f1=int(n*.50);f2=int(n*.65);f3=int(n*.80)
    if min(f2-f1,f3-f2,n-f3)<12:
        raise ValueError("No hay suficientes sesiones en cada particion")
    return set(days[f1:f2]),set(days[f2:f3]),set(days[f3:])


def analyze_market(m5:pd.DataFrame,symbol:str,point:float,cfg:ORBLabConfig=ORBLabConfig()):
    candidates=[]
    complete_sessions=None
    for minutes in RANGE_MINUTES:
        for mode in ENTRY_MODES:
            o=ORBConfig(symbol=symbol,range_minutes=minutes,mode=mode)
            signals=generate_orb_signals(m5,o,point)
            valid1,valid2,holdout=split_sessions(signals,symbol)
            if complete_sessions is None:
                complete_sessions=(valid1,valid2,holdout)
            for target in TP_ATR:
                events=trade_events(signals,point,target,cfg)
                f1=[e for e in events if pd.Timestamp(e["session"]) in valid1]
                f2=[e for e in events if pd.Timestamp(e["session"]) in valid2]
                # Evaluar SOLO los pliegues de validacion en seleccion.
                m1=event_metrics(f1,cfg);m2=event_metrics(f2,cfg)
                passes=_acceptable(m1,cfg,cfg.min_validation_trades) and _acceptable(m2,cfg,cfg.min_validation_trades)
                score=round(min(m1["mean_r"],m2["mean_r"])-.02*max(m1["max_drawdown_pct"],m2["max_drawdown_pct"]),6) if passes else None
                candidates.append({"range_minutes":minutes,"mode":mode,"target_atr":target,
                                   "signals":int((signals.signal!=0).sum()),
                                   "fold1":m1,"fold2":m2,"passes_two_folds":passes,"score":score})
    winners=[c for c in candidates if c["passes_two_folds"]]
    winner=max(winners,key=lambda x:x["score"]) if winners else None
    out={"strategy":"ORB_OPENING_RANGE","asset":symbol,"bars":len(m5),
         "tested_parameters":len(candidates),"candidates":candidates,
         "chosen":winner,"holdout":None,"decision":"NO_TRADE",
         "note":"Rentabilidad en R normalizada; sin comisiones/lotes reales ni tick backtesting"}
    if winner is None:
        out["reason"]="No hay configuracion que supere ambos pliegues de validacion"
        return out
    # Holdout final consultado UNA SOLA VEZ para el candidato ganador.
    o=ORBConfig(symbol=symbol,range_minutes=winner["range_minutes"],mode=winner["mode"])
    signals=generate_orb_signals(m5,o,point)
    events=trade_events(signals,point,winner["target_atr"],cfg)
    third=complete_sessions[2]
    tested=[e for e in events if pd.Timestamp(e["session"]) in third]
    out["holdout"]=event_metrics(tested,cfg)
    out["decision"]="FURTHER_RESEARCH_ONLY" if _acceptable(out["holdout"],cfg,cfg.min_test_trades) else "NO_TRADE"
    out["reason"]="No autoriza operativa; exige datos nuevos, costes, ticks y DEMO monitorizada"
    return out


def run_zip(zip_file:str|Path,cfg:ORBLabConfig=ORBLabConfig()):
    result={"study":"ORB 15/30min M5 (Admirals DEMO) - OFFLINE",
            "source":Path(zip_file).name,
            "approval":{"orders":False,"automatic_demo":False,"real":False},
            "cost_assumptions":{"ohlc":"BID","spread":"historical entry/exit",
             "slippage":"0.5 x spread adverse each leg","commission":"NOT MODELED",
             "swap":"NOT MODELED","lotage":"NOT MODELED","risk_fraction":cfg.risk_fraction},
            "selection":"two chronological validation folds 50-65%,65-80%; final holdout 80-100% only if passes both",
            "markets":{}}
    with zipfile.ZipFile(zip_file) as z:
        manifest=json.loads(z.read("orb_manifest.json"))
        acc=manifest["account"]
        if acc.get("demo") is not True or "admir" not in (acc.get("company","")+acc.get("server","")).lower() or acc.get("currency")!="EUR":
            raise ValueError("ZIP ORB requiere cuenta Admirals DEMO EUR")
        for market,record in manifest["markets"].items():
            if market not in SYMBOLS:
                continue
            if not record.get("file"):
                result["markets"][market]={"decision":"NO_TRADE","reason":"Faltan barras M5"}
                continue
            sym,point=SYMBOLS[market]
            data=read_m5(z,market)
            result["markets"][market]=analyze_market(data,sym,point,cfg)
    return result
