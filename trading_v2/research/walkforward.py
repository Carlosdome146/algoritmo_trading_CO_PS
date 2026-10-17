"""Selección automática *offline* del horizonte/umbral con bloque final intocable.

Estrategia: baseline original LONG/SHORT, filtro logístico entrenado solo sobre
labels de operaciones hipotéticas (próxima apertura -> stop/target/timeout).
NO ofrece inferencia en vivo ni integra trading en MT5.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from collections import Counter
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from trading_v2.backtesting.engine import Config, run_backtest
from trading_v2.strategies.trend_following import add_indicators

FEATURES = ("ema_gap_atr", "close_ema_atr", "rsi_center", "atr_ratio", "atr_to_price", "direction", "ret_3", "range_atr")
HORIZONS = (4, 16, 32)
THRESHOLDS = (None, 0.25, 0.35, 0.45, 0.55)

@dataclass(frozen=True)
class ResearchConfig:
    horizons: tuple[int, ...] = HORIZONS
    thresholds: tuple[float | None, ...] = THRESHOLDS
    embargo_bars: int = 40
    min_train_samples: int = 100
    min_validation_trades: int = 30
    min_validation_pf: float = 1.10
    min_validation_expectancy_r: float = 0.02
    train_ratio: float = .60
    validation_ratio: float = .20

    def __post_init__(self):
        if any(h < 1 for h in self.horizons) or not self.horizons:
            raise ValueError("Horizontes deben ser positivos")
        if self.embargo_bars <= max(self.horizons):
            raise ValueError("El embargo debe superar el horizonte más largo")
        if not 0 < self.train_ratio < self.train_ratio+self.validation_ratio < 1:
            raise ValueError("División temporal inválida")
        if self.min_validation_trades < 1:
            raise ValueError("Número mínimo de operaciones inválido")


def features_from_bars(bars: pd.DataFrame) -> pd.DataFrame:
    if not {"signal", "ema20", "ema50", "rsi", "atr", "atr_ratio"}.issubset(bars.columns):
        raise ValueError("Faltan indicadores: usar add_indicators primero")
    atr = bars["atr"].replace(0, np.nan)
    close = bars["Close"]
    f = pd.DataFrame(index=bars.index)
    f["ema_gap_atr"] = (bars["ema20"]-bars["ema50"])/atr
    f["close_ema_atr"] = (close-bars["ema20"])/atr
    f["rsi_center"] = (bars["rsi"]-50)/15
    f["atr_ratio"] = bars["atr_ratio"]
    f["atr_to_price"] = atr/close
    f["direction"] = bars["signal"]
    f["ret_3"] = close.pct_change(3)
    f["range_atr"] = (bars["High"]-bars["Low"])/atr
    return f.replace([np.inf,-np.inf],np.nan)


def event_outcome(bars: pd.DataFrame, signal_bar: int, horizon: int, cfg: Config) -> tuple[float, int]:
    """R de evento independiente, replicando las reglas del motor V2.

    El objetivo no incluye costes desconocidos del bróker, comisiones ni swaps.
    Evaluamos las dos barreras con OHLC y asumimos SL en ambigüedad intrabar.
    """
    if horizon < 1 or signal_bar+1 >= len(bars):
        raise ValueError("Evento fuera del histórico")
    side = int(bars["signal"].iloc[signal_bar])
    if side not in (-1,1):
        raise ValueError("Evento sin señal")
    atr = float(bars["atr"].iloc[signal_bar])
    if not np.isfinite(atr) or atr <= 0:
        raise ValueError("ATR inválido")
    start = signal_bar+1
    end = min(len(bars)-1,signal_bar+horizon)
    def spread_at(j):
        pts = cfg.fixed_spread_points if cfg.fixed_spread_points is not None else float(bars["Spread"].iloc[j])
        if not np.isfinite(pts) or pts < 0:
            raise ValueError("Spread inválido")
        return pts*cfg.point
    slip = cfg.slippage_points * cfg.point
    entry = float(bars["Open"].iloc[start]) + side*(spread_at(start)/2+slip)
    dist = cfg.sl_atr * atr
    stop = entry-side*dist
    target = entry+side*cfg.tp_atr*atr
    exit_price = None
    exit_i = end
    for j in range(start,end+1):
        spr=spread_at(j)
        op=float(bars["Open"].iloc[j])-side*spr/2
        hi=float(bars["High"].iloc[j])-side*spr/2
        lo=float(bars["Low"].iloc[j])-side*spr/2
        if (side == 1 and op <= stop) or (side == -1 and op >= stop):
            exit_price = op-side*slip
            exit_i = j
            break
        hit_stop=(lo<=stop) if side==1 else (hi>=stop)
        hit_target=(hi>=target) if side==1 else (lo<=target)
        if hit_stop or hit_target:
            exit_price=(stop if hit_stop else target)-side*slip
            exit_i=j
            break
    if exit_price is None:
        exit_price=float(bars["Close"].iloc[end])-side*spread_at(end)/2-side*slip
    return side*(exit_price-entry)/dist,exit_i


def candidates(bars:pd.DataFrame, features:pd.DataFrame, horizon:int, cfg:Config):
    """Etiquetas que solo usan información hasta el cierre del evento.

    Devuelve posiciones de señal, posiciones de salida, características y R.
    """
    rows=[]
    signals=bars["signal"].to_numpy()
    numeric_features=features.to_numpy(dtype=float)
    atr=bars["atr"].to_numpy()
    for i in range(len(bars)-horizon):
        if signals[i]==0 or not np.isfinite(atr[i]) or atr[i]<=0:
            continue
        if not np.isfinite(numeric_features[i]).all():
            continue
        r,end=event_outcome(bars,i,horizon,cfg)
        rows.append((i,end,numeric_features[i],r))
    return rows


def gate_signals(bars:pd.DataFrame, events:list, probabilities:np.ndarray | None, cutoff:float | None) -> pd.DataFrame:
    filtered=bars.copy()
    filtered["signal"]=0
    for k,(i,_end,_x,_r) in enumerate(events):
        if cutoff is None or (probabilities is not None and probabilities[k]>=cutoff):
            filtered.iat[i,filtered.columns.get_loc("signal")]=int(bars["signal"].iloc[i])
    return filtered


def metric_score(metrics:dict) -> float:
    # Selección en validación únicamente; favorece expectativa y penaliza DD.
    return float(metrics["mean_R"] - .025*metrics["max_drawdown_pct"])


def research(bars:pd.DataFrame, cfg: Config, rc:ResearchConfig=ResearchConfig()) -> dict:
    """Entrena en 60%, elige horizonte/umbral en 20%, evalúa una vez en 20%.

    Sin retuning ni modificación de modelos después de consultar el test.
    """
    if len(bars)<2000:
        raise ValueError("Se requieren al menos 2000 barras para entrenar/validar/probar")
    b=add_indicators(bars)
    f=features_from_bars(b)
    n=len(b)
    t=int(n*rc.train_ratio)
    v=int(n*(rc.train_ratio+rc.validation_ratio))
    maxh=max(rc.horizons)
    if min(t, v-t, n-v) < rc.min_train_samples + 2*rc.embargo_bars+maxh:
        raise ValueError("Histórico insuficiente para separación con embargo")
    validation_start=t+rc.embargo_bars
    test_start=v+rc.embargo_bars
    configs=[]
    candidates_by_h={}
    for h in rc.horizons:
        e=candidates(b,f,h,cfg)
        candidates_by_h[h]=e
        tr=[x for x in e if x[1]<t]
        va=[x for x in e if validation_start<=x[0] and x[1]<v]
        if len(tr)<rc.min_train_samples or len(va)<rc.min_validation_trades:
            continue
        xtr=np.vstack([x[2] for x in tr]); ytr=np.array([int(x[3]>0) for x in tr])
        if len(set(ytr))<2:
            continue
        model=make_pipeline(StandardScaler(),LogisticRegression(C=.2, max_iter=500, random_state=17))
        model.fit(xtr,ytr)
        pva=model.predict_proba(np.vstack([x[2] for x in va]))[:,1]
        candidates_by_h[h]=(e,model)
        for threshold in rc.thresholds:
            filtered=gate_signals(b,va,pva,threshold)
            segment=filtered.iloc[validation_start:v]
            params=replace(cfg,max_bars_held=h)
            metrics,_=run_backtest(segment,params)
            eligible=(metrics["trades"]>=rc.min_validation_trades
                      and metrics["profit_factor"] is not None
                      and metrics["profit_factor"]>=rc.min_validation_pf
                      and metrics["mean_R"] is not None
                      and metrics["mean_R"]>=rc.min_validation_expectancy_r)
            configs.append({"horizon_bars":h,"ml_threshold":threshold,"mode":"BASELINE" if threshold is None else "ML_FILTER",
                            "validation":metrics,"eligible":bool(eligible),"score":round(metric_score(metrics),6) if metrics["mean_R"] is not None else None})
    acceptable=[x for x in configs if x["eligible"]]
    # Nunca elegir parámetros con información del test.
    chosen=max(acceptable,key=lambda x:x["score"]) if acceptable else None
    split={"train_end_exclusive":str(b.index[t]), "validation_start":str(b.index[validation_start]),
           "validation_end_exclusive":str(b.index[v]),"test_start":str(b.index[test_start]),
           "embargo_bars":rc.embargo_bars,"train_ratio":rc.train_ratio,"validation_ratio":rc.validation_ratio}
    base={"decision":"NO_TRADE" if chosen is None else "VALIDATE_IN_DEMO_ONLY",
          "split":split,"tested_configs":configs, "chosen":chosen,
          "note":"Offline. Sin fees/swap/lotaje/condiciones del bróker. Test no usado para seleccionar. No autoriza operativa real."}
    if chosen is None:
        return base
    horizon=chosen["horizon_bars"]
    e,model=candidates_by_h[horizon]
    te=[x for x in e if test_start<=x[0] and x[1]<n]
    pte=model.predict_proba(np.vstack([x[2] for x in te]))[:,1] if te else np.array([])
    filtered=gate_signals(b,te,pte,chosen["ml_threshold"])
    m,trades=run_backtest(filtered.iloc[test_start:],replace(cfg,max_bars_held=horizon))
    base["test"]={"metrics":m,"reason_counts":dict(Counter(x["reason"] for x in trades)),
                  "avg_prob_if_accepted":(round(float(np.mean([p for p in pte if p>=chosen["ml_threshold"]])),4)
                                            if chosen["ml_threshold"] is not None and np.any(pte>=chosen["ml_threshold"]) else None),
                  "trades_sample":trades[:3],"rejected_note":"Si el OOS fracasa, mantener NO_TRADE; no optimizar de nuevo sobre test."}
    if (m["trades"]<rc.min_validation_trades or m["mean_R"] is None or m["mean_R"]<=0 or (m["profit_factor"] is not None and m["profit_factor"]<=1)):
        base["decision"]="NO_TRADE"
        base["test"]["out_of_sample_pass"]=False
    else:
        base["test"]["out_of_sample_pass"]=True
    return base
