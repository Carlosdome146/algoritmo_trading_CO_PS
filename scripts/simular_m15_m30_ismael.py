"""Simulación de 2.000 EUR en Cartera Intradía M15/M30 (Evaluación cada 15-30 min estilo Ismael)."""
from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from trading_v2.research.regime_lab_v3 import metrics


def get_intraday_trades(sym: str, tf, tf_label: str, sigma: float, rsi_th: float, stop_m: float, exit_p: int = 5) -> pd.DataFrame:
    r = mt5.copy_rates_from_pos(sym, tf, 0, 35000)
    if r is None or len(r) == 0:
        return pd.DataFrame()
    df = pd.DataFrame(r)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)

    c, h, l, o = df["close"].values, df["high"].values, df["low"].values, df["open"].values
    n = len(df)
    spr_cost = 0.8 if "GERMANY" in sym else (0.4 if "SP500" in sym else (3.0 if "IBEX" in sym else 0.00006))

    tr = np.maximum(h - l, np.abs(h - pd.Series(c).shift(1).fillna(c[0]).values))
    atr = pd.Series(tr).rolling(20, min_periods=10).mean().values

    delta = pd.Series(c).diff()
    up = delta.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    rsi2 = (100 - 100 / (1 + up / dn.replace(0, np.nan))).values

    sma200 = pd.Series(c).rolling(200, min_periods=50).mean().values
    sma500 = pd.Series(c).rolling(500, min_periods=100).mean().values
    sma20 = pd.Series(c).rolling(20, min_periods=10).mean().values
    std20 = pd.Series(c).rolling(20, min_periods=10).std(ddof=0).values
    sma_ex = pd.Series(c).rolling(exit_p, min_periods=3).mean().values
    bb_lo = sma20 - sigma * std20
    hrs = df.index.hour.values

    s_start, s_end = (7, 16) if sym != "[SP500]" else (13, 20)

    trades = []
    i = 505
    while i < n - 1:
        if not (s_start <= hrs[i] <= s_end):
            i += 1
            continue
        cond = (c[i] > sma200[i]) and (c[i] > sma500[i]) and (rsi2[i] < rsi_th) and (c[i] <= bb_lo[i])
        cur_atr = atr[i]
        if not cond or not np.isfinite(cur_atr) or cur_atr <= 0:
            i += 1
            continue

        k = i + 1
        entry = o[k] + spr_cost * 0.5
        stop = entry - stop_m * cur_atr
        exit_px = None
        for j in range(k, min(n, k + 24)):
            if l[j] <= stop:
                exit_px = stop - spr_cost * 0.5
                break
            if c[j] > sma_ex[j] and j + 1 < n:
                exit_px = o[j + 1] - spr_cost * 0.5
                j = j + 1
                break
        if exit_px is None:
            j = min(n - 1, k + 23)
            exit_px = c[j] - spr_cost * 0.5

        r_val = (exit_px - entry) / (stop_m * cur_atr)
        mins = int((df.index[j] - df.index[k]).total_seconds() // 60)
        trades.append({
            "entry_time": df.index[k],
            "exit_time": df.index[j],
            "sym": sym,
            "tf": tf_label,
            "entry_px": entry,
            "exit_px": exit_px,
            "duration_min": max(15, mins),
            "r": r_val,
        })
        i = j + 1

    return pd.DataFrame(trades)


def main():
    if not mt5.initialize():
        return

    t_eu_m15 = get_intraday_trades("EURUSD", mt5.TIMEFRAME_M15, "M15", 2.2, 5, 4.0, 5)
    t_eu_m30 = get_intraday_trades("EURUSD", mt5.TIMEFRAME_M30, "M30", 2.2, 8, 2.5, 5)
    t_dax_m30 = get_intraday_trades("GERMANY40", mt5.TIMEFRAME_M30, "M30", 2.2, 5, 4.0, 5)
    t_sp_m30 = get_intraday_trades("[SP500]", mt5.TIMEFRAME_M30, "M30", 1.8, 5, 4.0, 5)

    # Filtrar al periodo común donde los 3 activos tienen datos M30/M15 (desde Nov 2023 a Oct 2026: ~3 años)
    all_intraday = pd.concat([t_eu_m15, t_eu_m30, t_dax_m30, t_sp_m30], ignore_index=True)
    all_intraday = all_intraday[all_intraday["entry_time"] >= "2024-01-01"].sort_values("entry_time").reset_index(drop=True)

    cap = 2000.0
    peak = 2000.0
    max_dd = 0.0
    pnls = []
    eqs = []
    for r_v in all_intraday["r"]:
        p = (cap * 0.015) * r_v  # 1.5% riesgo intradía
        cap += p
        peak = max(peak, cap)
        max_dd = max(max_dd, (peak - cap) / peak * 100)
        pnls.append(p)
        eqs.append(cap)

    all_intraday["pnl_eur"] = pnls
    all_intraday["equity"] = eqs
    all_intraday["year"] = all_intraday["entry_time"].dt.year

    print("===============================================================================================")
    print("SIMULACIÓN INTRADÍA M15 / M30 (EVALUACIÓN CADA 15-30 MIN ESTILO ISMAEL) CON 2.000 EUR (2024-2026)")
    print("===============================================================================================")
    for yr, grp in all_intraday.groupby("year"):
        wr = (grp["r"] > 0).mean() * 100
        print(f"Año {yr} | Operaciones: {len(grp):<3d} | WinRate: {wr:5.1f}% | R Total: {grp['r'].sum():+6.2f}R | Saldo Fin Año: {grp['equity'].iloc[-1]:,.2f} EUR")
    print("-" * 95)
    m_tot = metrics(all_intraday["r"].to_numpy())
    print(f"TOTAL (2024-2026): N={m_tot['n']} trades | WinRate={m_tot['win_rate']:.1f}% | PF={m_tot['profit_factor']:.2f} | MaxDD={max_dd:.2f}% | 2.000€ -> {cap:,.2f}€")

    print("\nÚLTIMAS 20 OPERACIONES INTRADÍA (M15 / M30):")
    print(f"{'Fecha y Hora (UTC)':<18} | {'Activo':<10} | {'TF':<4} | {'Entrada':<9} | {'Salida':<9} | {'Duración':<8} | {'Resultado':<10} | {'PnL (€)':<9} | {'Saldo'}")
    print("-" * 105)
    for _, row in all_intraday.tail(20).iterrows():
        dt_s = row["entry_time"].strftime("%Y-%m-%d %H:%M")
        sym = row["sym"]
        epx = f"{row['entry_px']:.4f}" if sym == "EURUSD" else f"{row['entry_px']:.1f}"
        xpx = f"{row['exit_px']:.4f}" if sym == "EURUSD" else f"{row['exit_px']:.1f}"
        tag = "WIN " if row["r"] > 0 else "LOSS"
        print(f"{dt_s:<18} | {sym:<10} | {row['tf']:<4} | {epx:<9} | {xpx:<9} | {row['duration_min']:>4d} min | {tag} {row['r']:+5.2f}R | {row['pnl_eur']:+7.2f}€ | {row['equity']:8.2f}€")

    mt5.shutdown()


if __name__ == "__main__":
    main()
