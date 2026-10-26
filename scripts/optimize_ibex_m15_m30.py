"""Búsqueda exhaustiva de la mejor estrategia para el IBEX 35 en M15 y M30 con Win Rate >= 75-80%."""
from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from trading_v2.research.regime_lab_v3 import metrics, wilson_lb


def run_ibex_deep_search():
    if not mt5.initialize():
        print("Error al inicializar MT5")
        return

    sym = "[IBEX35]"
    # Obtener todas las barras disponibles en MT5 para M15 y M30
    rates_m15 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 45000)
    rates_m30 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M30, 0, 30000)

    print("=" * 95)
    print("LABORATORIO CUANTITATIVO DE ALTA PRECISIÓN EXCLUSIVO PARA EL IBEX 35 (M15 Y M30)")
    print("=" * 95)

    datasets = [
        ("M15 (15 min)", rates_m15),
        ("M30 (30 min)", rates_m30),
    ]

    best_overall = []

    for tf_label, rates in datasets:
        if rates is None or len(rates) == 0:
            continue
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.set_index("time", inplace=True)

        c = df["close"].values
        h = df["high"].values
        l = df["low"].values
        o = df["open"].values
        n = len(df)

        # Spread real típico de sesión líquida de mañana (09:00 a 13:00 Madrid)
        spr_cost = 3.5

        # Indicadores
        tr = np.maximum(h - l, np.abs(h - pd.Series(c).shift(1).fillna(c[0]).values))
        atr = pd.Series(tr).rolling(14, min_periods=5).mean().values

        delta = pd.Series(c).diff()
        up = delta.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
        dn = (-delta.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
        rsi2 = (100 - 100 / (1 + up / dn.replace(0, np.nan))).values

        sma200 = pd.Series(c).rolling(200, min_periods=40).mean().values
        ema20 = pd.Series(c).ewm(span=20, adjust=False).mean().values
        sma20 = pd.Series(c).rolling(20, min_periods=10).mean().values
        std20 = pd.Series(c).rolling(20, min_periods=10).std(ddof=0).values
        hrs = df.index.hour.values

        rng = np.maximum(h - l, 1e-9)
        lower_wick = (np.minimum(o, c) - l) / rng
        upper_wick = (h - np.maximum(o, c)) / rng
        clv = (c - l) / rng

        # Probar diferentes combinaciones de filtros específicos del IBEX 35:
        # 1. Ventana horaria matinal: de 07:00 a 11:00 UTC (09:00 a 13:00 Madrid) donde el spread y el volumen son óptimos
        # 2. Lookback de extremos: 6, 8, 12 velas
        # 3. Targets adecuados al spread de 3.5 pts: 15, 18, 20, 25, 30 puntos
        # 4. Multiplicadores de SL y Breakeven

        for lookback in [6, 8, 12]:
            recent_lo = pd.Series(l).shift(1).rolling(lookback, min_periods=3).min().values
            recent_hi = pd.Series(h).shift(1).rolling(lookback, min_periods=3).max().values

            for s_end in [11, 13]:  # 11:00 UTC (13:00 Madrid) o 13:00 UTC (15:00 Madrid)
                for min_wick in [0.45, 0.50, 0.55]:
                    for tgt_pts in [15.0, 18.0, 20.0, 25.0, 30.0]:
                        for sl_mult in [2.0, 2.5, 3.0]:
                            trades = []
                            i = 210
                            while i < n - 1:
                                hr = hrs[i]
                                if not (7 <= hr <= s_end):
                                    i += 1
                                    continue
                                cur_atr = atr[i]
                                if not np.isfinite(cur_atr) or cur_atr <= 0:
                                    i += 1
                                    continue

                                # Filtro 1: Tendencia y estructura de rebote institucional
                                # Compras: Sobre SMA200 y EMA20, barrido de mínimo reciente con absorción fuerte
                                is_long = (
                                    (c[i] > sma200[i])
                                    and (c[i] > ema20[i])
                                    and (l[i] <= recent_lo[i])
                                    and (lower_wick[i] >= min_wick)
                                    and (clv[i] >= 0.70)
                                )
                                # Ventas: Bajo SMA200 y EMA20, barrido de máximo reciente con rechazo vendedor
                                is_short = (
                                    (c[i] < sma200[i])
                                    and (c[i] < ema20[i])
                                    and (h[i] >= recent_hi[i])
                                    and (upper_wick[i] >= min_wick)
                                    and (clv[i] <= 0.30)
                                )

                                side = 1 if is_long else (-1 if is_short else 0)
                                if side == 0:
                                    i += 1
                                    continue

                                k = i + 1
                                entry = o[k] + side * spr_cost * 0.5
                                tp_px = entry + side * tgt_pts
                                stop_dist = max(cur_atr * sl_mult, tgt_pts * 1.5)
                                sl_px = entry - side * stop_dist

                                exit_px = None
                                for j in range(k, min(n, k + 10)):
                                    hit_sl = (l[j] <= sl_px) if side == 1 else (h[j] >= sl_px)
                                    hit_tp = (h[j] >= tp_px) if side == 1 else (l[j] <= tp_px)
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
                                    j = min(n - 1, k + 9)
                                    exit_px = c[j] - side * spr_cost * 0.5

                                pnl = side * (exit_px - entry) - spr_cost * 0.5
                                r_val = pnl / stop_dist
                                trades.append(r_val)
                                i = j + 1

                            if len(trades) >= 20:
                                r_arr = np.array(trades)
                                m = metrics(r_arr)
                                if m["win_rate"] >= 75.0 and m["profit_factor"] >= 1.20:
                                    best_overall.append({
                                        "tf": tf_label,
                                        "target": tgt_pts,
                                        "sl_mult": sl_mult,
                                        "min_wick": min_wick,
                                        "session_end": s_end,
                                        "lookback": lookback,
                                        "n": m["n"],
                                        "win_rate": m["win_rate"],
                                        "pf": m["profit_factor"],
                                        "sum_r": r_arr.sum(),
                                        "mean_r": m["mean_r"],
                                    })

    best_df = pd.DataFrame(best_overall)
    if not best_df.empty:
        best_df.sort_values(by=["win_rate", "pf"], ascending=[False, False], inplace=True)
        print(f"\nSe han encontrado {len(best_df)} configuraciones en el IBEX 35 con Win Rate >= 75.0% y Profit Factor >= 1.20:")
        print(f"{'TF':<12} | {'Target':<7} | {'SL':<6} | {'Mecha':<6} | {'Sesión':<11} | {'N':<4} | {'Win Rate':<9} | {'PF':<6} | {'Retorno (R)':<12}")
        print("-" * 95)
        for _, row in best_df.head(15).iterrows():
            ses_str = f"07:00-{int(row['session_end'])}:00"
            print(
                f"{row['tf']:<12} | {row['target']:<5.1f}pt | {row['sl_mult']:<4.1f}x | {row['min_wick']*100:<4.0f}% | "
                f"{ses_str:<11} | {int(row['n']):<4d} | {row['win_rate']:6.1f}%  | {row['pf']:<6.2f} | {row['sum_r']:+6.2f} R"
            )
    else:
        print("\nNo se encontraron configuraciones en ese primer barrido. Probando arquitecturas alternativas...")

    mt5.shutdown()


if __name__ == "__main__":
    run_ibex_deep_search()
