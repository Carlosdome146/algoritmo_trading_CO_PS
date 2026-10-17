"""Laboratorio OFFLINE: comparar cuatro estrategias y horizontes con costes.

Dos pliegues de validación temporal expansiva, embargo de 40 barras,
selección SOLO en validación y holdout final reservado. No conecta a MT5.
No se reoptimiza a partir de un resultado negativo.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections import Counter
from pathlib import Path
import json
import zipfile
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from scripts import investigar_admirals_v2 as prior
from trading_v2.strategies import STRATEGIES,generate_signals

HORIZONS=(4,16,32)
CUTOFFS=(None,.55)


@dataclass(frozen=True)
class LabConfig:
    min_trades_fold: int=12
    min_trades_final: int=30
    min_training_events: int=80
    min_pf: float=1.10
    min_mean_r: float=.02
    embargo: int=40
    risk_fraction: float=.0025
    initial_eur:float=3000.
    slip_as_spread:float=.5

    def __post_init__(self):
        if self.embargo<=max(HORIZONS):
            raise ValueError('El embargo debe superar el horizonte máximo')
        if self.min_trades_fold<=0 or self.min_trades_final<=0 or self.min_training_events<=0:
            raise ValueError('Muestras mínimas deben ser positivas')
        if not 0<self.risk_fraction<=.01 or self.initial_eur<=0:
            raise ValueError('Límites de riesgo inválidos')
        if self.slip_as_spread<0:
            raise ValueError('Slippage inválido')


def windows(n, cfg:LabConfig):
    """Pliegues de tren creciente y bloques posteriores SIN solapamiento.

    F1: train [0,45%) -> validate [45%+embargo,58%).
    F2: train [0,58%) -> validate [58%+embargo,78%).
    Holdout final [78%+embargo,100%).
    """
    if n<3000:
        raise ValueError('No hay suficientes barras para validación temporal')
    p45,p58,p78=(int(n*p) for p in (.45,.58,.78))
    folds=((p45,p45+cfg.embargo,p58),(p58,p58+cfg.embargo,p78))
    holdout_start=p78+cfg.embargo
    if holdout_start>n-200 or any(end-start<max(HORIZONS)+cfg.min_trades_fold for _tr,start,end in folds):
        raise ValueError('Ventanas temporales insuficientes')
    return folds,(p78,holdout_start,n)


def _get_classifier(train, min_events):
    if len(train)<min_events:
        return None
    y=np.array([int(e[2]>0) for e in train],dtype=int)
    if np.unique(y).size<2:
        return None
    x=np.vstack([e[3] for e in train])
    model=make_pipeline(StandardScaler(),LogisticRegression(C=.2,max_iter=500,random_state=17))
    model.fit(x,y)
    return model


def _pass(m:dict,cfg:LabConfig,minimum:int):
    return (m['trades']>=minimum and m['profit_factor'] is not None and
            m['profit_factor']>=cfg.min_pf and m['mean_r'] is not None and
            m['mean_r']>=cfg.min_mean_r)


def loss_patterns(b,events,probs,threshold,horizon,point,start,end,cfg:LabConfig):
    """Diario de pérdidas explicativo, nunca aprendizaje/reentreno automático."""
    candidates={e[0]:idx for idx,e in enumerate(events)
                if start<=e[0] and e[0]+horizon<end and
                (threshold is None or (probs is not None and probs[idx]>=threshold))}
    a=prior.arrays_from(b)
    logs=[]
    next_i=start
    for i in sorted(candidates):
        if i<next_i:
            continue
        r,x,reason=prior.simulate_event(a,i,horizon,point,cfg.slip_as_spread)
        if x>=end:
            continue
        logs.append({'entry_signal_at':str(b.index[i]),'side':'LONG' if a['signal'][i]>0 else 'SHORT',
                     'R':round(float(r),5),'reason':reason,
                     'spread_to_atr':round(float(a['spread'][i]*point/a['atr'][i]),5),
                     'rsi':round(float(b['rsi'].iloc[i]),2),
                     'h1_direction':int(b.h1_direction.iloc[i]),
                     'ml_probability':round(float(probs[candidates[i]]),4) if threshold is not None else None})
        next_i=x+1
    losers=[q for q in logs if q['R']<0]
    winners=[q for q in logs if q['R']>0]
    return {
        'trades_recorded':len(logs),'losers':len(losers),
        'losses_by_side':dict(Counter(q['side'] for q in losers)),
        'losses_by_reason':dict(Counter(q['reason'] for q in losers)),
        'median_spread_atr_losses':round(float(np.median([q['spread_to_atr'] for q in losers])),5) if losers else None,
        'median_spread_atr_wins':round(float(np.median([q['spread_to_atr'] for q in winners])),5) if winners else None,
        'sample_losses':losers[:5],
        'note':'Información diagnóstica fuera de muestra. NO modificar parámetros ni reentrenar usando este mismo holdout.',
    }


def research_market(m15,h1,point,cfg:LabConfig=LabConfig()):
    base=prior.causal_indicators(m15,h1)
    folds,final_window=windows(len(base),cfg)
    params=prior.Params(equity=cfg.initial_eur,risk_fraction=cfg.risk_fraction)
    options=[]; prepared={}
    for strategy in STRATEGIES:
        b=generate_signals(base,strategy,point)
        signal_count=int((b.signal!=0).sum())
        for h in HORIZONS:
            events=prior.make_events(b,h,point)
            prepared[(strategy,h)]=(b,events)
            fold_context=[]
            for train_end,val_start,val_end in folds:
                train=[e for e in events if e[0]+h<train_end]
                validation=[e for e in events if val_start<=e[0] and e[0]+h<val_end]
                model=_get_classifier(train,cfg.min_training_events)
                preds=(model.predict_proba(np.vstack([e[3] for e in validation]))[:,1]
                       if model is not None and validation else None)
                fold_context.append((validation,preds,val_start,val_end))
            for cutoff in CUTOFFS:
                fold_metrics=[]
                for validation,preds,start,end in fold_context:
                    if cutoff is not None and preds is None:
                        fold_metrics.append(prior.metrics([],cfg.initial_eur))
                    else:
                        fold_metrics.append(prior.backtest_events(b,validation,preds,cutoff,h,point,start,end,params,
                                                                  slippage_multiplier=cfg.slip_as_spread))
                pass_both=all(_pass(m,cfg,cfg.min_trades_fold) for m in fold_metrics)
                score=(round(min(m['mean_r'] for m in fold_metrics) -
                              .025*max(m['max_drawdown_pct'] for m in fold_metrics),6)
                       if pass_both else None)
                options.append({'strategy':strategy,'horizon_bars':h,'ml_threshold':cutoff,
                                'total_signals':signal_count,'validation_folds':fold_metrics,
                                'passes_both_folds':pass_both,'score':score})
    # La elección no consulta ni utiliza resultados del holdout.
    accepted=[x for x in options if x['passes_both_folds']]
    winner=max(accepted,key=lambda x:(x['score'],x['validation_folds'][1]['win_rate'])) if accepted else None
    result={'signals':{s:int((prepared[(s,HORIZONS[0])][0].signal!=0).sum()) for s in STRATEGIES},
            'validation_candidates':options,'chosen':winner,
            'window_boundaries':{'folds':[{'train_end_exclusive':str(base.index[train_end]),
                                           'validation_start':str(base.index[st]),
                                           'validation_end_exclusive':str(base.index[end])}
                                          for train_end,st,end in folds],
                                'holdout_start':str(base.index[final_window[1]]),'embargo_bars':cfg.embargo},
            'decision':'NO_TRADE','holdout':None}
    if winner is None:
        result['reason']='Ninguna estrategia/horizonte/filtro supera ambos pliegues temporales'
        return result
    strategy,h,cutoff=winner['strategy'],winner['horizon_bars'],winner['ml_threshold']
    b,events=prepared[(strategy,h)]
    train_end,test_start,test_end=final_window
    held=[e for e in events if test_start<=e[0] and e[0]+h<test_end]
    train=[e for e in events if e[0]+h<train_end]
    model=_get_classifier(train,cfg.min_training_events) if cutoff is not None else None
    if cutoff is not None and model is None:
        raise RuntimeError('ML elegido sin capacidad de entrenamiento final')
    preds=model.predict_proba(np.vstack([e[3] for e in held]))[:,1] if model is not None and held else None
    base_metrics=prior.backtest_events(b,held,preds,cutoff,h,point,test_start,test_end,params,slippage_multiplier=0)
    stressed=prior.backtest_events(b,held,preds,cutoff,h,point,test_start,test_end,params,
                                  slippage_multiplier=cfg.slip_as_spread)
    patterns=loss_patterns(b,held,preds,cutoff,h,point,test_start,test_end,cfg)
    result['holdout']={'spread_only':base_metrics,'spread_plus_slippage':stressed,'loss_analysis':patterns,
                       'passes_test':_pass(base_metrics,cfg,cfg.min_trades_final) and
                                     _pass(stressed,cfg,cfg.min_trades_final)}
    # Jamás pasar a live en esta versión, incluso si el holdout es favorable.
    result['decision']='FURTHER_RESEARCH_ONLY' if result['holdout']['passes_test'] else 'NO_TRADE'
    result['reason']=('Candidato a investigación adicional: falta comisión, swap, lotaje, multi-régimen'
                      if result['holdout']['passes_test'] else
                      'La configuración elegida no supera el holdout reservado')
    return result


def run_archive(path,config:LabConfig=LabConfig()):
    result={'study':'Trading V2 Strategy Lab offline v1',
            'source_archive':Path(path).name,
            'sources':'Reglas originales inspiradas en Donchian, Bollinger/RSI/ADX y Supertrend; sin copiar código externo',
            'risk':{'capital_eur_theoretical':config.initial_eur,'fraction':config.risk_fraction,
                    'lots':'NOT MODELED','margin':'NOT MODELED',
                    'commission':'UNKNOWN / EXCLUDED','swap':'UNKNOWN / EXCLUDED',
                    'costs':'Bid OHLC, historical spread; stress extra 0.5 spread at each leg'},
            'method':'Two expanding validation folds (train 0-45%/0-58%; validation 45-58%/58-78%; holdout 78-100%, 40 bar embargo)',
            'approval':{'live':False,'demo_execution':False},'markets':{}}
    with zipfile.ZipFile(path) as z:
        m=json.loads(z.read('admirals_manifest.json'))['account']
        if not m.get('demo') or 'admir' not in (str(m.get('company',''))+str(m.get('server',''))).lower() or m.get('currency')!='EUR':
            raise ValueError('Debe utilizarse el ZIP Admirals DEMO EUR válido')
        for market,(_sym,point) in prior.SYMBOLS.items():
            m15,h1=prior.load_data(z,market)
            consistency=prior.check_m15_h1_consistency(m15,h1)
            result['markets'][market]=research_market(m15,h1,point,config)
            result['markets'][market]['data_quality']={'h1_consistency':consistency,
                                                       'm15_bars':len(m15),'h1_bars':len(h1)}
    return result
