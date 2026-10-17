"""Comprobaciones de integridad sin corregir silenciosamente los CSV."""
from __future__ import annotations
from dataclasses import dataclass, field
import pandas as pd

SECONDS = {"M15": 900, "H1": 3600, "D1": 86400}

class DataQualityError(ValueError):
    pass

@dataclass
class QualityReport:
    rows: int
    timeframe: str
    start: str
    end: str
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    hourly_intervals: int = 0
    daily_intervals: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        return vars(self).copy() | {"ok": self.ok}

def validate_bars(df: pd.DataFrame, timeframe: str) -> QualityReport:
    if timeframe not in SECONDS:
        raise ValueError("Timeframe desconocido: usa M15, H1 o D1")
    report = QualityReport(len(df), timeframe, str(df.index.min()), str(df.index.max()))
    if len(df) < 250:
        report.errors.append("Histórico demasiado corto: se exigen al menos 250 barras")
    for col in ["Open", "High", "Low", "Close"]:
        if col not in df:
            report.errors.append(f"Falta columna obligatoria {col}")
    if report.errors:
        return report
    if df.index.hasnans:
        report.errors.append("Hay marcas de tiempo vacías")
    if df.index.has_duplicates:
        report.errors.append("Hay timestamps duplicados")
    if not df.index.is_monotonic_increasing:
        report.errors.append("Las fechas no están ordenadas cronológicamente")
    o,h,l,c = (df[x] for x in ("Open","High","Low","Close"))
    if df[["Open","High","Low","Close"]].isna().any().any():
        report.errors.append("Existen precios OHLC vacíos o no numéricos")
    if (df[["Open","High","Low","Close"]] <= 0).any().any():
        report.errors.append("Existen precios no positivos")
    if ((h < o) | (h < c) | (h < l) | (l > o) | (l > c)).any():
        report.errors.append("OHLC inconsistente: high/low no contienen open/close")
    if "Spread" in df and (df["Spread"].dropna() < 0).any():
        report.errors.append("Spread negativo")
    if not isinstance(df.index, pd.DatetimeIndex):
        report.errors.append("Se requiere DatetimeIndex")
        return report
    if len(df) > 1:
        gaps = df.index.to_series().diff().dt.total_seconds().iloc[1:]
        if (gaps <= 0).any():
            report.errors.append("Hay intervalos temporales no positivos")
        base = SECONDS[timeframe]
        if ((gaps > 0) & (gaps < base)).any():
            report.errors.append(f"Detectados intervalos menores al timeframe {timeframe}")
        report.hourly_intervals = int((gaps == 3600).sum())
        report.daily_intervals = int((gaps == 86400).sum())
        if timeframe == "H1" and report.hourly_intervals >= 10 and report.daily_intervals >= 10:
            report.errors.append("Mezcla probable de barras H1 y D1: se observan secuencias de saltos 1h y 24h")
        if timeframe == "M15" and (gaps == 3600).sum() > 30 and (gaps == 900).sum() > 30:
            report.warnings.append("Muchos saltos de 1h en M15; revisar sesiones de mercado y huecos")
        if (gaps > 4*base).sum() > 0:
            report.warnings.append(f"Hay {int((gaps > 4*base).sum())} huecos >4 velas; verificar sesiones")
    if df.index.tz is None:
        report.warnings.append("Fechas sin zona horaria: origen no verificado; no usar para filtros UTC hasta documentarlo")
    if "Spread" not in df or df["Spread"].isna().all():
        report.warnings.append("Sin spread histórico: requerirá spread fijo explícito")
    return report
