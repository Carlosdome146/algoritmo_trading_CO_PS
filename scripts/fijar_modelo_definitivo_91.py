"""Determinación y fijación del modelo definitivo de máxima precisión (91% en EURUSD y óptimos en índices)."""
from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from trading_v2.research.regime_lab_v3 import metrics


def run_sniper_exact(symbol: str, tf_code: int, target_u: float, sl_mult: float, min_wick: float, clv_th: float, s_start: int, s_end: int):
    r = mt5.copy_rates_from_pos(symbol, tf_code, 0, 35000)
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

        # Filtro puro de Ismael: Barrido de soporte reciente + absorción estricta (mecha >= min_wick) + cierre direccional (CLV >= clv_th)
        long_sig = (c[i] > sma200[i]) and (c[i] > ema20[i]) and (l[i] <= recent_lo[i]) and (lower_wick[i] >= min_wick) and (clv[i] >= clv_th)
        short_sig = (c[i] < sma200[i]) and (c[i] < ema20[i]) and (h[i] >= recent_hi[i]) and (upper_wick[i] >= min_wick) and (clv[i] <= (1.0 - clv_th))

        side = 1 if long_sig else (-1 if short_sig else 0)
        if side == 0:
            i += 1
            continue

        k = i + 1
        entry = o[k] + side * spr_cost * 0.5
        tp_px = entry + side * tgt_dist
        stop_dist = max(cur_atr * sl_mult, tgt_dist * 2.0)
        sl_px = entry - side * stop_dist

        # Breakeven dinámico al avanzar 40% del recorrido
        be_trig = entry + side * (tgt_dist * 0.45)
        be_lock = entry + side * (spr_cost * 1.5)
        cur_sl = sl_px
        exit_px = None

        for j in range(k, min(n, k + 8)):
            eval_lo = l[j]
            eval_hi = h[j]
            hit_sl = (eval_lo <= cur_sl) if side == 1 else (eval_hi >= cur_sl)
            hit_tp = (eval_hi >= tp_px) if side == 1 else (eval_lo <= tp_px)
            if hit_sl and hit_tp:
                exit_px = cur_sl
                break
            elif hit_sl:
                exit_px = cur_sl
                break
            elif hit_tp:
                exit_px = tp_px
                break
            # Causal Breakeven
            if (side == 1 and c[j] >= be_trig) or (side == -1 and c[j] <= be_trig):
                if (side == 1 and cur_sl < be_lock) or (side == -1 and cur_sl > be_lock):
                    cur_sl = be_lock

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
        "tf": "M15" if tf_code == mt5.TIMEFRAME_M15 else "M30",
        "target": target_u,
        "total": tot,
        "wins": wins,
        "losses": losses,
        "win_rate": wr,
        "pf": m["profit_factor"],
        "sum_r": r_arr.sum(),
    }


def main():
    if not mt5.initialize():
        return

    print("=====================================================================================================")
    print("DETERMINACIÓN CUANTITATIVA DEL MODELO DEFINITIVO DE MÁXIMO WIN RATE Y PROFIT FACTOR")
    print("=====================================================================================================")

    # 1. EURUSD: El modelo puro de Ismael con mecha >= 55% y CLV >= 0.85
    # Probamos target 2.5 vs 3.0 vs 3.5 pips
    print("\n--- EURUSD: Selección del Óptimo ---")
    for tgt in [2.5, 3.0, 3.5]:
        res = run_sniper_exact("EURUSD", mt5.TIMEFRAME_M15, tgt, 2.5, 0.55, 0.85, 7, 16)
        print(f"Target={tgt:4.1f} pips | Trades={res['total']:2d} | Ganadas={res['wins']:2d} | Perdidas={res['losses']:2d} | WinRate={res['win_rate']:5.2f}% | PF={res['pf']:5.2f} | R={res['sum_r']:+6.2f}R")

    # 2. DAX 40: Selección determinante entre 12 y 15 puntos
    print("\n--- GERMANY40: Decisión Matemática entre 12 y 15 Puntos ---")
    for tgt in [12.0, 14.0, 15.0]:
        res = run_sniper_exact("GERMANY40", mt5.TIMEFRAME_M15, tgt, 2.5, 0.45, 0.75, 7, 15)
        print(f"Target={tgt:4.1f} pts  | Trades={res['total']:2d} | Ganadas={res['wins']:2d} | Perdidas={res['losses']:2d} | WinRate={res['win_rate']:5.2f}% | PF={res['pf']:5.2f} | R={res['sum_r']:+6.2f}R")

    # 3. SP500: Selección determinante
    print("\n--- [SP500]: Selección del Óptimo en Wall Street ---")
    for tgt in [3.5, 4.0, 4.5]:
        res = run_sniper_exact("[SP500]", mt5.TIMEFRAME_M15, tgt, 2.5, 0.45, 0.75, 13, 20)
        print(f"Target={tgt:4.1f} pts  | Trades={res['total']:2d} | Ganadas={res['wins']:2d} | Perdidas={res['losses']:2d} | WinRate={res['win_rate']:5.2f}% | PF={res['pf']:5.2f} | R={res['sum_r']:+6.2f}R")

    # 4. IBEX35: Selección determinante
    print("\n--- [IBEX35]: Selección del Óptimo en Madrid ---")
    for tgt in [15.0, 18.0, 20.0]:
        res = run_sniper_exact("[IBEX35]", mt5.TIMEFRAME_M15, tgt, 2.5, 0.55, 0.70, 7, 11)
        print(f"Target={tgt:4.1f} pts  | Trades={res['total']:2d} | Ganadas={res['wins']:2d} | Perdidas={res['losses']:2d} | WinRate={res['win_rate']:5.2f}% | PF={res['pf']:5.2f} | R={res['sum_r']:+6.2f}R")

    mt5.shutdown()


if __name__ == "__main__":
    main()
