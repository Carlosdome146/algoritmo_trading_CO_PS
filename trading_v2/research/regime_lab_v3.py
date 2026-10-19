"""Laboratorio V3: estrategias diarias robustas con filtro de régimen (OFFLINE, sin órdenes).

Principios anti-sobreajuste (lección aprendida en V2 M15):
1. Parámetros CANÓNICOS fijados a priori (literatura), sin optimización sobre los datos.
2. Número de pruebas contabilizado y umbral de significación corregido (Bonferroni).
3. Robustez por vecindad de parámetros: se exige que la mayoría de vecinos también gane.
4. Validación temporal: Descubrimiento (70 % antiguo) vs Confirmación (30 % reciente) y
   desglose por año natural.
5. Costes conservadores: max(spread de la vela, spread mediano reciente) + 0.5x spread de
   deslizamiento por lado + swap overnight (modo 5: % anual del nominal, por noche natural).

Ejecución causal:
- La señal se calcula al CIERRE de la vela t y se ejecuta en la APERTURA de t+1.
- El stop de catástrofe se evalúa intradía (Low/High); un gap a través del stop se ejecuta
  a la apertura. Las salidas por regla se calculan al cierre y se ejecutan en la apertura siguiente.
"""
from __future__ import annotations

import io
import math
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

from trading_v2.backtesting.contract_specs import get_contract_spec

INDICES = ("DAX40", "SP500", "DOW30", "NASDAQ100", "NIKKEI225")
MARKET_SYMBOL = {
    "DAX40": "GERMANY40",
    "SP500": "[SP500]",
    "DOW30": "[DJI30]",
    "NASDAQ100": "US100",
    "NIKKEI225": "[JP225]",
    "GOLD": "GOLD",
    "EURUSD": "EURUSD",
}


# --------------------------------------------------------------------------------------
# Datos
# --------------------------------------------------------------------------------------
def load_long_history(path: str | Path, market: str, timeframe: str = "D1") -> pd.DataFrame:
    with zipfile.ZipFile(path) as z:
        raw = z.read(f"ADMIRALS_{market}_{timeframe}.csv").decode("utf-8")
    df = pd.read_csv(io.StringIO(raw), parse_dates=["Time"]).set_index("Time").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    if (df[["Open", "High", "Low", "Close"]] <= 0).any().any():
        raise ValueError(f"Precios no positivos en {market} {timeframe}")
    return df


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    c, h, l = out["Close"], out["High"], out["Low"]
    prev_c = c.shift(1)
    tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    out["atr20"] = tr.rolling(20).mean()
    out["atr_regime"] = out["atr20"] / out["atr20"].rolling(250, min_periods=120).median()
    for n in (5, 20, 50, 100, 150, 200, 250):
        out[f"sma{n}"] = c.rolling(n).mean()
    bb_std20 = c.rolling(20).std(ddof=0)
    out["bb_lower_18"] = out["sma20"] - 1.8 * bb_std20
    out["bb_upper_18"] = out["sma20"] + 1.8 * bb_std20
    out["bb_lower_20"] = out["sma20"] - 2.0 * bb_std20
    out["bb_upper_20"] = out["sma20"] + 2.0 * bb_std20
    
    # Kaufman Efficiency Ratio (10 barras): ruido vs dirección macro
    change_10 = (c - c.shift(10)).abs()
    sum_diffs_10 = c.diff().abs().rolling(10).sum()
    out["ker10"] = change_10 / sum_diffs_10.replace(0, np.nan)

    delta = c.diff()
    for n in (2, 3):
        up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
        dn = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
        out[f"rsi{n}"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    rng = (h - l).replace(0, np.nan)
    out["ibs"] = (c - l) / rng
    out["roc63"] = c / c.shift(63) - 1
    out["prev_high"] = h.shift(1)
    return out


# --------------------------------------------------------------------------------------
# Estrategias (parámetros canónicos)
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class StrategySpec:
    name: str
    markets: tuple[str, ...]
    side: str  # "long" | "both"
    params: dict = field(default_factory=dict)
    stop_atr: float = 2.5
    max_bars: int = 10
    regime_cap: float | None = None  # bloquear entradas si atr_regime > cap


def entry_exit_signals(d: pd.DataFrame, s: StrategySpec) -> tuple[pd.Series, pd.Series]:
    """Devuelve (entrada {-1,0,1}, salida_por_regla bool) evaluadas al CIERRE de cada vela."""
    p = s.params
    c = d["Close"]
    if s.name.startswith("idx_rsi2_dip"):
        sma = d[f"sma{p.get('sma', 200)}"]
        entry = ((c > sma) & (d["rsi2"] < p.get("rsi_th", 10))).astype(int)
        exit_rule = c > d["sma5"]
    elif s.name.startswith("idx_ibs_dip"):
        sma = d[f"sma{p.get('sma', 200)}"]
        entry = ((c > sma) & (d["ibs"] < p.get("ibs_th", 0.2))).astype(int)
        exit_rule = c > d["prev_high"]
    elif s.name.startswith("tsmom"):
        sma = d[f"sma{p.get('sma', 200)}"]
        long_ = (c > sma) & (d["roc63"] > 0)
        short_ = (c < sma) & (d["roc63"] < 0)
        entry = long_.astype(int) - short_.astype(int)
        exit_rule = pd.Series(False, index=d.index)  # salida por cambio de estado (ver simulador)
    elif s.name.startswith("turn_of_month"):
        idx = d.index
        month_end = (idx + pd.offsets.MonthEnd(0)).normalize()
        bdays_left = np.busday_count(idx.values.astype("datetime64[D]"), month_end.values.astype("datetime64[D]"))
        entry = pd.Series((bdays_left <= p.get("days_before", 1)).astype(int), index=idx)
        entry &= c > d[f"sma{p.get('sma', 200)}"] if p.get("trend_filter") else True
        entry = entry.astype(int)
        dom_rank = idx.to_series().groupby([idx.year, idx.month]).cumcount() + 1
        exit_rule = pd.Series((dom_rank.values >= p.get("exit_day", 3)) & (bdays_left > 5), index=idx)
    elif s.name.startswith("idx_dax_bollinger_dip"):
        sma = d[f"sma{p.get('sma', 200)}"]
        sigma = p.get("sigma", 1.8)
        bb_mid = d["sma20"] if "sma20" in d else d["Close"].rolling(20).mean()
        bb_std = d["Close"].rolling(20).std(ddof=0)
        bb_lower = bb_mid - sigma * bb_std
        entry = ((c > sma) & (d["rsi2"] < p.get("rsi_th", 15)) & (c <= bb_lower)).astype(int)
        exit_rule = c > d["sma5"]
    elif s.name.startswith("fx_eurusd_ker_exhaustion"):
        ker_cap = p.get("ker_cap", 0.42)
        rsi_th = p.get("rsi_th", 8)
        sigma = p.get("sigma", 2.0)
        bb_mid = d["sma20"] if "sma20" in d else d["Close"].rolling(20).mean()
        bb_std = d["Close"].rolling(20).std(ddof=0)
        bb_lo = bb_mid - sigma * bb_std
        bb_up = bb_mid + sigma * bb_std
        is_ranging = (d["ker10"] < ker_cap) if "ker10" in d else pd.Series(True, index=d.index)
        long_sig = is_ranging & (d["rsi2"] < rsi_th) & (c <= bb_lo)
        short_sig = is_ranging & (d["rsi2"] > (100 - rsi_th)) & (c >= bb_up)
        entry = long_sig.astype(int) - short_sig.astype(int)
        exit_rule = c > d["sma5"]
    else:
        raise ValueError(f"Estrategia desconocida: {s.name}")
    if s.side == "long":
        entry = entry.clip(lower=0)
    if s.regime_cap is not None:
        entry = entry.where(d["atr_regime"].fillna(1.0) <= s.regime_cap, 0)
    return entry.fillna(0).astype(int), exit_rule.fillna(False).astype(bool)


# --------------------------------------------------------------------------------------
# Simulador diario causal con costes
# --------------------------------------------------------------------------------------
def simulate_daily(
    d: pd.DataFrame,
    s: StrategySpec,
    market: str,
    slip_mult: float = 0.5,
    entry_mode: str = "market",
    limit_offset_atr: float = 0.0,
) -> pd.DataFrame:
    spec = get_contract_spec(MARKET_SYMBOL[market])
    point = spec.point
    recent_med_spread = float(d["Spread"].iloc[-250:].replace(0, np.nan).median())
    cost_spread = np.maximum(d["Spread"].to_numpy(dtype=float), recent_med_spread) * point
    entry_sig, exit_rule = entry_exit_signals(d, s)
    o, h, l, c = (d[k].to_numpy(dtype=float) for k in ("Open", "High", "Low", "Close"))
    atr = d["atr20"].to_numpy(dtype=float)
    es, ex = entry_sig.to_numpy(), exit_rule.to_numpy()
    idx = d.index
    trades = []
    i, n = 250, len(d)
    while i < n - 1:
        side = int(es[i])
        if side == 0 or not math.isfinite(atr[i]) or atr[i] <= 0:
            i += 1
            continue
        k = i + 1  # entrada en k
        spr = cost_spread[k]
        if entry_mode == "market":
            entry = o[k] + (spr if side == 1 else 0.0) + side * spr * slip_mult
        elif entry_mode == "limit_close":
            limit_target = c[i]
            if side == 1:
                if l[k] > limit_target:
                    i += 1
                    continue
                fill_raw = min(o[k], limit_target)
                entry = fill_raw + spr + spr * slip_mult
            else:
                if h[k] < limit_target:
                    i += 1
                    continue
                fill_raw = max(o[k], limit_target)
                entry = fill_raw - spr * slip_mult
        elif entry_mode == "limit_discount":
            limit_target = o[k] - side * limit_offset_atr * atr[i]
            if side == 1:
                if l[k] > limit_target:
                    i += 1
                    continue
                fill_raw = limit_target
                entry = fill_raw + spr + spr * slip_mult
            else:
                if h[k] < limit_target:
                    i += 1
                    continue
                fill_raw = limit_target
                entry = fill_raw - spr * slip_mult
        else:
            raise ValueError(f"Modo de entrada desconocido: {entry_mode}")

        stop_dist = s.stop_atr * atr[i]
        stop = entry - side * stop_dist
        exit_px, reason, j = None, "TIME", k
        for j in range(k, min(n, k + s.max_bars)):
            spr_j = cost_spread[j]
            ex_o = o[j] + (spr_j if side == -1 else 0.0)
            ex_l = l[j] + (spr_j if side == -1 else 0.0)
            ex_h = h[j] + (spr_j if side == -1 else 0.0)
            if j > k and ((side == 1 and ex_o <= stop) or (side == -1 and ex_o >= stop)):
                exit_px, reason = ex_o - side * spr_j * slip_mult, "GAP_STOP"
                break
            if (side == 1 and ex_l <= stop) or (side == -1 and ex_h >= stop):
                exit_px, reason = stop - side * spr_j * slip_mult, "STOP"
                break
            if s.name.startswith("fx_"):
                rule = (c[j] > d["sma5"].iloc[j]) if side == 1 else (c[j] < d["sma5"].iloc[j])
            elif s.name.startswith("tsmom"):
                rule = (es[j] != side)
            else:
                rule = ex[j]
            if rule and j + 1 < n:
                spr_n = cost_spread[j + 1]
                exit_px = o[j + 1] + (spr_n if side == -1 else 0.0) - side * spr_n * slip_mult
                reason, j = "RULE", j + 1
                break
        if exit_px is None:
            j = min(n - 1, k + s.max_bars - 1)
            if j + 1 < n:
                spr_n = cost_spread[j + 1]
                exit_px = o[j + 1] + (spr_n if side == -1 else 0.0) - side * spr_n * slip_mult
                j = j + 1
            else:
                exit_px = c[j] + (cost_spread[j] if side == -1 else 0.0)
        nights = max(0, (idx[j].normalize() - idx[k].normalize()).days)
        rate = spec.swap_long if side == 1 else spec.swap_short
        swap_price = entry * (rate / 100.0) / 360.0 * nights if spec.swap_mode == 5 else rate * point * nights
        pnl_price = side * (exit_px - entry) + swap_price
        trades.append({
            "signal_time": idx[i], "entry_time": idx[k], "exit_time": idx[j], "side": side,
            "r": pnl_price / stop_dist, "swap_r": swap_price / stop_dist, "bars": j - k + 1, "reason": reason,
        })
        i = j  # sin solapamiento: la siguiente señal se evalúa desde la vela de salida
    return pd.DataFrame(trades)


# --------------------------------------------------------------------------------------
# Métricas
# --------------------------------------------------------------------------------------
def wilson_lb(wins: int, n: int, z: float = 1.6448536) -> float:
    if n == 0:
        return 0.0
    p = wins / n
    den = 1 + z * z / n
    centre = p + z * z / (2 * n)
    adj = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return 100 * (centre - adj) / den


def metrics(r: np.ndarray) -> dict:
    n = len(r)
    if n == 0:
        return {"n": 0}
    wins = int((r > 0).sum())
    gw, gl = r[r > 0].sum(), -r[r < 0].sum()
    eq = np.cumsum(r)
    dd = float((np.maximum.accumulate(np.concatenate([[0], eq]))[1:] - eq).max())
    sd = r.std(ddof=1) if n > 1 else 0.0
    q = np.sort(r)[: max(1, int(math.ceil(0.05 * n)))]
    return {
        "n": n,
        "win_rate": round(100 * wins / n, 1),
        "wilson_lb90": round(wilson_lb(wins, n), 1),
        "mean_r": round(float(r.mean()), 4),
        "profit_factor": round(float(gw / gl), 3) if gl > 0 else None,
        "t_stat": round(float(r.mean() / (sd / math.sqrt(n))), 2) if sd > 0 else None,
        "max_dd_r": round(dd, 2),
        "cvar5_r": round(float(q.mean()), 3),
    }


def evaluate(trades: pd.DataFrame, split_frac: float = 0.70) -> dict:
    if trades.empty:
        return {"all": {"n": 0}, "discovery": {"n": 0}, "confirmation": {"n": 0}, "years": {}}
    t0, t1 = trades["entry_time"].iloc[0], trades["entry_time"].iloc[-1]
    cut = t0 + (t1 - t0) * split_frac
    years = {
        int(y): metrics(g["r"].to_numpy()) for y, g in trades.groupby(trades["entry_time"].dt.year)
    }
    pos_years = [y for y, m in years.items() if m["n"] >= 3 and m["mean_r"] > 0]
    valid_years = [y for y, m in years.items() if m["n"] >= 3]
    return {
        "all": metrics(trades["r"].to_numpy()),
        "discovery": metrics(trades.loc[trades["entry_time"] < cut, "r"].to_numpy()),
        "confirmation": metrics(trades.loc[trades["entry_time"] >= cut, "r"].to_numpy()),
        "split_time": str(cut),
        "pct_positive_years": round(100 * len(pos_years) / len(valid_years), 1) if valid_years else None,
        "years": years,
        "avg_bars": round(float(trades["bars"].mean()), 2),
        "avg_swap_r": round(float(trades["swap_r"].mean()), 4),
        "exit_reasons": trades["reason"].value_counts().to_dict(),
    }


def bonferroni_t(n_trials: int, alpha: float = 0.05) -> float:
    return NormalDist().inv_cdf(1 - alpha / max(1, n_trials))


# --------------------------------------------------------------------------------------
# Registro previo de estrategias + vecindades de robustez
# --------------------------------------------------------------------------------------
def canonical_strategies() -> list[StrategySpec]:
    return [
        StrategySpec("idx_rsi2_dip", INDICES, "long", {"sma": 200, "rsi_th": 10}, stop_atr=2.5, max_bars=10),
        StrategySpec("idx_rsi2_dip_regime", INDICES, "long", {"sma": 200, "rsi_th": 10}, stop_atr=2.5, max_bars=10, regime_cap=1.8),
        StrategySpec("idx_ibs_dip", INDICES, "long", {"sma": 200, "ibs_th": 0.2}, stop_atr=2.5, max_bars=5),
        StrategySpec("turn_of_month", INDICES, "long", {"days_before": 1, "exit_day": 3, "sma": 200, "trend_filter": False}, stop_atr=3.0, max_bars=8),
        StrategySpec("tsmom", tuple(MARKET_SYMBOL), "both", {"sma": 200}, stop_atr=3.0, max_bars=60),
        StrategySpec("idx_dax_bollinger_dip", ("DAX40",), "long", {"sma": 200, "rsi_th": 15, "sigma": 1.8}, stop_atr=2.5, max_bars=10),
        StrategySpec("fx_eurusd_ker_exhaustion", ("EURUSD",), "both", {"ker_cap": 0.42, "rsi_th": 8, "sigma": 2.5}, stop_atr=2.5, max_bars=8),
    ]


def neighbours(s: StrategySpec) -> list[StrategySpec]:
    out = []
    if s.name.startswith("idx_rsi2_dip"):
        for sma in (150, 200, 250):
            for th in (5, 10, 15):
                for st in (2.0, 2.5, 3.0):
                    out.append(StrategySpec(s.name, s.markets, s.side, {"sma": sma, "rsi_th": th}, st, s.max_bars, s.regime_cap))
    elif s.name.startswith("idx_ibs_dip"):
        for sma in (150, 200, 250):
            for th in (0.15, 0.2, 0.25):
                for st in (2.0, 2.5, 3.0):
                    out.append(StrategySpec(s.name, s.markets, s.side, {"sma": sma, "ibs_th": th}, st, s.max_bars))
    elif s.name.startswith("turn_of_month"):
        for db in (1, 2, 3):
            for ed in (2, 3, 4):
                out.append(StrategySpec(s.name, s.markets, s.side, {**s.params, "days_before": db, "exit_day": ed}, s.stop_atr, s.max_bars))
    elif s.name.startswith("tsmom"):
        for sma in (100, 150, 200, 250):
            for st in (2.5, 3.0, 4.0):
                out.append(StrategySpec(s.name, s.markets, s.side, {"sma": sma}, st, s.max_bars))
    elif s.name.startswith("idx_dax_bollinger_dip"):
        for sma in (150, 200, 250):
            for th in (10, 15, 20):
                for sig in (1.5, 1.8, 2.0):
                    for st in (2.0, 2.5, 3.0):
                        out.append(StrategySpec(s.name, s.markets, s.side, {"sma": sma, "rsi_th": th, "sigma": sig}, st, s.max_bars))
    elif s.name.startswith("fx_eurusd_ker_exhaustion"):
        for kc in (0.38, 0.42, 0.45):
            for th in (6, 8, 10):
                for sig in (2.3, 2.5, 2.7):
                    for st in (2.0, 2.5, 3.0):
                        out.append(StrategySpec(s.name, s.markets, s.side, {"ker_cap": kc, "rsi_th": th, "sigma": sig}, st, s.max_bars))
    return out


def run_lab(path: str | Path, timeframe: str = "D1") -> dict:
    strategies = canonical_strategies()
    n_trials = sum(len(s.markets) for s in strategies)
    t_req = bonferroni_t(n_trials)
    result = {
        "study": "Trading V3 Robust Daily Regime Lab",
        "timeframe": timeframe,
        "pre_registered_trials": n_trials,
        "bonferroni_t_required": round(t_req, 2),
        "markets": {},
    }
    data = {m: add_indicators(load_long_history(path, m, timeframe)) for m in MARKET_SYMBOL}
    for s in strategies:
        for m in s.markets:
            d = data[m]
            ev = evaluate(simulate_daily(d, s, m))
            nb = []
            for ns in neighbours(s):
                nm = evaluate(simulate_daily(d, ns, m))["all"]
                nb.append(nm.get("profit_factor") or 0.0)
            ev["neighbour_pf_gt_1_pct"] = round(100 * float(np.mean([x > 1.0 for x in nb])), 1) if nb else None
            ev["neighbour_pf_median"] = round(float(np.median(nb)), 3) if nb else None
            a, c = ev["all"], ev["confirmation"]
            ev["verdict"] = (
                "ROBUST_CANDIDATE"
                if a.get("n", 0) >= 60
                and (a.get("profit_factor") or 0) >= 1.2
                and (c.get("profit_factor") or 0) >= 1.05
                and (a.get("t_stat") or 0) >= t_req
                and (ev["pct_positive_years"] or 0) >= 60
                and (ev["neighbour_pf_gt_1_pct"] or 0) >= 70
                else "PROMISING" if (a.get("profit_factor") or 0) >= 1.1 and (c.get("profit_factor") or 0) >= 1.0
                and (ev["neighbour_pf_gt_1_pct"] or 0) >= 60
                else "REJECTED"
            )
            ev["spec"] = asdict(s)
            ev["data_range"] = [str(d.index[0]), str(d.index[-1]), len(d)]
            result["markets"].setdefault(m, {})[s.name] = ev
    return result


def main(argv=None):
    import argparse
    import json
    p = argparse.ArgumentParser(description="Laboratorio V3 diario robusto")
    p.add_argument("--zip", default="admirals_historial_largo_local.zip")
    p.add_argument("--out", default="v3_daily_lab_result.json")
    args = p.parse_args(argv)
    res = run_lab(args.zip)
    print("=" * 105)
    print(f"{'MERCADO':<8s} | {'ESTRATEGIA':<22s} | {'N':<4s} | {'WR%':<6s} | {'PF ALL':<7s} | {'PF CONF':<8s} | {'t-stat':<6s} | {'VECINOS>1':<10s} | {'VEREDICTO'}")
    print("-" * 105)
    for m, strats in res["markets"].items():
        for sname, ev in strats.items():
            a = ev["all"]
            c = ev["confirmation"]
            print(
                f"{m:<8s} | {sname:<22s} | {a.get('n', 0):<4d} | "
                f"{str(a.get('win_rate')) + '%':<6s} | "
                f"{str(a.get('profit_factor')):<7s} | "
                f"{str(c.get('profit_factor')):<8s} | "
                f"{str(a.get('t_stat')):<6s} | "
                f"{str(ev.get('neighbour_pf_gt_1_pct')) + '%':<10s} | "
                f"{ev['verdict']}"
            )
    print("=" * 105)
    Path(args.out).write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print(f"Resultado guardado en {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

