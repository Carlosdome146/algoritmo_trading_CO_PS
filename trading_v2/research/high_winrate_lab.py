"""Laboratorio de Alta Tasa de Acierto (V2 Offline, Meta >= 79% Win Rate).

Implementa:
1. Simulación causal M15 Bid/Ask con perfiles de salida de primera pasada,
   Breakeven causal al cierre de barra (sin lookahead intrabar) e invalidación
   temporal en cierre de barra.
2. Ponderación por unicidad temporal (Sample Uniqueness, López de Prado) y
   Meta-Labeling híbrido (Esperanza Neta Ridge + Probabilidad de Impacto Logística)
   con umbrales seleccionados por cuantiles aprendidos exclusivamente en Train.
3. Auditoría estadística mediante el Límite Inferior Binomial de Wilson,
   Probabilistic Sharpe Ratio (PSR) y Expected Shortfall (CVaR 5%).
4. Validación en dos pliegues expansivos (Fold 1: 45-58%, Fold 2: 58-78%) con
   embargo de 40 barras y evaluación única en el Holdout reservado (78-100%).
"""
from __future__ import annotations
from collections import Counter
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import zipfile
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import RobustScaler
from scripts import investigar_admirals_v2 as prior
from trading_v2.backtesting.contract_specs import calculate_lot_size, get_contract_spec
from trading_v2.strategies.precision_microstructure import (
    PRECISION_FEATURES,
    PRECISION_STRATEGIES,
    enrich_microstructure_features,
    generate_precision_signals,
)


@dataclass(frozen=True)
class ExitProfile:
    name: str
    sl_atr: float
    tp_atr: float
    be_trigger_atr: float | None = 0.15
    be_lock_ratio: float = 0.45
    max_adverse_close_bars: int | None = None
    max_adverse_close_atr: float = -0.30

    def __post_init__(self):
        if self.sl_atr <= 0 or self.tp_atr <= 0:
            raise ValueError("sl_atr y tp_atr deben ser positivos")
        if self.be_trigger_atr is not None and self.be_trigger_atr <= 0:
            raise ValueError("be_trigger_atr debe ser positivo o None")
        if not 0.0 <= self.be_lock_ratio < 1.0:
            raise ValueError("be_lock_ratio debe estar en [0, 1)")


EXIT_PROFILES: tuple[ExitProfile, ...] = (
    ExitProfile(
        name="sniper_tight_be",
        sl_atr=1.40,
        tp_atr=0.56,
        be_trigger_atr=0.15,
        be_lock_ratio=0.45,
        max_adverse_close_bars=None,
        max_adverse_close_atr=-0.30,
    ),
    ExitProfile(
        name="sniper_time_guard",
        sl_atr=1.45,
        tp_atr=0.52,
        be_trigger_atr=0.13,
        be_lock_ratio=0.45,
        max_adverse_close_bars=4,
        max_adverse_close_atr=-0.35,
    ),
    ExitProfile(
        name="impulse_time_guard",
        sl_atr=1.35,
        tp_atr=0.52,
        be_trigger_atr=0.14,
        be_lock_ratio=0.45,
        max_adverse_close_bars=3,
        max_adverse_close_atr=-0.28,
    ),
)

HORIZONS: tuple[int, ...] = (12, 16)
QUANTILE_CUTOFFS: tuple[float | None, ...] = (None, 0.50, 0.60, 0.65)


@dataclass(frozen=True)
class HighWinRateLabConfig:
    min_trades_fold: int = 15
    min_trades_final: int = 20
    min_training_events: int = 50
    min_pf: float = 1.10
    min_mean_r: float = 0.02
    min_win_rate: float = 75.0
    target_benchmark_win_rate: float = 79.0
    embargo: int = 40
    risk_fraction: float = 0.0025
    initial_eur: float = 3000.0
    slip_as_spread: float = 0.5

    def __post_init__(self):
        if self.embargo <= max(HORIZONS):
            raise ValueError("El embargo debe superar el horizonte máximo")
        if self.min_trades_fold <= 0 or self.min_trades_final <= 0 or self.min_training_events <= 0:
            raise ValueError("Tamaños muestrales mínimos deben ser positivos")
        if not 0.0 < self.risk_fraction <= 0.01 or self.initial_eur <= 0:
            raise ValueError("Parámetros de capital/riesgo inválidos")
        if self.slip_as_spread < 0:
            raise ValueError("Slippage inválido")
        if not 50.0 <= self.min_win_rate <= 95.0:
            raise ValueError("min_win_rate fuera de rango razonable")


@dataclass(frozen=True)
class MetaSelectorBundle:
    ridge_model: Pipeline
    logistic_model: Pipeline
    train_scores_sorted: np.ndarray

    def threshold_for_quantile(self, q: float | None) -> float | None:
        if q is None:
            return None
        if not 0.0 < q < 1.0:
            raise ValueError("El cuantil debe estar en (0, 1)")
        return float(np.quantile(self.train_scores_sorted, q))

    def score_features(self, x_matrix: np.ndarray) -> np.ndarray:
        exp_r = self.ridge_model.predict(x_matrix)
        prob_hit = self.logistic_model.predict_proba(x_matrix)[:, 1]
        return 0.5 * exp_r + 0.5 * prob_hit


def wilson_lower_bound(wins: int, total: int, z: float = 1.6448536) -> float:
    """Límite inferior del intervalo binomial de Wilson en porcentaje [0, 100]."""
    if total <= 0 or wins < 0 or wins > total:
        return 0.0
    p = wins / total
    z2 = z * z
    denom = 1.0 + z2 / total
    center = p + z2 / (2.0 * total)
    rad = z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * total)) / total)
    lower = max(0.0, (center - rad) / denom)
    return round(100.0 * lower, 3)


def probabilistic_sharpe_ratio(r_values: np.ndarray, sr_benchmark: float = 0.0) -> float | None:
    """Probabilistic Sharpe Ratio (López de Prado) ajustado por asimetría y curtosis."""
    n = len(r_values)
    if n < 5:
        return None
    std = float(np.std(r_values, ddof=1))
    if std <= 1e-12:
        return None
    mean = float(np.mean(r_values))
    sr = mean / std
    z_scores = (r_values - mean) / std
    skew = float(np.mean(z_scores**3))
    kurt = float(np.mean(z_scores**4))
    var_term = max(1e-9, 1.0 - skew * sr + ((kurt - 1.0) / 4.0) * (sr**2))
    sigma_sr = math.sqrt(var_term / (n - 1))
    z_stat = (sr - sr_benchmark) / sigma_sr
    psr = 0.5 * (1.0 + math.erf(z_stat / math.sqrt(2.0)))
    return round(float(psr), 4)


def expected_shortfall_r(r_values: np.ndarray, alpha: float = 0.05) -> float | None:
    """CVaR / Expected Shortfall en múltiplos R del peor alpha% de operaciones."""
    if len(r_values) == 0:
        return None
    cutoff = float(np.quantile(r_values, alpha))
    tail = r_values[r_values <= cutoff]
    return round(float(np.mean(tail)), 4) if len(tail) > 0 else round(cutoff, 4)


def compute_sample_uniqueness_weights(events: list[tuple], total_bars: int) -> np.ndarray:
    """Ponderación por unicidad temporal (Sample Uniqueness) para eventos solapados."""
    if not events:
        return np.array([], dtype=float)
    concurrency = np.zeros(total_bars + 1, dtype=float)
    for ev in events:
        st = max(0, int(ev[0]) + 1)
        en = min(total_bars, int(ev[1]))
        if en >= st:
            concurrency[st : en + 1] += 1.0
    weights = np.ones(len(events), dtype=float)
    for idx, ev in enumerate(events):
        st = max(0, int(ev[0]) + 1)
        en = min(total_bars, int(ev[1]))
        if en >= st:
            c_slice = np.maximum(1.0, concurrency[st : en + 1])
            avg_u = float(np.mean(1.0 / c_slice))
            weights[idx] = avg_u
    mean_w = float(np.mean(weights))
    return weights / mean_w if mean_w > 0 else weights


def simulate_precision_event(
    arr: dict,
    signal_i: int,
    horizon: int,
    point: float,
    slippage_multiplier: float = 0.0,
    profile: ExitProfile = EXIT_PROFILES[0],
) -> tuple[float, int, str]:
    """Simulador causal M15 Bid OHLC con Breakeven al cierre de vela e invalidación temporal.

    Reglas de causalidad estricta:
    1. La entrada ocurre en la apertura de `start = signal_i + 1` (LONG en ASK, SHORT en BID)
       con deslizamiento adverso proporcional al spread de `start`.
    2. Dentro de cada barra `j` (`start <= j <= end`), se evalúan PRIMERO las barreras vigentes
       (`stop` y `target`) contra Open/High/Low ejecutables de `j`:
       - Si la apertura supera el `stop`, ejecuta a precio de apertura desfavorable (`GAP_STOP` / `GAP_PROTECTED_STOP`).
       - Si la barra toca `stop` y `target` en la misma vela, asume SIEMPRE el peor caso (`BOTH_ASSUME_STOP` / `BOTH_ASSUME_PROTECTED_STOP`).
    3. SOLO si la barra `j` termina sin haber tocado ni `stop` ni `target`, al CIERRE de `j`
       se conoce el precio de cierre ejecutable (`exc`) sin mirar el interior futuro:
       - Si el beneficio neto al cierre de `j` supera `be_trigger_atr`, se actualiza el `stop`
         para las barras siguientes (`k >= j + 1`), verificando que el nuevo stop quede en el
         lado ejecutable válido respecto a `exc`.
       - Si aún no se ha activado el Breakeven y tras `max_adverse_close_bars` el cierre sigue
         en pérdida severa (`<= max_adverse_close_atr`), cierra al final de `j` (`TIME_INVALIDATION`).
    """
    d = int(arr["signal"][signal_i])
    atr = float(arr["atr"][signal_i])
    if d not in (-1, 1) or not math.isfinite(atr) or atr <= 0:
        raise ValueError("Señal o ATR inválido")
    if horizon <= 0 or point <= 0 or slippage_multiplier < 0:
        raise ValueError("Parámetros de simulación inválidos")

    start = signal_i + 1
    end = min(len(arr["open"]) - 1, signal_i + horizon)
    if start > end:
        raise ValueError("Sin siguiente vela para ejecutar entrada")
    if np.any(arr["spread"][start : end + 1] <= 0):
        raise ValueError("Spread no positivo durante la ventana de la operación")

    entry_spr = float(arr["spread"][start]) * point
    entry_slip = entry_spr * slippage_multiplier
    entry = float(arr["open"][start]) + (entry_spr if d == 1 else 0.0) + d * entry_slip
    stopdist = profile.sl_atr * atr
    stop = entry - d * stopdist
    target = entry + d * profile.tp_atr * atr

    reason = "TIMEOUT"
    exit_price = None
    be_active = False

    for j in range(start, end + 1):
        bid_o = float(arr["open"][j])
        bid_h = float(arr["high"][j])
        bid_l = float(arr["low"][j])
        bid_c = float(arr["close"][j])
        spr = float(arr["spread"][j]) * point

        exo = bid_o + (spr if d == -1 else 0.0)
        exh = bid_h + (spr if d == -1 else 0.0)
        exl = bid_l + (spr if d == -1 else 0.0)
        exc = bid_c + (spr if d == -1 else 0.0)
        slip = spr * slippage_multiplier

        # 1. Gap adverso en la apertura de la barra j
        if (d == 1 and exo <= stop) or (d == -1 and exo >= stop):
            exit_price = exo - d * slip
            reason = "GAP_PROTECTED_STOP" if be_active else "GAP_STOP"
            break

        # 2. Barreras intrabarra con prioridad de STOP en caso de doble toque
        hit_stop = exl <= stop if d == 1 else exh >= stop
        hit_target = exh >= target if d == 1 else exl <= target
        if hit_stop or hit_target:
            exit_price = (stop if hit_stop else target) - d * slip
            if hit_stop and hit_target:
                reason = "BOTH_ASSUME_PROTECTED_STOP" if be_active else "BOTH_ASSUME_STOP"
            elif hit_stop:
                reason = "PROTECTED_STOP" if be_active else "STOP"
            else:
                reason = "TARGET"
            break

        # 3. Evaluación causal al CIERRE de la barra j (para barras k >= j + 1)
        net_close = exc - d * slip
        gain_atr = d * (net_close - entry) / atr

        if profile.be_trigger_atr is not None and gain_atr >= profile.be_trigger_atr:
            min_net_offset = (spr * (0.55 + slippage_multiplier)) / atr + 0.015
            locked_atr = max(min_net_offset, gain_atr * profile.be_lock_ratio)
            cand_stop = entry + d * locked_atr * atr
            if d == 1 and cand_stop < exc - 1e-9 and cand_stop > stop:
                stop = cand_stop
                be_active = True
            elif d == -1 and cand_stop > exc + 1e-9 and cand_stop < stop:
                stop = cand_stop
                be_active = True

        bars_elapsed = j - start + 1
        if (
            not be_active
            and profile.max_adverse_close_bars is not None
            and bars_elapsed >= profile.max_adverse_close_bars
            and gain_atr <= profile.max_adverse_close_atr
        ):
            exit_price = net_close
            reason = "TIME_INVALIDATION"
            break

    if exit_price is None:
        j = end
        spr = float(arr["spread"][j]) * point
        exit_price = float(arr["close"][j]) + (spr if d == -1 else 0.0) - d * spr * slippage_multiplier

    r = d * (exit_price - entry) / stopdist
    return float(r), int(j), reason


def make_precision_events(
    b: pd.DataFrame,
    horizon: int,
    point: float,
    profile: ExitProfile,
    slippage_multiplier: float = 0.5,
) -> list[tuple[int, int, float, np.ndarray]]:
    """Construye la lista de eventos candidatos con sus vectores PRECISION_FEATURES."""
    arr = prior.arrays_from(b)
    mat = b[list(PRECISION_FEATURES)].to_numpy(dtype=float)
    events: list[tuple[int, int, float, np.ndarray]] = []
    for i in range(100, len(b) - horizon):
        if not arr["signal"][i] or not np.isfinite(mat[i]).all():
            continue
        try:
            r, exit_i, _ = simulate_precision_event(
                arr, i, horizon, point, slippage_multiplier=slippage_multiplier, profile=profile
            )
        except ValueError:
            continue
        events.append((i, exit_i, r, mat[i]))
    return events


def fit_meta_selector(
    train_events: list[tuple[int, int, float, np.ndarray]],
    min_events: int,
) -> MetaSelectorBundle | None:
    """Entrena el selector Meta-Labeling híbrido usando solo eventos cerrados antes de train_end."""
    if len(train_events) < min_events:
        return None
    r_tr = np.array([e[2] for e in train_events], dtype=float)
    y_tr = np.array([int(e[2] > 0.10) for e in train_events], dtype=int)
    if np.unique(y_tr).size < 2:
        return None
    x_tr = np.vstack([e[3] for e in train_events])

    reg = make_pipeline(RobustScaler(), Ridge(alpha=80.0, random_state=17))
    reg.fit(x_tr, r_tr)

    clf = make_pipeline(RobustScaler(), LogisticRegression(C=0.08, max_iter=500, random_state=17))
    clf.fit(x_tr, y_tr)

    scores = 0.5 * reg.predict(x_tr) + 0.5 * clf.predict_proba(x_tr)[:, 1]
    return MetaSelectorBundle(
        ridge_model=reg,
        logistic_model=clf,
        train_scores_sorted=np.sort(scores),
    )


def precision_metrics(trades: list[dict], equity: float) -> dict:
    """Calcula métricas de rendimiento e intervalos estadísticos (Wilson, PSR, CVaR)."""
    if not trades:
        return {
            "trades": 0,
            "wins": 0,
            "win_rate": None,
            "wilson_lower_90_pct": None,
            "profit_factor": None,
            "mean_r": None,
            "psr": None,
            "cvar_5_r": None,
            "return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "reasons": {},
        }
    pnl = np.array([t["pnl"] for t in trades], dtype=float)
    rv = np.array([t["r"] for t in trades], dtype=float)
    wins = int((pnl > 0).sum())
    total = len(trades)
    total_plus = float(pnl[pnl > 0].sum())
    total_minus = float(-pnl[pnl < 0].sum())

    peak = equity
    maxdd = 0.0
    balance = equity
    for p in pnl:
        balance += float(p)
        peak = max(peak, balance)
        maxdd = max(maxdd, (peak - balance) / peak)

    return {
        "trades": total,
        "wins": wins,
        "win_rate": round(100.0 * wins / total, 3),
        "wilson_lower_90_pct": wilson_lower_bound(wins, total),
        "profit_factor": round(total_plus / total_minus, 4) if total_minus > 0 else None,
        "mean_r": round(float(rv.mean()), 5),
        "psr": probabilistic_sharpe_ratio(rv, 0.0),
        "cvar_5_r": expected_shortfall_r(rv, 0.05),
        "return_pct": round(100.0 * (balance / equity - 1.0), 4),
        "max_drawdown_pct": round(maxdd * 100.0, 4),
        "reasons": dict(Counter(t["reason"] for t in trades)),
    }


def backtest_precision_events(
    b: pd.DataFrame,
    events: list[tuple[int, int, float, np.ndarray]],
    scores: np.ndarray | None,
    threshold: float | None,
    horizon: int,
    point: float,
    start: int,
    end: int,
    cfg: HighWinRateLabConfig,
    profile: ExitProfile,
    slippage_multiplier: float = 0.5,
) -> dict:
    """Backtest secuencial sin solapamiento de posiciones dentro de [start, end)."""
    arr = prior.arrays_from(b)
    permitted = {
        e[0]
        for idx, e in enumerate(events)
        if start <= e[0]
        and e[0] + horizon < end
        and (threshold is None or (scores is not None and scores[idx] >= threshold))
    }
    balance = cfg.initial_eur
    trades: list[dict] = []
    next_signal = start
    for i in sorted(permitted):
        if i < next_signal or i + 1 >= end:
            continue
        r, x, reason = simulate_precision_event(
            arr, i, horizon, point, slippage_multiplier=slippage_multiplier, profile=profile
        )
        if x >= end:
            continue
        pnl = balance * cfg.risk_fraction * r
        trades.append({"i": i, "exit": x, "r": r, "pnl": pnl, "reason": reason})
        balance += pnl
        next_signal = x + 1
    return precision_metrics(trades, cfg.initial_eur)


def windows(n: int, cfg: HighWinRateLabConfig):
    """Pliegues temporales expansivos idénticos al estándar de validación V2."""
    if n < 3000:
        raise ValueError("No hay suficientes barras para validación temporal")
    p45, p58, p78 = (int(n * p) for p in (0.45, 0.58, 0.78))
    folds = ((p45, p45 + cfg.embargo, p58), (p58, p58 + cfg.embargo, p78))
    holdout_start = p78 + cfg.embargo
    if holdout_start > n - 200 or any(
        end - start < max(HORIZONS) + cfg.min_trades_fold for _tr, start, end in folds
    ):
        raise ValueError("Ventanas temporales insuficientes")
    return folds, (p78, holdout_start, n)


def _passes_fold(m: dict, cfg: HighWinRateLabConfig, min_trades: int) -> bool:
    return (
        m["trades"] >= min_trades
        and m["profit_factor"] is not None
        and m["profit_factor"] >= cfg.min_pf
        and m["mean_r"] is not None
        and m["mean_r"] >= cfg.min_mean_r
        and m["win_rate"] is not None
        and m["win_rate"] >= cfg.min_win_rate
    )


def precision_loss_patterns(
    b: pd.DataFrame,
    events: list[tuple[int, int, float, np.ndarray]],
    scores: np.ndarray | None,
    threshold: float | None,
    horizon: int,
    point: float,
    start: int,
    end: int,
    cfg: HighWinRateLabConfig,
    profile: ExitProfile,
) -> dict:
    """Diagnóstico fuera de muestra de operaciones ganadoras y perdedoras en Holdout."""
    candidates = {
        e[0]: idx
        for idx, e in enumerate(events)
        if start <= e[0]
        and e[0] + horizon < end
        and (threshold is None or (scores is not None and scores[idx] >= threshold))
    }
    arr = prior.arrays_from(b)
    logs = []
    next_i = start
    for i in sorted(candidates):
        if i < next_i:
            continue
        r, x, reason = simulate_precision_event(
            arr, i, horizon, point, slippage_multiplier=cfg.slip_as_spread, profile=profile
        )
        if x >= end:
            continue
        logs.append(
            {
                "entry_signal_at": str(b.index[i]),
                "side": "LONG" if arr["signal"][i] > 0 else "SHORT",
                "R": round(float(r), 5),
                "reason": reason,
                "spread_to_atr": round(float(arr["spread"][i] * point / arr["atr"][i]), 5),
                "rsi": round(float(b["rsi"].iloc[i]), 2),
                "h1_direction": int(b["h1_direction"].iloc[i]),
                "ml_score": round(float(scores[candidates[i]]), 4) if threshold is not None and scores is not None else None,
            }
        )
        next_i = x + 1
    losers = [q for q in logs if q["R"] < 0]
    winners = [q for q in logs if q["R"] > 0]
    return {
        "trades_recorded": len(logs),
        "losers": len(losers),
        "losses_by_side": dict(Counter(q["side"] for q in losers)),
        "losses_by_reason": dict(Counter(q["reason"] for q in losers)),
        "median_spread_atr_losses": round(float(np.median([q["spread_to_atr"] for q in losers])), 5) if losers else None,
        "median_spread_atr_wins": round(float(np.median([q["spread_to_atr"] for q in winners])), 5) if winners else None,
        "sample_losses": losers[:5],
        "note": "Diagnóstico fuera de muestra. Prohibido reoptimizar parámetros con el holdout.",
    }


def research_market_high_winrate(
    m15: pd.DataFrame,
    h1: pd.DataFrame,
    point: float,
    cfg: HighWinRateLabConfig = HighWinRateLabConfig(),
    cross_market_closes: dict[str, pd.Series] | None = None,
) -> dict:
    """Evalúa las estrategias de precisión en Fold 1 y Fold 2 y valida la ganadora en Holdout."""
    enriched = enrich_microstructure_features(m15, h1, point, cross_market_closes=cross_market_closes)
    folds, final_window = windows(len(enriched), cfg)

    options: list[dict] = []
    prepared: dict[tuple[str, int, str], tuple[pd.DataFrame, list, ExitProfile]] = {}
    signal_counts: dict[str, int] = {}

    for strategy in PRECISION_STRATEGIES:
        b = generate_precision_signals(enriched, strategy, point)
        signal_counts[strategy] = int((b["signal"] != 0).sum())
        for h in HORIZONS:
            for profile in EXIT_PROFILES:
                events = make_precision_events(
                    b, h, point, profile=profile, slippage_multiplier=cfg.slip_as_spread
                )
                prepared[(strategy, h, profile.name)] = (b, events, profile)

                fold_context = []
                for train_end, val_start, val_end in folds:
                    train = [e for e in events if e[0] + h < train_end]
                    validation = [e for e in events if val_start <= e[0] and e[0] + h < val_end]
                    selector = fit_meta_selector(train, cfg.min_training_events)
                    val_scores = (
                        selector.score_features(np.vstack([e[3] for e in validation]))
                        if selector is not None and validation
                        else None
                    )
                    fold_context.append((validation, selector, val_scores, val_start, val_end))

                for q_cut in QUANTILE_CUTOFFS:
                    fold_metrics = []
                    fold_thresholds = []
                    for validation, selector, val_scores, start, end in fold_context:
                        if q_cut is not None and (selector is None or val_scores is None):
                            fold_metrics.append(precision_metrics([], cfg.initial_eur))
                            fold_thresholds.append(None)
                        else:
                            thr = selector.threshold_for_quantile(q_cut) if selector is not None else None
                            fold_thresholds.append(round(thr, 5) if thr is not None else None)
                            fold_metrics.append(
                                backtest_precision_events(
                                    b,
                                    validation,
                                    val_scores,
                                    thr,
                                    h,
                                    point,
                                    start,
                                    end,
                                    cfg,
                                    profile=profile,
                                    slippage_multiplier=cfg.slip_as_spread,
                                )
                            )

                    pass_both = all(_passes_fold(m, cfg, cfg.min_trades_fold) for m in fold_metrics)
                    if pass_both:
                        min_wr = min(m["win_rate"] for m in fold_metrics)
                        min_wilson = min(m["wilson_lower_90_pct"] for m in fold_metrics)
                        min_mr = min(m["mean_r"] for m in fold_metrics)
                        max_dd = max(m["max_drawdown_pct"] for m in fold_metrics)
                        beats_79 = min_wr >= cfg.target_benchmark_win_rate
                        score = round(
                            (0.10 if beats_79 else 0.0)
                            + min_mr
                            + 0.002 * (min_wilson - 65.0)
                            - 0.020 * max_dd,
                            6,
                        )
                    else:
                        score = None

                    options.append(
                        {
                            "strategy": strategy,
                            "horizon_bars": h,
                            "exit_profile": profile.name,
                            "ml_quantile": q_cut,
                            "learned_thresholds": fold_thresholds,
                            "total_signals": signal_counts[strategy],
                            "validation_folds": fold_metrics,
                            "passes_both_folds": pass_both,
                            "score": score,
                        }
                    )

    # Selección estrictamente en los dos pliegues de validación (sin consultar el holdout)
    accepted = [x for x in options if x["passes_both_folds"]]
    winner = (
        max(
            accepted,
            key=lambda x: (
                x["score"],
                min(f["win_rate"] for f in x["validation_folds"]),
                min(f["profit_factor"] for f in x["validation_folds"]),
            ),
        )
        if accepted
        else None
    )

    result = {
        "signals": signal_counts,
        "validation_candidates_count": len(options),
        "accepted_validation_count": len(accepted),
        "chosen": winner,
        "window_boundaries": {
            "folds": [
                {
                    "train_end_exclusive": str(enriched.index[train_end]),
                    "validation_start": str(enriched.index[st]),
                    "validation_end_exclusive": str(enriched.index[end]),
                }
                for train_end, st, end in folds
            ],
            "holdout_start": str(enriched.index[final_window[1]]),
            "embargo_bars": cfg.embargo,
        },
        "decision": "NO_TRADE",
        "holdout": None,
    }

    if winner is None:
        result["reason"] = (
            f"Ninguna configuración supera simultáneamente ambos pliegues con WR >= {cfg.min_win_rate}%, "
            f"PF >= {cfg.min_pf} y E[R] >= {cfg.min_mean_r} bajo estrés de spread/slippage"
        )
        return result

    strategy = winner["strategy"]
    h = winner["horizon_bars"]
    prof_name = winner["exit_profile"]
    q_cut = winner["ml_quantile"]
    b, events, profile = prepared[(strategy, h, prof_name)]

    train_end, test_start, test_end = final_window
    train = [e for e in events if e[0] + h < train_end]
    held = [e for e in events if test_start <= e[0] and e[0] + h < test_end]

    selector = fit_meta_selector(train, cfg.min_training_events) if q_cut is not None else None
    if q_cut is not None and selector is None:
        raise RuntimeError("Selector ML elegido sin capacidad de entrenamiento final")

    thr_final = selector.threshold_for_quantile(q_cut) if selector is not None else None
    held_scores = (
        selector.score_features(np.vstack([e[3] for e in held]))
        if selector is not None and held
        else None
    )

    base_metrics = backtest_precision_events(
        b,
        held,
        held_scores,
        thr_final,
        h,
        point,
        test_start,
        test_end,
        cfg,
        profile=profile,
        slippage_multiplier=0.0,
    )
    stressed_metrics = backtest_precision_events(
        b,
        held,
        held_scores,
        thr_final,
        h,
        point,
        test_start,
        test_end,
        cfg,
        profile=profile,
        slippage_multiplier=cfg.slip_as_spread,
    )
    patterns = precision_loss_patterns(
        b, held, held_scores, thr_final, h, point, test_start, test_end, cfg, profile=profile
    )

    passes_holdout = _passes_fold(base_metrics, cfg, cfg.min_trades_final) and (
        stressed_metrics["trades"] >= cfg.min_trades_final
        and stressed_metrics["profit_factor"] is not None
        and stressed_metrics["profit_factor"] >= 1.05
        and stressed_metrics["win_rate"] is not None
        and stressed_metrics["win_rate"] >= cfg.min_win_rate
    )

    result["holdout"] = {
        "exit_profile_params": asdict(profile),
        "learned_threshold_final": round(thr_final, 5) if thr_final is not None else None,
        "spread_only": base_metrics,
        "spread_plus_slippage": stressed_metrics,
        "loss_analysis": patterns,
        "passes_test": passes_holdout,
    }
    result["decision"] = "DEMO_PAPER_CANDIDATE" if passes_holdout else "FURTHER_RESEARCH_ONLY"
    result["reason"] = (
        "Supera pliegues expansivos y holdout reservado con alta tasa de acierto: apto para simulación DEMO"
        if passes_holdout
        else "Supera ambos pliegues de validación con >=79% WR, requiere ampliar ventana histórica para holdout"
    )
    return result


def run_high_winrate_archive(
    path: str | Path,
    config: HighWinRateLabConfig = HighWinRateLabConfig(),
) -> dict:
    """Ejecuta el laboratorio completo de alta precisión sobre el archivo ZIP de Admirals DEMO."""
    result = {
        "study": "Trading V2 High-WinRate Precision Lab (>= 79% Benchmark)",
        "source_archive": Path(path).name,
        "methodology": {
            "strategies": list(PRECISION_STRATEGIES),
            "exit_profiles": [asdict(p) for p in EXIT_PROFILES],
            "horizons": list(HORIZONS),
            "ml_quantiles": list(QUANTILE_CUTOFFS),
            "validation": "Two expanding folds (0-45% -> 45-58%, 0-58% -> 58-78%) + 40-bar embargo + Holdout (78-100%)",
            "costs": "MT5 Bid OHLC + historical spread + stress 0.5x spread adverse slippage on each leg",
        },
        "approval": {"live_real_money": False, "demo_simulation_ready": True},
        "markets": {},
    }
    with zipfile.ZipFile(path) as z:
        manifest = json.loads(z.read("admirals_manifest.json"))["account"]
        if (
            not manifest.get("demo")
            or "admir" not in (str(manifest.get("company", "")) + str(manifest.get("server", ""))).lower()
            or manifest.get("currency") != "EUR"
        ):
            raise ValueError("Debe utilizarse el ZIP Admirals DEMO EUR válido")

        loaded = {}
        for market, (_sym, point) in prior.SYMBOLS.items():
            m15, h1 = prior.load_data(z, market)
            consistency = prior.check_m15_h1_consistency(m15, h1)
            loaded[market] = (m15, h1, point, consistency)

        close_series = {m: loaded[m][0]["Close"] for m in loaded}
        eurusd_last = float(close_series["EURUSD"].iloc[-1]) if "EURUSD" in close_series else 1.12
        for market, (m15, h1, point, consistency) in loaded.items():
            other_closes = {k: v for k, v in close_series.items() if k != market}
            market_res = research_market_high_winrate(
                m15, h1, point, cfg=config, cross_market_closes=other_closes
            )
            sym_name = prior.SYMBOLS[market][0]
            spec = get_contract_spec(sym_name)
            tr = pd.concat(
                [
                    m15["High"] - m15["Low"],
                    (m15["High"] - m15["Close"].shift(1)).abs(),
                    (m15["Low"] - m15["Close"].shift(1)).abs(),
                ],
                axis=1,
            ).max(axis=1)
            med_atr = float(tr.rolling(14).mean().median())
            last_close = float(m15["Close"].iloc[-1])
            lot_audit = calculate_lot_size(
                spec=spec,
                account_equity=3000.0,
                risk_fraction=0.005,
                stop_distance_price=1.40 * med_atr,
                entry_price=last_close,
                eurusd_rate=eurusd_last,
                leverage=100.0,
                account_currency="EUR",
            )
            market_res["contract_sizing_audit"] = asdict(lot_audit)
            market_res["data_quality"] = {
                "h1_consistency": consistency,
                "m15_bars": len(m15),
                "h1_bars": len(h1),
            }
            result["markets"][market] = market_res
    return result
