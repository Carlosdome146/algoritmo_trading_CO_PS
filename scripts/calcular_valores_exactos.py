"""Cálculo del valor exacto y determinado (sin horquillas) para cada activo con el modelo Francotirador de Ismael."""
from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from trading_v2.research.regime_lab_v3 import metrics


def get_exact_sniper_metrics(symbol: str, tf_code: int, target_u: float, sl_mult: float, min_wick: float, s_start: int, s_end: int):
    r = mt5.copy_rates_from_pos(symbol, tf_code, 0, 30000)
    df = pd.DataFrame(r)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    c, h, l, o = df["close"].values, df["high"].values, df["low"].values, df["open"].values
    n = len(df)

    is_fx = "EUR" in symbol
    unit = 0.00010 if is_fx else 1.0
    spr_cost = 0.00006 if is_fx else (0.8 if "GER" in symbol else (0.4 if "SP500" in symbol else 3.5))
    tgt_dist = target_u * unit

    tr = np.maximum(h - l, np.abs(h - pd.Series(c).shift(1).fillna(c[0]).values))
    atr = pd.Series(tr).rolling(14, min_periods=5).mean().values
    sma200 = pd.Series(c).rolling(200, min_periods=50).mean().values
    ema20 = pd.Series(c).ewm(span=20, adjust=False).mean().values

    rng = np.maximum(h - l, 1e-9)
    lower_wick = (np.minimum(o, c) - l) / rng
    upper_wick = (h - np.maximum(o, c)) / rng
    clv = (c - l) / rng
    recent_lo = pd.Series(l).shift(1).rolling(8, min_periods=3).min().values
    recent_hi = pd.Series(h).shift(1).rolling(8, min_periods=3).max().values
    hrs = df.index.hour.values

    trades = []
    wins = 0
    losses = 0

    i = 210
    while i < n - 1:
        if not (s_start <= hrs[i] <= s_end):
            i += 1
            continue
        cur_atr = atr[i]
        if not np.isfinite(cur_atr) or cur_atr <= 0:
            i += 1
            continue

        long_sig = (c[i] > sma200[i]) and (c[i] > ema20[i]) and (l[i] <= recent_lo[i]) and (lower_wick[i] >= min_wick) and (clv[i] >= 0.75)
        short_sig = (c[i] < sma200[i]) and (c[i] < ema20[i]) and (h[i] >= recent_hi[i]) and (upper_wick[i] >= min_wick) and (clv[i] <= 0.25)

        side = 1 if long_sig else (-1 if short_sig else 0)
        if side == 0:
            i += 1
            continue

        k = i + 1
        entry = o[k] + side * spr_cost * 0.5
        tp_px = entry + side * tgt_dist
        stop_dist = max(cur_atr * sl_mult, tgt_dist * 2.0)
        sl_px = entry - side * stop_dist

        exit_px = None
        for j in range(k, min(n, k + 8)):
            eval_lo = l[j]
            eval_hi = h[j]
            hit_sl = (eval_lo <= sl_px) if side == 1 else (eval_hi >= sl_px)
            hit_tp = (eval_hi >= tp_px) if side == 1 else (eval_lo <= tp_px)
            if hit_sl and hit_tp:
                exit_px = sl_px
                break
            elif hit_sl:
                exit_px = sl_px
                break
            elif hit_tp:
                exit_px = tp_px
                break
        if exit_px is None:
            j = min(n - 1, k + 7)
            exit_px = c[j] - side * spr_cost * 0.5

        pnl = side * (exit_px - entry) - spr_cost * 0.5
        r_val = pnl / stop_dist
        if pnl > 0:
            wins += 1
        else:
            losses += 1
        trades.append(r_val)
        i = j + 1

    tot = wins + losses
    wr = (wins / tot * 100.0) if tot > 0 else 0.0
    r_arr = np.array(trades)
    m = metrics(r_arr)
    return {
        "symbol": symbol,
        "wins": wins,
        "losses": losses,
        "total": tot,
        "win_rate": wr,
        "pf": m["profit_factor"],
        "sum_r": r_arr.sum(),
        "mean_r": m["mean_r"],
    }


def main():
    if not mt5.initialize():
        return

    # Parámetros únicos determinados para cada activo en producción:
    active_configs = [
        # sym, tf, target_u, sl_mult, min_wick, s_start, s_end
        ("EURUSD", mt5.TIMEFRAME_M15, 3.5, 2.5, 0.50, 7, 16),
        ("GERMANY40", mt5.TIMEFRAME_M15, 12.0, 2.5, 0.35, 7, 15),
        ("[SP500]", mt5.TIMEFRAME_M15, 3.5, 2.5, 0.35, 13, 20),
        ("[IBEX35]", mt5.TIMEFRAME_M15, 15.0, 2.5, 0.55, 7, 11),
    ]

    print("=" * 95)
    print("MÉTRICAS EXACTAS Y DETERMINADAS (VALORES ÚNICOS) POR ACTIVO EN MT5")
    print("=" * 95)
    print(f"{'Activo':<12} | {'Operaciones Totales':<20} | {'Ganadas':<8} | {'Perdidas':<8} | {'Win Rate EXACTO':<16} | {'Profit Factor':<14} | {'Retorno Neto ($R$)'}")
    print("-" * 95)

    for sym, tf, tgt, sl, wk, st, nd in active_configs:
        res = get_exact_sniper_metrics(sym, tf, tgt, sl, wk, st, nd)
        tf_name = "M15"
        print(
            f"{sym:<12} | {res['total']:<4d} operaciones     | {res['wins']:<8d} | {res['losses']:<8d} | "
            f"  {res['win_rate']:5.2f}%         |   {res['pf']:5.2f}         |  {res['sum_r']:+6.2f} R"
        )
    print("-" * 95)

    mt5.shutdown()


if __name__ == "__main__":
    main()
