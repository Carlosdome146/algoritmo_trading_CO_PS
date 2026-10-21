"""Opening Range Breakout (ORB) intradia M5 - SOLO SEÑALES OFFLINE.

El ORB de 15/30 minutos construye el rango de apertura; NO entra cada 15/30m.
Timestamp de cada vela = apertura de M5 en UTC. Señal AL CIERRE de la vela;
su ejecución simulada solo puede ser al inicio de la vela M5 siguiente.
Cambio de hora europeo y estadounidense calculado mediante zoneinfo.
No conecta a MetaTrader5 ni envia ordenes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone, timedelta
from zoneinfo import ZoneInfo
import math
import numpy as np
import pandas as pd

SESSIONS = {
    "GERMANY40": ("Europe/Berlin", 9, 0),  # Apertura Xetra, hora alemana
    "[SP500]": ("America/New_York", 9, 30),  # Apertura cash EEUU
    "[DJI30]": ("America/New_York", 9, 30),
    "US100": ("America/New_York", 9, 30),
    # EURUSD y GOLD: sesiones con distintas definiciones, fuera del ORB indices inicial
}

@dataclass(frozen=True)
class ORBConfig:
    symbol: str
    range_minutes: int = 15
    mode: str = "breakout"       # breakout o retest confirmado
    entry_window_minutes: int = 120  # fin de búsqueda desde la apertura
    buffer_atr: float = 0.05
    min_range_atr: float = 0.5
    max_range_atr: float = 8.0
    max_signals_per_session: int = 2
    cooldown_bars: int = 3

    def __post_init__(self) -> None:
        if self.symbol not in SESSIONS:
            raise ValueError("ORB inicial disponible solo para indices soportados: " + repr(self.symbol))
        if self.range_minutes not in (15, 30):
            raise ValueError("El ORB solo admite 15 o 30 minutos")
        if self.mode not in ("breakout", "retest"):
            raise ValueError("Modo de ORB desconocido")
        if self.entry_window_minutes < self.range_minutes + 5 or self.entry_window_minutes > 360:
            raise ValueError("Ventana de entrada invalida")
        if self.buffer_atr < 0 or self.min_range_atr < 0 or self.max_range_atr <= self.min_range_atr:
            raise ValueError("Rango ATR/buffer invalido")
        if self.max_signals_per_session < 1 or self.cooldown_bars < 1:
            raise ValueError("Cuotas/cooldown invalidos")


def market_open_utc(symbol: str, day: date) -> pd.Timestamp:
    """Hora real de apertura local de la bolsa, convertida a UTC con DST."""
    if symbol not in SESSIONS:
        raise ValueError("Simbolo no soportado")
    zone, hour, minute = SESSIONS[symbol]
    local_dt = datetime.combine(day, time(hour=hour, minute=minute), tzinfo=ZoneInfo(zone))
    return pd.Timestamp(local_dt.astimezone(timezone.utc))


def validate_m5(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df.index, pd.DatetimeIndex) or df.index.tz is None:
        raise ValueError("Se requiere DatetimeIndex M5 aware UTC")
    if df.empty or df.index.has_duplicates or not df.index.is_monotonic_increasing:
        raise ValueError("M5 vacio, duplicado o sin orden cronologico")
    if not {"Open","High","Low","Close","Spread"}.issubset(df):
        raise ValueError("CSV M5 sin campos OHLC o Spread")
    b=df.copy()
    b.index=b.index.tz_convert("UTC")
    # Spread=0 en CSV MT5 no implica negociar gratis: dato desconocido.
    # No usamos ni propagamos nunca información de spreads futuros.
    raw_col = "SpreadRaw" if "SpreadRaw" in b.columns else "Spread"
    for col in ("Open", "High", "Low", "Close", raw_col):
        b[col] = pd.to_numeric(b[col], errors="raise")
        if not np.isfinite(b[col].to_numpy(dtype=float)).all():
            raise ValueError(f"{col}: valores no finitos")
    if (b[["Open","High","Low","Close"]] <= 0).any().any():
        raise ValueError("OHLC: precios no positivos")
    raw = b[raw_col].astype(float)
    if (raw < 0).any():
        raise ValueError("Spread: valores negativos, exportación inválida")
    b["SpreadRaw"] = raw
    b["SpreadMissing"] = raw.eq(0)
    # Estimación conservadora solo para estudio exploratorio: percentil 75
    # de los spread POSITIVOS observados en hasta 288 barras ANTERIORES.
    # Hasta tener 8 observaciones positivas históricas se deja NaN y se
    # prohíbe abrir o simular trades en esas barras.
    past_positive = raw.where(raw > 0).shift(1)
    estimate = past_positive.rolling(288, min_periods=8).quantile(.75)
    b["Spread"] = raw.where(raw > 0, estimate)
    b["SpreadUsable"] = b["Spread"].notna() & (b["Spread"] > 0)
    b["SpreadImputed"] = b["SpreadMissing"] & b["SpreadUsable"]
    if ((b.High < b[["Open","Close","Low"]].max(axis=1)) |
        (b.Low > b[["Open","Close"]].min(axis=1))).any():
        raise ValueError("OHLC inconsistente")
    intervals = b.index.to_series().diff().dropna().dt.total_seconds()
    if (intervals<300).any() or (intervals % 300 != 0).any():
        raise ValueError("Series que no respetan cuadricula M5")
    return b


def add_orb_indicators(df: pd.DataFrame) -> pd.DataFrame:
    b=validate_m5(df)
    prev=b.Close.shift(1)
    tr=pd.concat([b.High-b.Low,(b.High-prev).abs(),(b.Low-prev).abs()],axis=1).max(axis=1)
    b["atr14"]=tr.rolling(14,min_periods=14).mean()
    return b


def generate_orb_signals(df:pd.DataFrame, cfg:ORBConfig, point:float) -> pd.DataFrame:
    """Señales causales; no usa max/min de velas posteriores.

    Días sin la totalidad de barras M5 de apertura se descartan; no se
    suponen intervalos faltantes. Los límites de la sesión son en horario
    local y los niveles ORB solo quedan disponibles al terminar el rango.
    """
    if not math.isfinite(point) or point<=0:
        raise ValueError("point debe ser positivo")
    b=add_orb_indicators(df)
    b["signal"]=0
    b["orb_high"]=np.nan
    b["orb_low"]=np.nan
    b["orb_ready"]=False
    b["orb_session"]=pd.Series(pd.NaT,index=b.index,dtype="datetime64[ns, UTC]")
    zone=SESSIONS[cfg.symbol][0]
    local_days=b.index.tz_convert(zone).date
    days=sorted(set(local_days))
    bars_orb=cfg.range_minutes//5
    delta=pd.Timedelta(minutes=5)
    for day in days:
        if day.weekday()>=5:
            continue
        op=market_open_utc(cfg.symbol,day)
        end=op+pd.Timedelta(minutes=cfg.range_minutes)
        last_start=op+pd.Timedelta(minutes=cfg.entry_window_minutes)-delta
        expected=pd.date_range(start=op,periods=bars_orb,freq="5min",tz="UTC")
        if not expected.isin(b.index).all():
            continue
        rg=b.loc[expected]
        hi=float(rg.High.max());lo=float(rg.Low.min())
        width=hi-lo
        if width<=0:
            continue
        available=b.index[(b.index>=end)&(b.index<=last_start)]
        if len(available)==0:
            continue
        b.loc[available,"orb_high"]=hi
        b.loc[available,"orb_low"]=lo
        b.loc[available,"orb_ready"]=True
        b.loc[available,"orb_session"]=op
        count=0;last_i=-10000
        long_armed=False;short_armed=False
        for ts in available:
            i=int(b.index.get_loc(ts))
            if i<14 or i<=last_i+cfg.cooldown_bars-1:
                continue
            # Proteger frente a huecos dentro de la ventana de entrada.
            if i==0 or b.index[i-1]!=ts-delta:
                long_armed=short_armed=False
                continue
            atr=float(b["atr14"].iloc[i])
            if not math.isfinite(atr) or atr<=0 or not cfg.min_range_atr<=width/atr<=cfg.max_range_atr:
                continue
            # Sin spread utilizable no hay señal. Imputados solo con
            # spread positivo observado ANTES de esta vela.
            if not bool(b.SpreadUsable.iloc[i]):
                continue
            spread=float(b.Spread.iloc[i])*point
            if spread / atr >= .15:
                continue
            buffer=cfg.buffer_atr*atr
            close=float(b.Close.iloc[i])
            previous=float(b.Close.iloc[i-1])
            upper=hi+buffer;lower=lo-buffer
            long_break=(close>upper and previous<=upper)
            short_break=(close<lower and previous>=lower)
            direction=0
            if cfg.mode=="breakout":
                if long_break:
                    direction=1
                elif short_break:
                    direction=-1
            else:
                # Un cierre fuera del ORB en una vela ANTERIOR arma el retest.
                # No usar el futuro ni declarar retest en la vela de ruptura.
                if long_armed and float(b.Low.iloc[i])<=hi and close>upper:
                    direction=1
                elif short_armed and float(b.High.iloc[i])>=lo and close<lower:
                    direction=-1
                if long_break:
                    long_armed=True
                    short_armed=False
                elif short_break:
                    short_armed=True
                    long_armed=False
            if direction:
                b.at[ts,"signal"]=direction
                count+=1;last_i=i
                if cfg.mode=="retest":
                    long_armed=short_armed=False
                if count>=cfg.max_signals_per_session:
                    break
    return b
