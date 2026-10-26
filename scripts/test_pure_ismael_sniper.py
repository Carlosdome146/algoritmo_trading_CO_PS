"""Replicación pura del modelo Francotirador de Ismael (captura de impulso + barrido + absorción)."""
from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from trading_v2.research.regime_lab_v3 import metrics


def test_ismael_sniper(symbol: str, tf_code: int, target_pips_pts: float, sl_mult: float = 2.5, min_wick: float = 0.50):
    r = mt5.copy_rates_from_pos(symbol, tf_code, 0, 30000)
    if r is None or len(r) == 0:
        return None
    df = pd.DataFrame(r)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    c, h, l, o = df["close"].values, df["high"].values, df["low"].values, df["open"].values
    n = len(df)

    is_fx = "EUR" in symbol
    unit = 0.00010 if is_fx else 1.0
    spr_cost = 0.00006 if is_fx else (0.8 if "GER" in symbol else (0.4 if "SP500" in symbol else 3.0))
    tgt_dist = target_pips_pts * unit

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
    s_start, s_end = (7, 16) if symbol != "[SP500]" else (13, 20)

    trades = []
    i = 210
    while i < n - 1:
        if not (s_start <= hrs[i] <= s_end):
            i += 1
            continue
        cur_atr = atr[i]
        if not np.isfinite(cur_atr) or cur_atr <= 0:
            i += 1
            continue

        # Patrón Ismael: Barrido de extremo reciente + absorción fuerte (mecha >= 50%) + cierre direccional
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
        trades.append({"r": r_val, "win": pnl > 0, "pnl": pnl})
        i = j + 1

    if len(trades) < 10:
        return None
    tdf = pd.DataFrame(trades)
    m = metrics(tdf["r"].to_numpy())
    return {"n": m["n"], "win_rate": m["win_rate"], "pf": m["profit_factor"], "sum_r": tdf["r"].sum()}


def main():
    if not mt5.initialize():
        return

    print("=" * 85)
    print("REPLICACIÓN DEL MODELO FRANCOTIRADOR DE ISMAEL (IMPULSO DIRECTO TRAS ABSORCIÓN)")
    print("=" * 85)

    configs = [
        ("EURUSD", mt5.TIMEFRAME_M15, 2.5),
        ("EURUSD", mt5.TIMEFRAME_M15, 3.0),
        ("EURUSD", mt5.TIMEFRAME_M15, 3.5),
        ("GERMANY40", mt5.TIMEFRAME_M15, 12.0),
        ("GERMANY40", mt5.TIMEFRAME_M15, 15.0),
        ("GERMANY40", mt5.TIMEFRAME_M30, 18.0),
        ("[SP500]", mt5.TIMEFRAME_M15, 3.5),
        ("[SP500]", mt5.TIMEFRAME_M15, 4.5),
        ("[SP500]", mt5.TIMEFRAME_M30, 5.0),
        ("[IBEX35]", mt5.TIMEFRAME_M15, 15.0),
        ("[IBEX35]", mt5.TIMEFRAME_M30, 20.0),
    ]

    for sym, tf_code, tgt in configs:
        tf_str = "M15" if tf_code == mt5.TIMEFRAME_M15 else "M30"
        res = test_ismael_sniper(sym, tf_code, tgt)
        if res:
            n_t = res["n"]
            wr = res["win_rate"]
            pf = res["pf"]
            sr = res["sum_r"]
            print(f"{sym:<12} | {tf_str} | Target={tgt:4.1f} | N={n_t:3d} trades | WinRate={wr:5.1f}% | ProfitFactor={pf:4.2f} | Retorno={sr:+6.2f} R")

    mt5.shutdown()


if __name__ == "__main__":
    main()
