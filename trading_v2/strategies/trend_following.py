"""Baseline LONG/SHORT determinista; no entrena con datos futuros."""
from __future__ import annotations
import numpy as np
import pandas as pd

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    close = out["Close"]
    out["ema20"] = close.ewm(span=20, adjust=False).mean()
    out["ema50"] = close.ewm(span=50, adjust=False).mean()
    prev = close.shift(1)
    tr = pd.concat([(out["High"]-out["Low"]), (out["High"]-prev).abs(), (out["Low"]-prev).abs()], axis=1).max(axis=1)
    out["atr"] = tr.rolling(14).mean()
    out["atr_mean"] = out["atr"].rolling(60).mean()
    out["atr_ratio"] = out["atr"] / out["atr_mean"]
    d = close.diff()
    gain = d.clip(lower=0).rolling(14).mean()
    loss = -d.clip(upper=0).rolling(14).mean()
    out["rsi"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    out["signal"] = 0
    good = out[["ema20", "ema50", "atr_ratio", "rsi"]].notna().all(axis=1)
    long_signal = good & (out["ema20"] > out["ema50"]) & (close > out["ema50"]) & out["rsi"].between(42, 68) & (out["atr_ratio"] >= .82)
    short_signal = good & (out["ema20"] < out["ema50"]) & (close < out["ema50"]) & out["rsi"].between(32, 58) & (out["atr_ratio"] >= .82)
    out.loc[long_signal, "signal"] = 1
    out.loc[short_signal, "signal"] = -1
    return out
