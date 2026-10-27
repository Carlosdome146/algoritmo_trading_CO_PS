"""Evaluación empírica del impacto de las 3 mejoras (Carlos + The-Quant-Trading-Vault)
sobre las estadísticas exactas de nuestro modelo Francotirador en los 4 activos."""
from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from trading_v2.research.regime_lab_v3 import metrics


def eval_variant(
    df: pd.DataFrame,
    symbol: str,
    target_u: float,
    sl_mult: float,
    min_wick: float,
    clv_th: float,
    s_start: int,
    s_end: int,
    use_joya1_slope: bool = False,
    use_joya2_no_opp_wick: bool = False,
    use_joya3_keltner: bool = False,
) -> dict:
    c = df["close"].values
    h = df["high"].values
    l = df["low"].values
    o = df["open"].values
    n = len(df)

    is_fx = "EUR" in symbol
    unit = 0.00010 if is_fx else 1.0
    spr_cost = 0.00006 if is_fx else (0.8 if "GER" in symbol else (0.4 if "SP500" in symbol else 3.5))
    tgt_dist = target_u * unit

    prev_c = pd.Series(c).shift(1).fillna(c[0]).values
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    atr14 = pd.Series(tr).rolling(14, min_periods=5).mean().values
    atr10 = pd.Series(tr).rolling(10, min_periods=3).mean().values

    sma200 = pd.Series(c).rolling(200, min_periods=50).mean().values
    ema20 = pd.Series(c).ewm(span=20, adjust=False).mean().values

    # Canal de Keltner (EMA20 +/- 1.5 * ATR10) y posicion Keltner
    k_ub = ema20 + 1.5 * atr10
    k_lb = ema20 - 1.5 * atr10
    k_rng = np.maximum(k_ub - k_lb, 1e-9)
    k_pos = (l - k_lb) / k_rng      # posición del mínimo respecto al canal inferior
    k_pos_hi = (h - k_lb) / k_rng   # posición del máximo respecto al canal superior

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
        cur_atr = atr14[i]
        if not np.isfinite(cur_atr) or cur_atr <= 0:
            i += 1
            continue

        # Base Sniper conditions
        if is_fx:
            # En EURUSD el modelo 91.67% opera el patron Ismael alcista puro (ema20 > sma200)
            long_sig = (
                (c[i] > sma200[i])
                and (ema20[i] > sma200[i])
                and (c[i] > ema20[i])
                and (l[i] <= recent_lo[i])
                and (lower_wick[i] >= min_wick)
                and (clv[i] >= clv_th)
            )
            short_sig = False
        else:
            long_sig = (
                (c[i] > sma200[i])
                and (c[i] > ema20[i])
                and (l[i] <= recent_lo[i])
                and (lower_wick[i] >= min_wick)
                and (clv[i] >= clv_th)
            )
            short_sig = (
                (c[i] < sma200[i])
                and (c[i] < ema20[i])
                and (h[i] >= recent_hi[i])
                and (upper_wick[i] >= min_wick)
                and (clv[i] <= (1.0 - clv_th))
            )

        # Joya 1: Pendiente estructural (SMA200 e inclinación a favor)
        if use_joya1_slope:
            long_sig = long_sig and (sma200[i] >= sma200[i - 4]) and (ema20[i] > sma200[i])
            short_sig = short_sig and (sma200[i] <= sma200[i - 4]) and (ema20[i] < sma200[i])

        # Joya 2: Sombra contraria casi nula (Intraday Hammer puro: mecha opuesta <= 12%)
        if use_joya2_no_opp_wick:
            long_sig = long_sig and (upper_wick[i] <= 0.12)
            short_sig = short_sig and (lower_wick[i] <= 0.12)

        # Joya 3: Confluencia con extremo de Keltner (Carlos QuantDinger + Vault)
        if use_joya3_keltner:
            long_sig = long_sig and (k_pos[i] <= 0.35)
            short_sig = short_sig and (k_pos_hi[i] >= 0.65)

        side = 1 if long_sig else (-1 if short_sig else 0)
        if side == 0:
            i += 1
            continue

        k = i + 1
        entry = o[k] + side * spr_cost * 0.5
        tp_px = entry + side * tgt_dist
        stop_dist = max(cur_atr * sl_mult, tgt_dist * 2.0)
        sl_px = entry - side * stop_dist

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
    r_arr = np.array(trades) if tot > 0 else np.array([0.0])
    m = metrics(r_arr) if tot > 0 else {"profit_factor": 0.0}
    return {
        "total": tot,
        "wins": wins,
        "losses": losses,
        "wr": wr,
        "pf": m["profit_factor"],
        "sum_r": float(r_arr.sum()) if tot > 0 else 0.0,
    }


def main():
    if not mt5.initialize():
        return

    assets = [
        ("EURUSD", mt5.TIMEFRAME_M15, 3.0, 2.5, 0.55, 0.85, 7, 16),
        ("GERMANY40", mt5.TIMEFRAME_M15, 12.0, 2.5, 0.45, 0.75, 7, 15),
        ("[IBEX35]", mt5.TIMEFRAME_M15, 15.0, 2.5, 0.55, 0.70, 7, 11),
        ("[SP500]", mt5.TIMEFRAME_M15, 4.0, 2.5, 0.45, 0.75, 13, 20),
    ]

    variants = [
        ("0. MODELO ACTUAL (EN VIVO)", False, False, False),
        ("1. + Joya 1 (Pendiente Estructural)", True, False, False),
        ("2. + Joya 2 (Martillo Sin Mecha Sup)", False, True, False),
        ("3. + Joya 3 (Canal Keltner Carlos)", False, False, True),
        ("4. COMBINACIÓN ÓPTIMA (1+2+3)", True, True, True),
    ]

    for sym, tf, tgt, sl_m, wick, clv_t, s_h, e_h in assets:
        r = mt5.copy_rates_from_pos(sym, tf, 0, 35000)
        df = pd.DataFrame(r)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.set_index("time", inplace=True)

        print(f"\n==========================================================================================")
        print(f"ACTIVO: {sym} (Target={tgt} | Mecha>={wick:.0%} | CLV>={clv_t:.2f})")
        print(f"==========================================================================================")
        print(f"{'VARIANTE':<38} | {'TRADES':<6} | {'G / P':<9} | {'WIN RATE':<9} | {'PF':<6} | {'RETORNO R'}")
        print("-" * 90)
        for v_name, j1, j2, j3 in variants:
            res = eval_variant(df, sym, tgt, sl_m, wick, clv_t, s_h, e_h, j1, j2, j3)
            gp = f"{res['wins']:2d} / {res['losses']:2d}"
            print(f"{v_name:<38} | {res['total']:<6d} | {gp:<9} | {res['wr']:6.2f}%  | {res['pf']:5.2f} | {res['sum_r']:+6.2f}R")

    mt5.shutdown()


if __name__ == "__main__":
    main()
