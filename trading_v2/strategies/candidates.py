"""Estrategias V2 offline. Implementación original de reglas conocidas.

Inspiración conceptual: Donchian, Bollinger/RSI/ADX, Supertrend. No se han
copiado implementaciones de otros repositorios ni estrategias hiperoptimizadas.
Cada señal del índice i solo usa OHLC de velas cerradas hasta i y H1 cerrada.
"""
from __future__ import annotations
from typing import Literal
import numpy as np
import pandas as pd

STRATEGIES = ("ema_rsi_baseline", "donchian_breakout", "bollinger_reversion", "supertrend_follow")
StrategyName = Literal["ema_rsi_baseline", "donchian_breakout", "bollinger_reversion", "supertrend_follow"]


def adx_approx(b: pd.DataFrame, period: int = 14) -> pd.Series:
    """ADX con suavizado rolling y sin desplazamientos hacia el futuro."""
    up = b.High.diff()
    down = -b.Low.diff()
    plus = up.where((up > down) & (up > 0), 0.0)
    minus = down.where((down > up) & (down > 0), 0.0)
    prev = b.Close.shift(1)
    tr = pd.concat([b.High - b.Low, (b.High - prev).abs(),
                    (b.Low - prev).abs()], axis=1).max(axis=1)
    tr_sm = tr.rolling(period, min_periods=period).sum().replace(0, np.nan)
    pdi = 100 * plus.rolling(period, min_periods=period).sum() / tr_sm
    mdi = 100 * minus.rolling(period, min_periods=period).sum() / tr_sm
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.rolling(period, min_periods=period).mean()


def supertrend_direction(b: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.Series:
    """Estado Supertrend causal basado en ATR y bandas finales del cierre anterior."""
    prev = b.Close.shift(1)
    tr = pd.concat([b.High-b.Low,(b.High-prev).abs(),(b.Low-prev).abs()],axis=1).max(axis=1)
    atr = tr.rolling(period, min_periods=period).mean().to_numpy(dtype=float)
    median = ((b.High+b.Low)/2).to_numpy(dtype=float)
    close = b.Close.to_numpy(dtype=float)
    up = median + multiplier*atr
    dn = median - multiplier*atr
    final_up = np.full(len(b),np.nan)
    final_dn = np.full(len(b),np.nan)
    direction = np.zeros(len(b),dtype=int)
    for i in range(len(b)):
        if not np.isfinite(atr[i]):
            continue
        if i==0 or direction[i-1]==0:
            final_up[i] = up[i]
            final_dn[i] = dn[i]
            direction[i] = 1 if close[i] >= median[i] else -1
            continue
        final_up[i] = up[i] if up[i] < final_up[i-1] or close[i-1] > final_up[i-1] else final_up[i-1]
        final_dn[i] = dn[i] if dn[i] > final_dn[i-1] or close[i-1] < final_dn[i-1] else final_dn[i-1]
        if close[i] > final_up[i-1]:
            direction[i]=1
        elif close[i] < final_dn[i-1]:
            direction[i]=-1
        else:
            direction[i]=direction[i-1]
    return pd.Series(direction,index=b.index,name="supertrend_direction")


def generate_signals(base:pd.DataFrame,strategy:str,point:float) -> pd.DataFrame:
    """Entrada M15 en siguiente apertura; la tendencia H1 ya viene alineada.

    base = salida de scripts.investigar_admirals_v2.causal_indicators, donde
    h1_direction se calcula solo a partir de barras H1 cerradas.
    """
    if strategy not in STRATEGIES:
        raise ValueError(f"Estrategia desconocida: {strategy}")
    if point<=0:
        raise ValueError("point debe ser positivo")
    expected={"Open","High","Low","Close","Spread","atr","atr_ratio","rsi","ema20","ema50","h1_direction","signal"}
    if not expected.issubset(base.columns):
        raise ValueError(f"Faltan indicadores: {sorted(expected-set(base.columns))}")
    b=base.copy()
    if strategy=="ema_rsi_baseline":
        b["direction"]=b["signal"].astype(int)
        return b
    c=b.Close
    liquid = b["atr"].notna() & (b.atr>0) & (b.Spread>0) & ((b.Spread*point/b.atr)<.15)
    liquid &= b.h1_direction.notna()
    b["signal"]=0
    if strategy=="donchian_breakout":
        hi=b.High.shift(1).rolling(20,min_periods=20).max()
        lo=b.Low.shift(1).rolling(20,min_periods=20).min()
        buy=liquid & (c>hi) & (b.h1_direction==1) & (b.atr_ratio>=.8)
        sell=liquid & (c<lo) & (b.h1_direction==-1) & (b.atr_ratio>=.8)
    elif strategy=="bollinger_reversion":
        avg=c.rolling(20,min_periods=20).mean()
        dev=c.rolling(20,min_periods=20).std(ddof=0)
        lower=avg-2*dev
        upper=avg+2*dev
        adx=adx_approx(b)
        buy=liquid & (c<lower) & (b.rsi<=35) & (adx<25)
        sell=liquid & (c>upper) & (b.rsi>=65) & (adx<25)
    else:
        trend=supertrend_direction(b)
        before=trend.shift(1)
        buy=liquid & (trend==1) & (before==-1) & (b.h1_direction==1) & (b.atr_ratio>=.8)
        sell=liquid & (trend==-1) & (before==1) & (b.h1_direction==-1) & (b.atr_ratio>=.8)
    b.loc[buy.fillna(False),"signal"]=1
    b.loc[sell.fillna(False),"signal"]=-1
    b["direction"]=b.signal
    return b
