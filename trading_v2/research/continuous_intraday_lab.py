"""Laboratorio OFFLINE de trading intradía CONTINUO M15/M30 (NO ORB).

Entrada: ZIP M5 de Admirals DEMO exportado con scripts/exportar_orb_m5_mt5.py
(aunque se llame 'orb', los datos abarcan las sesiones completas).
Resampling desde M5 completos => M15/M30/H1 causales. Señal al CIERRE,
entrada en la APERTURA de la siguiente vela, sin trades overnight.
NO conecta a MetaTrader5 ni emite órdenes, incluso si el backtest es positivo.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import math
import zipfile

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from scripts.investigar_admirals_v2 import metrics
from trading_v2.strategies.candidates import STRATEGIES, generate_signals
from trading_v2.strategies.trend_following import add_indicators

MARKETS = {
    "DAX40": ("GERMANY40", .01, "Europe/Berlin", "09:00", "17:30"),
    "SP500": ("[SP500]", .01, "America/New_York", "09:30", "16:00"),
    "NASDAQ100": ("US100", .01, "America/New_York", "09:30", "16:00"),
    "DOW30": ("[DJI30]", .01, "America/New_York", "09:30", "16:00"),
}
TIMEFRAMES = (15, 30)
HORIZONS_MINUTES = (60, 120)
ML_THRESHOLDS = (None, .55)
ML_FEATURES = ("ema_gap_atr", "close_ema_atr", "rsi", "atr_ratio",
               "h1_direction", "spread_atr", "ret3", "direction")


@dataclass(frozen=True)
class IntradayLabConfig:
    equity: float = 3000.
    risk_fraction: float = .0025
    sl_atr: float = 1.2
    tp_atr: float = 1.8
    slippage_spread: float = .5
    embargo_bars: int = 12  # 12 M30 = 6h; > 4 barras horizonte máximo M30
    min_train_events: int = 80
    min_validation_trades: int = 12
    min_holdout_trades: int = 30
    min_pf: float = 1.10
    min_mean_r: float = .02

    def __post_init__(self) -> None:
        if not 0 < self.risk_fraction <= .01 or self.equity <= 0:
            raise ValueError("Riesgo/capital invalidos")
        if self.sl_atr <= 0 or self.tp_atr <= 0 or self.slippage_spread < 0:
            raise ValueError("Stop, target o slippage invalidos")
        if self.embargo_bars <= max(HORIZONS_MINUTES)//min(TIMEFRAMES):
            raise ValueError("Embargo debe exceder el horizonte maximo")
        if min(self.min_train_events,self.min_validation_trades,self.min_holdout_trades) < 1:
            raise ValueError("Minimos de muestra invalidos")


def read_m5(z:zipfile.ZipFile, market:str) -> tuple[pd.DataFrame,dict]:
    csv = f"ADMIRALS_{market}_M5.csv"
    b = pd.read_csv(BytesIO(z.read(csv)))
    required = {"Time","Open","High","Low","Close","Spread"}
    if not required.issubset(b.columns):
        raise ValueError(f"{csv}: faltan columnas {sorted(required-set(b.columns))}")
    b["Time"] = pd.to_datetime(b["Time"],utc=True,errors="raise")
    b = b.set_index("Time")
    if b.empty or b.index.has_duplicates or not b.index.is_monotonic_increasing:
        raise ValueError(f"{csv}: tiempo desordenado o duplicado")
    for col in ("Open","High","Low","Close","Spread"):
        b[col] = pd.to_numeric(b[col],errors="raise")
    if not np.isfinite(b[list(required-{"Time"})].to_numpy(dtype=float)).all():
        raise ValueError(f"{csv}: datos numericos invalidos")
    if (b[["Open","High","Low","Close"]] <= 0).any().any() or (b.Spread<0).any():
        raise ValueError(f"{csv}: precios o spreads invalidos")
    if ((b.High < b[["Open","Low","Close"]].max(axis=1)) |
        (b.Low > b[["Open","Close"]].min(axis=1))).any():
        raise ValueError(f"{csv}: OHLC inconsistente")
    diffs = b.index.to_series().diff().dropna().dt.total_seconds()
    if (diffs < 300).any() or ((diffs % 300)!=0).any():
        raise ValueError(f"{csv}: serie no M5")
    raw = b["Spread"].astype(float)
    n_zero = int((raw==0).sum())
    quality = {"m5_bars":len(b),"spread_zero_bars":n_zero,
               "spread_zero_pct":round(n_zero*100/len(b),3),
               "spread_imputed":0,"spread_unusable":0}
    if n_zero/len(b)>.20:
        raise ValueError(f"{csv}: más del 20% de spreads desconocidos")
    # Spreads 0 = DESCONOCIDO. Percentil 75 de los positivos anteriores;
    # jamás usar futuros o considerar cero como sin coste.
    prior_positive = raw.where(raw>0).shift(1)
    estimated = prior_positive.rolling(288,min_periods=8).quantile(.75)
    usable = raw.where(raw>0,estimated)
    b["SpreadUsable"] = usable.notna() & (usable>0)
    b["SpreadImputed"] = raw.eq(0) & b["SpreadUsable"]
    b["Spread"] = usable
    quality["spread_imputed"]=int(b["SpreadImputed"].sum())
    quality["spread_unusable"]=int((~b["SpreadUsable"]).sum())
    return b,quality


def resample_complete(m5:pd.DataFrame, minutes:int)->pd.DataFrame:
    """NUNCA usar barras parciales; el índice de una vela es su APERTURA UTC."""
    if minutes not in (15,30,60):
        raise ValueError("Solo M15, M30 y H1")
    count = minutes//5
    a=m5.copy()
    a["_ones"]=1
    a["_open_time"]=a.index
    grouped=a.resample(f"{minutes}min",label="left",closed="left").agg({
        "Open":"first","High":"max","Low":"min","Close":"last",
        "Spread":"max", "SpreadUsable":"min",
        "_ones":"sum","_open_time":["first","last"],
    })
    grouped.columns=["Open","High","Low","Close","Spread","SpreadUsable",
                     "Count","FirstTs","LastTs"]
    expected_end=grouped.index + pd.Timedelta(minutes=minutes-5)
    completed=(grouped.Count==count) & (grouped.FirstTs==grouped.index) & (grouped.LastTs==expected_end)
    out=grouped.loc[completed,["Open","High","Low","Close","Spread","SpreadUsable"]].copy()
    out["SpreadUsable"]=out["SpreadUsable"].astype(bool)
    return out


def causal_h1_direction(b:pd.DataFrame,h1:pd.DataFrame,minutes:int) -> pd.Series:
    if h1.empty:
        return pd.Series(np.nan,index=b.index)
    h=h1.copy()
    h["e20"]=h.Close.ewm(span=20,adjust=False).mean()
    h["e50"]=h.Close.ewm(span=50,adjust=False).mean()
    h["direction"]=np.select([h.e20>h.e50,h.e20<h.e50],[1,-1],default=0)
    h["closed_at"]=h.index+pd.Timedelta(hours=1)
    # Solo la H1 YA CERRADA cuando termina M15/M30.
    q=pd.DataFrame({"closed_at":b.index+pd.Timedelta(minutes=minutes),
                    "_pos":np.arange(len(b))})
    aligned=pd.merge_asof(q.sort_values("closed_at"),
                          h[["closed_at","direction"]].sort_values("closed_at"),
                          on="closed_at",direction="backward")
    return pd.Series(aligned.sort_values("_pos").direction.to_numpy(),index=b.index)


def in_cash_session(b:pd.DataFrame,minutes:int,market:str)->pd.Series:
    sym,point,zone,op,cl=MARKETS[market]
    local=(b.index+pd.Timedelta(minutes=minutes)).tz_convert(zone)
    day=local.strftime("%H:%M")
    return pd.Series((local.weekday<5) & (day>op) & (day<=cl),index=b.index)


def session_close_utc(index:pd.Timestamp,market:str)->pd.Timestamp:
    _,_,zone,_,end=MARKETS[market]
    local=index.tz_convert(zone)
    hour,minute=map(int,end.split(":"))
    date_local=local.date()
    return pd.Timestamp(date_local).tz_localize(zone)+pd.Timedelta(hours=hour,minutes=minute)


def make_signals(b:pd.DataFrame,h1:pd.DataFrame,minutes:int,market:str,strategy:str)->pd.DataFrame:
    _,point,*_=MARKETS[market]
    base=add_indicators(b)
    base["h1_direction"]=causal_h1_direction(base,h1,minutes)
    if strategy=="ema_rsi_baseline":
        # El baseline existente no lleva filtro H1 en su función individual.
        # Se aplica en esta capa, sin cambiar el codigo legado.
        match=base.signal*base.h1_direction==1
        base.loc[~match.fillna(False),"signal"]=0
    out=generate_signals(base,strategy,point)
    tradable=in_cash_session(out,minutes,market)
    tradable &= out["SpreadUsable"].fillna(False)
    out.loc[~tradable,"signal"]=0
    out["direction"]=out.signal.astype(int)
    out["ema_gap_atr"]=(out.ema20-out.ema50)/out.atr.replace(0,np.nan)
    out["close_ema_atr"]=(out.Close-out.ema20)/out.atr.replace(0,np.nan)
    out["spread_atr"]=out.Spread*point/out.atr.replace(0,np.nan)
    out["ret3"]=out.Close.pct_change(3)
    return out.replace([np.inf,-np.inf],np.nan)


def simulate_trade(b:pd.DataFrame,signal_i:int,minutes:int,market:str,
                   horizon_minutes:int,cfg:IntradayLabConfig):
    """OHLC MT5 BID. Entradas/salidas por BID/ASK + deslizamiento adverso.

    Si TP y SL se tocan en una vela M15/M30, se supone STOP.
    Se bloquean entradas que no puedan salir antes del fin de sesión cash.
    """
    idx=b.index
    direction=int(b.signal.iloc[signal_i])
    if direction not in (-1,1) or signal_i+1>=len(b):
        return None
    i=signal_i+1
    delta=pd.Timedelta(minutes=minutes)
    if idx[i]-idx[signal_i]!=delta or not bool(b.SpreadUsable.iloc[i]):
        return None
    session_end=session_close_utc(idx[signal_i],market)
    if idx[i]<idx[signal_i] or idx[i]>=session_end:
        return None
    atr=float(b.atr.iloc[signal_i])
    if not math.isfinite(atr) or atr<=0:
        return None
    stop_distance=cfg.sl_atr*atr
    max_i=min(len(idx)-1,signal_i+horizon_minutes//minutes)
    start_spread=float(b.Spread.iloc[i])*MARKETS[market][1]
    entry_bid=float(b.Open.iloc[i])
    entry=entry_bid+(start_spread if direction==1 else 0.)+direction*cfg.slippage_spread*start_spread
    stop=entry-direction*stop_distance
    target=entry+direction*cfg.tp_atr*atr
    reason="TIMEOUT"
    exit_price=None
    exit_i=i
    for j in range(i,max_i+1):
        if j>i and idx[j]-idx[j-1]!=delta:
            # Serie histórica incompleta: resultado desconocido, no se finge un win.
            return None
        if idx[j]+delta>session_end:
            break
        if not bool(b.SpreadUsable.iloc[j]) or not math.isfinite(float(b.Spread.iloc[j])):
            return None
        spread=float(b.Spread.iloc[j])*MARKETS[market][1]
        out_open=float(b.Open.iloc[j])+(spread if direction==-1 else 0)
        out_high=float(b.High.iloc[j])+(spread if direction==-1 else 0)
        out_low=float(b.Low.iloc[j])+(spread if direction==-1 else 0)
        slip=cfg.slippage_spread*spread
        exit_i=j
        gap=(out_open<=stop if direction==1 else out_open>=stop)
        if gap:
            exit_price=out_open-direction*slip
            reason="GAP_STOP"
            break
        stopped=(out_low<=stop if direction==1 else out_high>=stop)
        targeted=(out_high>=target if direction==1 else out_low<=target)
        if stopped or targeted:
            exit_price=(stop if stopped else target)-direction*slip
            reason="BOTH_ASSUME_STOP" if stopped and targeted else ("STOP" if stopped else "TARGET")
            break
    if exit_price is None:
        if exit_i<i:
            return None
        spread=float(b.Spread.iloc[exit_i])*MARKETS[market][1]
        exit_price=float(b.Close.iloc[exit_i])+(spread if direction==-1 else 0)-direction*cfg.slippage_spread*spread
        reason="SESSION_OR_TIME_EXIT"
    rr=direction*(exit_price-entry)/stop_distance
    features=np.array([float(b[f].iloc[signal_i]) for f in ML_FEATURES],dtype=float)
    if not np.isfinite(features).all() or not math.isfinite(rr):
        return None
    return {"i":signal_i,"exit_i":exit_i,"r":float(rr),"reason":reason,
            "features":features,"direction":direction}


def make_events(b:pd.DataFrame,minutes:int,market:str,horizon_minutes:int,cfg:IntradayLabConfig)->list[dict]:
    result=[]
    for i in np.flatnonzero(b.signal.to_numpy(dtype=int)):
        ev=simulate_trade(b,int(i),minutes,market,horizon_minutes,cfg)
        if ev is not None:
            result.append(ev)
    return result


def metrics_for_events(events:list[dict],cfg:IntradayLabConfig)->dict:
    balance=cfg.equity
    trades=[]
    for e in events:
        pnl=balance*cfg.risk_fraction*e["r"]
        trades.append({"pnl":pnl,"r":e["r"],"reason":e["reason"]})
        balance+=pnl
    return metrics(trades,cfg.equity)


def select_trades(events:list[dict],start:int,end:int,cutoff:float|None,
                  model=None) ->list[dict]:
    """No abre posiciones superpuestas ni mezcla pliegues temporales."""
    viable=[e for e in events if start<=e["i"] and e["exit_i"]<end]
    if cutoff is not None:
        if model is None or not viable:
            return []
        probs=model.predict_proba(np.vstack([e["features"] for e in viable]))[:,1]
        viable=[e for e,p in zip(viable,probs) if p>=cutoff]
    viable=sorted(viable,key=lambda v:v["i"])
    chosen=[];next_bar=start
    for e in viable:
        if e["i"]<next_bar:
            continue
        chosen.append(e)
        next_bar=e["exit_i"]+1
    return chosen


def fit_ml(events:list[dict],cutoff:int,cfg:IntradayLabConfig):
    past=[e for e in events if e["exit_i"] < cutoff]
    if len(past)<cfg.min_train_events:
        return None
    x=np.vstack([e["features"] for e in past])
    y=np.array([int(e["r"]>0) for e in past])
    if len(set(y))<2:
        return None
    model=make_pipeline(StandardScaler(),LogisticRegression(C=.2,max_iter=500,random_state=17))
    model.fit(x,y)
    return model


def windows(n:int,cfg:IntradayLabConfig):
    if n<1500:
        raise ValueError("Histórico M15/M30 insuficiente (mínimo 1.500 velas completas)")
    p45,p58,p78=(int(n*f) for f in (.45,.58,.78))
    folds=((p45,p45+cfg.embargo_bars,p58),(p58,p58+cfg.embargo_bars,p78))
    final=(p78,p78+cfg.embargo_bars,n)
    if any(end-start<100 for _,start,end in folds) or final[1]>=n-100:
        raise ValueError("No hay suficientes barras separadas por embargo")
    return folds,final


def passes(m:dict,cfg:IntradayLabConfig,min_trades:int):
    return (m["trades"]>=min_trades and m["profit_factor"] is not None and
            m["profit_factor"]>=cfg.min_pf and m["mean_r"] is not None and
            m["mean_r"]>=cfg.min_mean_r)


def analyze_market(m5:pd.DataFrame,market:str,cfg:IntradayLabConfig=IntradayLabConfig())->dict:
    h1=resample_complete(m5,60)
    result={"market":market,"bars_m5":len(m5),"candidates":[],"chosen":None,
            "holdout":None,"decision":"NO_TRADE","signal_totals":{}}
    prepared={}
    for minutes in TIMEFRAMES:
        b=resample_complete(m5,minutes)
        folds,final=windows(len(b),cfg)
        for strategy in STRATEGIES:
            s=make_signals(b,h1,minutes,market,strategy)
            result["signal_totals"][f"M{minutes}_{strategy}"]=int((s.signal!=0).sum())
            for horizon in HORIZONS_MINUTES:
                events=make_events(s,minutes,market,horizon,cfg)
                prepared[(minutes,strategy,horizon)]=(s,events,folds,final)
                fold_items=[]
                for train_end,start,end in folds:
                    ml=fit_ml(events,train_end,cfg)
                    fold_items.append((start,end,ml))
                for cutoff in ML_THRESHOLDS:
                    values=[]
                    for start,end,model in fold_items:
                        trades=select_trades(events,start,end,cutoff,model)
                        values.append(metrics_for_events(trades,cfg))
                    ok=all(passes(m,cfg,cfg.min_validation_trades) for m in values)
                    score=(round(min(m["mean_r"] for m in values) -
                                 .025*max(m["max_drawdown_pct"] for m in values),6) if ok else None)
                    result["candidates"].append({
                        "timeframe":f"M{minutes}","strategy":strategy,
                        "horizon_minutes":horizon,"ml_threshold":cutoff,
                        "events":len(events),"folds":values,
                        "passes_validation":ok,"score":score,
                    })
    accepted=[c for c in result["candidates"] if c["passes_validation"]]
    if not accepted:
        result["reason"]="Ningún candidato M15/M30 supera ambas validaciones temporales"
        return result
    winner=max(accepted,key=lambda c:(c["score"],min(m["trades"] for m in c["folds"])))
    result["chosen"]=winner
    minutes=int(winner["timeframe"][1:])
    _,events,_,(train_end,start,end)=prepared[(minutes,winner["strategy"],winner["horizon_minutes"])]
    model=fit_ml(events,train_end,cfg) if winner["ml_threshold"] is not None else None
    holdout=select_trades(events,start,end,winner["ml_threshold"],model)
    result["holdout"]=metrics_for_events(holdout,cfg)
    result["decision"]="FURTHER_RESEARCH_ONLY" if passes(result["holdout"],cfg,cfg.min_holdout_trades) else "NO_TRADE"
    result["reason"]="Ni siquiera un holdout favorable autoriza órdenes; faltan costes contractuales y paper trading prospectivo"
    return result


def run_zip(path:str|Path,cfg:IntradayLabConfig=IntradayLabConfig())->dict:
    result={"study":"CONTINUOUS_INTRADAY_M15_M30_OFFLINE",
            "source":Path(path).name,
            "strategy_families":list(STRATEGIES),
            "timeframes":["M15","M30"],
            "session_type":"full cash market session Europe/Berlin or America/New_York with DST",
            "hypotheses_per_market":len(TIMEFRAMES)*len(STRATEGIES)*len(HORIZONS_MINUTES)*len(ML_THRESHOLDS),
            "risk":{"theoretical_risk_fraction":cfg.risk_fraction,"entry_exit":"bid/ask; spread + adverse half-spread slippage",
                    "commissions":"NOT MODELED","swaps":"NOT MODELED","lotage":"NOT MODELED"},
            "selection":"two expanding folds with embargo; holdout only for selected candidate",
            "approval":{"auto_demo":False,"real":False},"markets":{}}
    with zipfile.ZipFile(path) as z:
        manifest=json.loads(z.read("orb_manifest.json"))
        acc=manifest.get("account",{})
        if (acc.get("demo") is not True or acc.get("currency")!="EUR" or
            "admir" not in (str(acc.get("company",""))+" "+str(acc.get("server",""))).lower()):
            raise ValueError("Solo ZIP de Admirals DEMO EUR; no mezclar fuentes de bróker")
        for market in MARKETS:
            record=manifest.get("markets",{}).get(market,{})
            if not record.get("file"):
                result["markets"][market]={"decision":"NO_TRADE_DATA_MISSING",
                    "reason":"Sin CSV M5 exportado"}
                continue
            try:
                data,quality=read_m5(z,market)
                study=analyze_market(data,market,cfg)
                study["data_quality"]=quality
                result["markets"][market]=study
            except (ValueError, KeyError, pd.errors.ParserError) as exc:
                result["markets"][market]={"decision":"NO_TRADE_DATA_INVALID",
                    "reason":str(exc)}
    return result
