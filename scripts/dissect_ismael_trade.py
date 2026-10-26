"""Optimización del patrón ISMAEL_SWEEP_RECLAIM + BB_EXTREME_DIP en EURUSD M15."""
from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from trading_v2.research.regime_lab_v3 import metrics


def main():
    if not mt5.initialize():
        return

    r = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_M15, 0, 35000)
    df = pd.DataFrame(r)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)

    c, h, l, o = df["close"].values, df["high"].values, df["low"].values, df["open"].values
    n = len(df)
    spr_cost = 0.00006

    tr = np.maximum(h - l, np.abs(h - pd.Series(c).shift(1).fillna(c[0]).values))
    atr = pd.Series(tr).rolling(14, min_periods=5).mean().values

    delta = pd.Series(c).diff()
    up = delta.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    rsi2 = (100 - 100 / (1 + up / dn.replace(0, np.nan))).values

    sma200 = pd.Series(c).rolling(200, min_periods=50).mean().values
    ema20 = pd.Series(c).ewm(span=20, adjust=False).mean().values
    sma20 = pd.Series(c).rolling(20, min_periods=10).mean().values
    std20 = pd.Series(c).rolling(20, min_periods=10).std(ddof=0).values
    sma5 = pd.Series(c).rolling(5, min_periods=3).mean().values
    bb_lo = sma20 - 2.2 * std20

    rng = np.maximum(h - l, 1e-9)
    lower_wick = (np.minimum(o, c) - l) / rng
    clv = (c - l) / rng
    recent_lo = pd.Series(l).shift(1).rolling(8, min_periods=3).min().values
    hrs = df.index.hour.values

    for tp_mult in [0.45, 0.55, 0.65]:
        for wick_min in [0.50, 0.55, 0.60]:
            trades = []
            i = 210
            while i < n - 1:
                if not (7 <= hrs[i] <= 16):
                    i += 1
                    continue
                cur_atr = atr[i]
                if not np.isfinite(cur_atr) or cur_atr <= 0:
                    i += 1
                    continue

                trig_bb = (c[i] > sma200[i]) and (rsi2[i] < 5.0) and (c[i] <= bb_lo[i])
                trig_ismael = (
                    (l[i] <= recent_lo[i])
                    and (c[i] > sma200[i])
                    and (ema20[i] > sma200[i])
                    and (c[i] > ema20[i])
                    and (lower_wick[i] >= wick_min)
                    and (clv[i] >= 0.85)
                )

                if not (trig_bb or trig_ismael):
                    i += 1
                    continue

                k = i + 1
                entry = o[k] + spr_cost * 0.5
                if trig_ismael and not trig_bb:
                    tp_px = entry + tp_mult * cur_atr
                    stop = entry - 2.5 * cur_atr
                    be_trig = entry + 0.30 * cur_atr
                    be_lock = entry + 0.05 * cur_atr
                    cur_sl = stop
                    exit_px = None
                    for j in range(k, min(n, k + 8)):
                        if l[j] <= cur_sl:
                            exit_px = cur_sl - spr_cost * 0.5
                            break
                        if h[j] >= tp_px:
                            exit_px = tp_px
                            break
                        if c[j] >= be_trig and cur_sl < be_lock:
                            cur_sl = be_lock
                    if exit_px is None:
                        j = min(n - 1, k + 7)
                        exit_px = c[j] - spr_cost * 0.5
                    r_val = (exit_px - entry) / (2.5 * cur_atr)
                    t_type = "ISMAEL_SWEEP_RECLAIM"
                else:
                    stop = entry - 3.5 * cur_atr
                    exit_px = None
                    for j in range(k, min(n, k + 16)):
                        if l[j] <= stop:
                            exit_px = stop - spr_cost * 0.5
                            break
                        if c[j] > sma5[j] and j + 1 < n:
                            exit_px = o[j + 1] - spr_cost * 0.5
                            j = j + 1
                            break
                    if exit_px is None:
                        j = min(n - 1, k + 15)
                        exit_px = c[j] - spr_cost * 0.5
                    r_val = (exit_px - entry) / (3.5 * cur_atr)
                    t_type = "BB_EXTREME_DIP"

                trades.append({
                    "entry_time": df.index[k],
                    "type": t_type,
                    "r": r_val,
                })
                i = j + 1

            tdf = pd.DataFrame(trades)
            ism = tdf[tdf["type"] == "ISMAEL_SWEEP_RECLAIM"]
            m_all = metrics(tdf["r"].to_numpy())
            m_ism = metrics(ism["r"].to_numpy())
            print(
                f"tp={tp_mult} wick>={wick_min} | TOTAL: N={m_all['n']} WR={m_all['win_rate']:.1f}% PF={m_all['profit_factor']:.2f} "
                f"| ISMAEL_PATTERN: N={m_ism['n']} WR={m_ism['win_rate']:.1f}% PF={m_ism['profit_factor']:.2f}"
            )

    mt5.shutdown()


if __name__ == "__main__":
    main()
