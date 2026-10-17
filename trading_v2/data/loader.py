"""Lectura de CSV de broker y Yahoo sin asumir una zona horaria."""
from __future__ import annotations
from pathlib import Path
import pandas as pd
from .validator import validate_bars, DataQualityError, QualityReport

def load_csv(path: str | Path, timeframe: str) -> tuple[pd.DataFrame, QualityReport]:
    frame = pd.read_csv(path)
    time_candidates = [k for k in ("Time", "Datetime", "Date", "timestamp") if k in frame.columns]
    time_col = time_candidates[0] if time_candidates else frame.columns[0]
    frame[time_col] = pd.to_datetime(frame[time_col], errors="coerce", utc=False)
    frame = frame.set_index(time_col)
    frame.index.name = "Time"
    for col in ("Open", "High", "Low", "Close", "Spread"):
        if col in frame:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    quality = validate_bars(frame, timeframe)
    if not quality.ok:
        raise DataQualityError("; ".join(quality.errors))
    return frame, quality
