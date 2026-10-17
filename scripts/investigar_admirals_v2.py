#!/usr/bin/env python3
"""Estudio multi-mercado MT5 OFFLINE: nunca conecta al terminal ni emite órdenes.

Entrada ZIP exportada por scripts/exportar_historial_admirals_mt5.py
Salida JSON reproducible. Costes: precios OHLC MT5 interpretados como BID,
spread histórico al abrir/cerrar, deslizamiento de escenario; NO incluye
comisiones y swaps (bróker/entidad/tipo de cuenta pendientes de confirmar).
"""
from __future__ import annotations
import argparse
from collections import Counter
from dataclasses import dataclass
from io import BytesIO
import json
import math
from pathlib import Path
import zipfile
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

SYMBOLS = {"DAX40": ("GERMANY40", .01), "SP500": ("[SP500]", .01),
           "DOW30": ("[DJI30]", .01), "GOLD": ("GOLD", .01),
           "EURUSD": ("EURUSD", .00001)}
HORIZONS = (4, 16, 32)
THRESHOLDS = (None, .35, .45, .55)
FEATURES = ("ema_gap_atr", "close_ema_atr", "rsi", "atr_ratio", "atr_pct", "direction", "ret3")

@dataclass(frozen=True)
class Params:
    equity: float = 3000.0
    risk_fraction: float = .0025
    sl_atr: float = 1.2
    tp_atr: float = 1.8
    train_fraction: float = .60
    validation_fraction: float = .20
    embargo_bars: int = 40
    min_training_examples: int = 80
    min_validation_trades: int = 30
    min_final_trades: int = 30
    min_pf: float = 1.10
    min_expectancy_r: float = .02


def load_data(z: zipfile.ZipFile, market: str):
    data = {}
    for tf in ("M15", "H1"):
        filename = f"ADMIRALS_{market}_{tf}.csv"
        f = pd.read_csv(BytesIO(z.read(filename)))
        if not {"Time", "Open", "High", "Low", "Close", "Spread"}.issubset(f):
            raise ValueError(f"{filename}: faltan columnas")
        f["Time"] = pd.to_datetime(f["Time"], utc=True, errors="raise")
        f = f.set_index("Time")
        for col in ("Open", "High", "Low", "Close", "Spread"):
            f[col] = pd.to_numeric(f[col], errors="raise")
        if len(f) < 2000 or f.index.has_duplicates or not f.index.is_monotonic_increasing:
            raise ValueError(f"{filename}: histórico insuficiente o fechas inválidas")
        if (f[["Open", "High", "Low", "Close"]] <= 0).any().any():
            raise ValueError(f"{filename}: precios no positivos")
        if ((f.High < f[["Open", "Close", "Low"]].max(axis=1)) |
            (f.Low > f[["Open", "Close"]].min(axis=1))).any():
            raise ValueError(f"{filename}: OHLC inconsistente")
        if (f.Spread < 0).any() or (f.Spread == 0).mean() > .02:
            raise ValueError(f"{filename}: spread ausente/0 excesivamente; rechazar")
        seconds = f.index.to_series().diff().dt.total_seconds().dropna()
        smallest = 900 if tf == "M15" else 3600
        if (seconds < smallest).any():
            raise ValueError(f"{filename}: granularidad irregular")
        data[tf] = f
    return data["M15"], data["H1"]


def check_m15_h1_consistency(m15:pd.DataFrame, h1:pd.DataFrame):
    """Compara solo horas M15 completas contra sus barras H1, sin rellenar huecos."""
    agg=m15.resample("1h").agg({"Open":"first","High":"max",
                                      "Low":"min","Close":"last","Spread":"count"})
    complete=agg[agg.Spread==4][["Open","High","Low","Close"]]
    joined=complete.join(h1[["Open","High","Low","Close"]],how="inner",lsuffix="_M15",rsuffix="_H1")
    if len(joined)<500:
        raise ValueError("Menos de 500 velas H1 reconstruibles; incompatibilidad temporal")
    mismatches=np.zeros(len(joined),dtype=bool)
    for field in ("Open","High","Low","Close"):
        mismatches |= ~np.isclose(joined[f"{field}_M15"],joined[f"{field}_H1"],rtol=0,atol=1e-7)
    if mismatches.any():
        raise ValueError(f"H1/M15 no coinciden en {int(mismatches.sum())}/{len(joined)} velas completas")
    return {"complete_hours_compared":len(joined),"mismatches":0}


def causal_indicators(m15: pd.DataFrame, h1: pd.DataFrame) -> pd.DataFrame:
    b = m15.copy()
    c = b.Close
    b["ema20"] = c.ewm(span=20, adjust=False).mean()
    b["ema50"] = c.ewm(span=50, adjust=False).mean()
    prev = c.shift(1)
    tr = pd.concat([b.High-b.Low, (b.High-prev).abs(), (b.Low-prev).abs()],axis=1).max(axis=1)
    b["atr"] = tr.rolling(14, min_periods=14).mean()
    b["atr_ratio"] = b.atr / b.atr.rolling(60, min_periods=60).mean()
    rise = c.diff().clip(lower=0).rolling(14).mean()
    fall = (-c.diff().clip(upper=0)).rolling(14).mean()
    b["rsi"] = 100-100/(1+rise/fall.replace(0,np.nan))
    h = h1.copy()
    h["ema20"] = h.Close.ewm(span=20,adjust=False).mean()
    h["ema50"] = h.Close.ewm(span=50,adjust=False).mean()
    # Timestamp de la barra = comienzo; la tendencia H1 se conoce al cierre H1.
    # No utilizar la barra horaria aún en formación al generar la señal M15.
    h["close_time"] = h.index + pd.Timedelta(hours=1)
    h["h1_direction"] = np.select([h.ema20 > h.ema50,h.ema20<h.ema50],[1,-1],default=0)
    signal_close = pd.DataFrame({"signal_close":b.index + pd.Timedelta(minutes=15),"row":np.arange(len(b))})
    aligned = pd.merge_asof(signal_close.sort_values("signal_close"),
        h[["close_time","h1_direction"]].reset_index(drop=True).sort_values("close_time"),
        left_on="signal_close",right_on="close_time",direction="backward")
    b["h1_direction"] = aligned.sort_values("row").h1_direction.to_numpy()
    b["signal"] = 0
    ok = b[["atr","rsi","atr_ratio","h1_direction"]].notna().all(axis=1)
    long = ok & (b.ema20>b.ema50) & (c>b.ema50) & b.rsi.between(42,68) & (b.atr_ratio>=.82) & (b.h1_direction==1)
    short = ok & (b.ema20<b.ema50) & (c<b.ema50) & b.rsi.between(32,58) & (b.atr_ratio>=.82) & (b.h1_direction==-1)
    b.loc[long,"signal"] = 1
    b.loc[short,"signal"] = -1
    b["ema_gap_atr"] = (b.ema20-b.ema50)/b.atr
    b["close_ema_atr"] = (c-b.ema20)/b.atr
    b["atr_pct"] = b.atr/c
    b["direction"] = b.signal
    b["ret3"] = c.pct_change(3)
    return b.replace([np.inf,-np.inf],np.nan)


def simulate_event(arr: dict, signal_i: int, horizon: int, point: float,
                   slippage_multiplier: float = 0.0, sl_atr=1.2, tp_atr=1.8):
    """Bid OHLC: LONG compra ASK y cierra BID; SHORT vende BID y cierra ASK.

    Barreras fijas a precios de salida ejecutables y selección adversa si
    stop y objetivo se tocan en la misma vela; gaps a precio de apertura.
    slippage_multiplier (spread) se aplica adversamente en ambos extremos.
    """
    d = int(arr["signal"][signal_i])
    atr = float(arr["atr"][signal_i])
    if d not in (-1, 1) or not math.isfinite(atr) or atr<=0:
        raise ValueError("Señal o ATR inválido")
    start = signal_i+1
    end = min(len(arr["open"])-1,signal_i+horizon)
    if start>end:
        raise ValueError("Sin siguiente vela")
    if np.any(arr["spread"][start:end+1] <= 0):
        raise ValueError("Spread no positivo en operación")
    entry_spr = arr["spread"][start]*point
    entry_slippage = entry_spr*slippage_multiplier
    entry = float(arr["open"][start]) + (entry_spr if d==1 else 0.) + d*entry_slippage
    stopdist=sl_atr*atr
    stop=entry-d*stopdist
    target=entry+d*tp_atr*atr
    reason="TIMEOUT"
    j=end
    exit_price=None
    for j in range(start,end+1):
        bid_o=float(arr["open"][j]);bid_h=float(arr["high"][j]);bid_l=float(arr["low"][j])
        spr=arr["spread"][j]*point
        exo=bid_o+(spr if d==-1 else 0.)
        exh=bid_h+(spr if d==-1 else 0.)
        exl=bid_l+(spr if d==-1 else 0.)
        slip=spr*slippage_multiplier
        if (d==1 and exo<=stop) or (d==-1 and exo>=stop):
            exit_price=exo-d*slip;reason="GAP_STOP";break
        hit_stop=exl<=stop if d==1 else exh>=stop
        hit_target=exh>=target if d==1 else exl<=target
        if hit_stop or hit_target:
            exit_price=(stop if hit_stop else target)-d*slip
            reason="BOTH_ASSUME_STOP" if hit_stop and hit_target else ("STOP" if hit_stop else "TARGET")
            break
    if exit_price is None:
        j=end
        spr=arr["spread"][j]*point
        exit_price=float(arr["close"][j])+(spr if d==-1 else 0.)-d*spr*slippage_multiplier
    r=d*(exit_price-entry)/stopdist
    return float(r),int(j),reason


def arrays_from(b:pd.DataFrame):
    return {k: b[v].to_numpy(dtype=float) for k,v in
            {"open":"Open","high":"High","low":"Low","close":"Close",
             "spread":"Spread","atr":"atr","signal":"signal"}.items()}


def make_events(b:pd.DataFrame,horizon:int,point:float):
    """Genera resultados hipotéticos de señales independientemente (labels)."""
    arr=arrays_from(b)
    mat=b[list(FEATURES)].to_numpy(dtype=float)
    events=[]
    for i in range(75,len(b)-horizon):
        if not arr["signal"][i] or not np.isfinite(mat[i]).all():
            continue
        try:
            r,exit_i,_=simulate_event(arr,i,horizon,point)
        except ValueError:
            continue
        events.append((i,exit_i,r,mat[i]))
    return events


def metrics(trades:list[dict],equity:float):
    if not trades:
        return {"trades":0,"win_rate":None,"profit_factor":None,"mean_r":None,
                "return_pct":0.,"max_drawdown_pct":0.}
    pnl=np.array([t["pnl"] for t in trades]);rv=np.array([t["r"] for t in trades])
    total_plus=float(pnl[pnl>0].sum());total_minus=float(-pnl[pnl<0].sum())
    peak=equity;maxdd=0.;balance=equity
    for p in pnl:
        balance+=float(p);peak=max(peak,balance);maxdd=max(maxdd,(peak-balance)/peak)
    return {"trades":len(trades),"win_rate":round(100*float((pnl>0).mean()),3),
            "profit_factor":round(total_plus/total_minus,4) if total_minus>0 else None,
            "mean_r":round(float(rv.mean()),5),"return_pct":round(100*(balance/equity-1),4),
            "max_drawdown_pct":round(maxdd*100,4),
            "reasons":dict(Counter(t["reason"] for t in trades))}


def backtest_events(b:pd.DataFrame,events:list,probabilities,threshold,horizon,point,
                    start,end,p:Params,slippage_multiplier=0):
    arr=arrays_from(b)
    permitted={e[0] for idx,e in enumerate(events) if e[0]>=start and e[0]+horizon<end and
               (threshold is None or (probabilities is not None and probabilities[idx]>=threshold))}
    balance=p.equity;trades=[];next_signal=start
    for i in sorted(permitted):
        if i<next_signal or i+1>=end:
            continue
        r,x,reason=simulate_event(arr,i,horizon,point,slippage_multiplier,p.sl_atr,p.tp_atr)
        if x>=end:
            continue
        pnl=balance*p.risk_fraction*r
        trades.append({"i":i,"exit":x,"r":r,"pnl":pnl,"reason":reason})
        balance+=pnl
        next_signal=x+1
    return metrics(trades,p.equity)


def analyse_market(m15,h1,point,params:Params):
    b=causal_indicators(m15,h1)
    n=len(b);t=int(n*params.train_fraction);v=int(n*(params.train_fraction+params.validation_fraction))
    vs=t+params.embargo_bars;ts=v+params.embargo_bars
    if params.embargo_bars<=max(HORIZONS) or ts>=n-400:
        raise ValueError("Split temporal inseguro")
    candidates=[];cache={}
    for h in HORIZONS:
        ev=make_events(b,h,point)
        train=[e for e in ev if e[0]+h<t]
        validation=[e for e in ev if vs<=e[0] and e[0]+h<v]
        if len(train)<params.min_training_examples or not validation:
            continue
        y=np.array([int(e[2]>0) for e in train]);
        if len(set(y))<2:
            continue
        model=make_pipeline(StandardScaler(),LogisticRegression(C=.2,max_iter=500,random_state=17))
        model.fit(np.vstack([e[3] for e in train]),y)
        pred=model.predict_proba(np.vstack([e[3] for e in validation]))[:,1]
        cache[h]=(model,ev)
        for threshold in THRESHOLDS:
            m=backtest_events(b,validation,pred,threshold,h,point,vs,v,params)
            acceptable=(m["trades"]>=params.min_validation_trades and
                         m["profit_factor"] is not None and m["profit_factor"]>=params.min_pf and
                         m["mean_r"] is not None and m["mean_r"]>=params.min_expectancy_r)
            score=(m["mean_r"]-.025*m["max_drawdown_pct"]) if m["mean_r"] is not None else None
            candidates.append({"horizon_bars":h,"threshold":threshold,"validation":m,
                               "passes":bool(acceptable),"score":round(score,5) if score is not None else None})
    passed=[c for c in candidates if c["passes"]]
    chosen=max(passed,key=lambda c:c["score"]) if passed else None
    summary={"first":str(m15.index.min()),"last":str(m15.index.max()),
             "samples_m15":len(m15),"samples_h1":len(h1),
             "signal_count":int((b.signal!=0).sum()),
             "split":{"train_end":str(m15.index[t]),"validation_from":str(m15.index[vs]),
                      "validation_end":str(m15.index[v]),"holdout_from":str(m15.index[ts]),
                      "embargo_bars":params.embargo_bars},
             "configurations":candidates,"chosen":chosen,
             "decision":"NO_TRADE","reason":"Ninguna configuración pasa validación" if chosen is None else None}
    if chosen is None:
        return summary
    h=chosen["horizon_bars"];model,ev=cache[h]
    held=[e for e in ev if ts<=e[0] and e[0]+h<n]
    probs=model.predict_proba(np.vstack([e[3] for e in held]))[:,1] if held else np.array([])
    optimistic=backtest_events(b,held,probs,chosen["threshold"],h,point,ts,n,params,0.0)
    stress=backtest_events(b,held,probs,chosen["threshold"],h,point,ts,n,params,0.50)
    def good(m):
        return (m["trades"]>=params.min_final_trades and m["profit_factor"] is not None and
                m["profit_factor"]>=params.min_pf and m["mean_r"] is not None and
                m["mean_r"]>=params.min_expectancy_r)
    summary["holdout"]={"spread_only":optimistic,"spread_plus_slippage_half_spread_each_side":stress}
    summary["decision"]="FURTHER_RESEARCH_ONLY" if good(optimistic) and good(stress) else "NO_TRADE"
    summary["reason"]="No supera las condiciones del holdout" if summary["decision"]=="NO_TRADE" else "Pasa filtros exploratorios, pero costes y duración insuficientes para operar"
    return summary


def run(zip_path, params=Params()):
    results={"type":"Admirals MT5 V2 MULTI-ASSET RESEARCH (OFFLINE)",
             "source":Path(zip_path).name,
             "risk_assumptions":{"equity_eur":params.equity,"risk_fraction":params.risk_fraction,
                "fees":"UNKNOWN, EXCLUDED","swaps":"UNKNOWN, EXCLUDED",
                "quote_model":"MT5 OHLC=BID; LONG entry ASK, SHORT exit ASK",
                "selection":"60/20/20 chronological, 40 bar embargo; 3 horizons, ML thresholds",
                "h1_alignment":"only FULLY CLOSED H1 bars in M15 decisions",
                "holdout_scenarios":"historical spreads; stress adds half-spread adverse slippage EACH leg",
                "portfolio_risk":"NOT MODELED: each market simulated independently in EUR normalized R"},
             "markets":{},"approved_for_live":False,"approved_for_demo_execution":False}
    with zipfile.ZipFile(zip_path) as z:
        manifest=json.loads(z.read("admirals_manifest.json"))
        account=manifest.get("account",{})
        if not account.get("demo") or "admir" not in (str(account.get("company",""))+str(account.get("server",""))).lower():
            raise ValueError("Archivo no corresponde a Admirals DEMO")
        if account.get("currency")!="EUR":
            raise ValueError("La cuenta usada no está denominada en EUR: recalibrar supuestos")
        for market,(_symbol,point) in SYMBOLS.items():
            m15,h1=load_data(z,market)
            consistency=check_m15_h1_consistency(m15,h1)
            results["markets"][market]=analyse_market(m15,h1,point,params)
            results["markets"][market]["h1_m15_consistency"]=consistency
    return results


def main():
    parser=argparse.ArgumentParser(description="Evaluación multi-mercado offline Admirals: SIN ÓRDENES")
    parser.add_argument('--zip',required=True,help='ZIP exportado desde Admirals MT5')
    parser.add_argument('--out',default='admirals_v2_research_local_result.json')
    args=parser.parse_args()
    report=run(args.zip)
    Path(args.out).write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    print('TRADING V2 - SIN CONEXION MT5, SIN ORDENES, SIN DINERO REAL')
    for market, r in report['markets'].items():
        choice=r['chosen']
        holdout=r.get('holdout') or {}
        print(market, '->',r['decision'], ' | señales:',r['signal_count'],
              ' | horizonte:',choice['horizon_bars'] if choice else 'ninguno',
              ' | holdout (coste estrés):',holdout.get('spread_plus_slippage_half_spread_each_side',{}).get('profit_factor'))
    print('Informe:',Path(args.out).resolve())

if __name__=='__main__':
    main()
