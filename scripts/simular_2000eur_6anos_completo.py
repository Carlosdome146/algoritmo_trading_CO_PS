"""Simulación Retrospectiva de 6 a 8.9 años (99.999 barras MT5) con 2.000,00 EUR iniciales
aplicando nuestro Modelo Unificado Intradía M15/M30 en los 4 activos de la cartera."""
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


def get_asset_trades_99k(
    sym: str,
    tf,
    tf_label: str,
    sigma: float,
    rsi_th: float,
    stop_m: float,
    tp_units: float,
    min_wick: float,
    clv_th: float,
    s_start: int,
    s_end: int,
    use_keltner: bool = False,
    max_opp_wick: float | None = None,
) -> tuple[pd.DataFrame, dict]:
    r = mt5.copy_rates_from_pos(sym, tf, 0, 99999)
    if r is None or len(r) == 0:
        return pd.DataFrame(), {}
    df = pd.DataFrame(r)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    df.sort_index(inplace=True)
    df = df[~df.index.duplicated(keep="first")]

    c, h, l, o = df["close"].values, df["high"].values, df["low"].values, df["open"].values
    n = len(df)
    start_dt = df.index[0]
    end_dt = df.index[-1]
    years = (end_dt - start_dt).total_seconds() / (365.25 * 86400)

    is_fx = "EUR" in sym
    unit = 0.00010 if is_fx else 1.0
    spr_cost = 0.8 if "GERMANY" in sym else (0.4 if "SP500" in sym else (3.0 if "IBEX" in sym else 0.00006))

    prev_c = pd.Series(c).shift(1).fillna(c[0]).values
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    atr = pd.Series(tr).rolling(20, min_periods=10).mean().values
    atr10 = pd.Series(tr).rolling(10, min_periods=3).mean().values

    delta = pd.Series(c).diff()
    up = delta.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    rsi2 = (100 - 100 / (1 + up / dn.replace(0, np.nan))).values

    sma200 = pd.Series(c).rolling(200, min_periods=50).mean().values
    sma500 = pd.Series(c).rolling(500, min_periods=100).mean().values
    ema20 = pd.Series(c).ewm(span=20, adjust=False).mean().values
    sma20 = pd.Series(c).rolling(20, min_periods=10).mean().values
    std20 = pd.Series(c).rolling(20, min_periods=10).std(ddof=0).values
    sma5 = pd.Series(c).rolling(5, min_periods=3).mean().values
    bb_lo = sma20 - sigma * std20

    # Keltner Channel (Carlos QuantDinger)
    k_ub = ema20 + 1.5 * atr10
    k_lb = ema20 - 1.5 * atr10
    k_rng = np.maximum(k_ub - k_lb, 1e-9)
    k_pos_lo = (l - k_lb) / k_rng

    rng = np.maximum(h - l, 1e-9)
    lower_wick = (np.minimum(o, c) - l) / rng
    upper_wick = (h - np.maximum(o, c)) / rng
    clv = (c - l) / rng
    recent_lo = pd.Series(l).shift(1).rolling(8, min_periods=3).min().values
    hrs = df.index.hour.values

    trades = []
    i = 505
    while i < n - 1:
        if not (s_start <= hrs[i] <= s_end):
            i += 1
            continue
        cur_atr = atr[i]
        if not np.isfinite(cur_atr) or cur_atr <= 0:
            i += 1
            continue

        # Gatillo 1: Bollinger Extreme Dip (Media SMA5)
        cond_bb = (c[i] > sma200[i]) and (c[i] > sma500[i]) and (rsi2[i] < rsi_th) and (c[i] <= bb_lo[i])

        # Gatillo 2: Sniper Ismael Sweep Reclaim + Keltner/Vault
        cond_sniper = (
            (c[i] > sma200[i])
            and (ema20[i] > sma200[i])
            and (c[i] > ema20[i])
            and (l[i] <= recent_lo[i])
            and (lower_wick[i] >= min_wick)
            and (clv[i] >= clv_th)
        )
        if use_keltner:
            cond_sniper = cond_sniper and (k_pos_lo[i] <= 0.35)
        if max_opp_wick is not None:
            cond_sniper = cond_sniper and (upper_wick[i] <= max_opp_wick)

        if not (cond_bb or cond_sniper):
            i += 1
            continue

        k = i + 1
        entry = o[k] + spr_cost * 0.5

        if cond_sniper and not cond_bb:
            # Salida Francotirador con Breakeven Causal
            tgt_dist = min(tp_units * unit, 0.65 * cur_atr) if not is_fx else (0.65 * cur_atr)
            tp_px = entry + tgt_dist
            stop_dist = 2.5 * cur_atr
            cur_sl = entry - stop_dist
            be_trig = entry + 0.30 * cur_atr
            be_lock = entry + spr_cost * 1.5
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
            r_val = (exit_px - entry) / stop_dist
        else:
            # Salida Reversión Dinámica SMA5
            stop_dist = stop_m * cur_atr
            stop = entry - stop_dist
            exit_px = None
            for j in range(k, min(n, k + 24)):
                if l[j] <= stop:
                    exit_px = stop - spr_cost * 0.5
                    break
                if c[j] > sma5[j] and j + 1 < n:
                    exit_px = o[j + 1] - spr_cost * 0.5
                    j = j + 1
                    break
            if exit_px is None:
                j = min(n - 1, k + 23)
                exit_px = c[j] - spr_cost * 0.5
            r_val = (exit_px - entry) / stop_dist

        mins = int((df.index[j] - df.index[k]).total_seconds() // 60)
        trades.append({
            "entry_time": df.index[k],
            "exit_time": df.index[j],
            "sym": sym,
            "tf": tf_label,
            "entry_px": entry,
            "exit_px": exit_px,
            "duration_min": max(15, mins),
            "r": float(r_val),
            "win": float(r_val) > 0,
        })
        i = j + 1

    tdf = pd.DataFrame(trades)
    if len(tdf) == 0:
        return tdf, {}
    m = metrics(tdf["r"].to_numpy())
    info = {
        "sym": sym,
        "tf": tf_label,
        "bars": n,
        "start": start_dt.strftime("%Y-%m-%d"),
        "end": end_dt.strftime("%Y-%m-%d"),
        "years": years,
        "n": m["n"],
        "wins": int((tdf["r"] > 0).sum()),
        "losses": int((tdf["r"] <= 0).sum()),
        "wr": m["win_rate"],
        "pf": m["profit_factor"],
        "sum_r": float(tdf["r"].sum()),
    }
    return tdf, info


def main():
    if not mt5.initialize():
        return

    from scripts.simulacion_2000eur_max_historico_6anos import simulate_portfolio_compounding

    print("===============================================================================================================")
    print("AUDITORÍA DE MÁXIMA PROFUNDIDAD HISTÓRICA EN MT5 (99.999 BARRAS: 2018 A 2026 — HASTA 8.9 AÑOS)")
    print("===============================================================================================================")

    assets_cfg = [
        # (sym, tf, tf_label, sigma, rsi_th, stop_m, tp_units, min_wick, clv_th, s_start, s_end, use_keltner, max_opp_wick)
        ("EURUSD", mt5.TIMEFRAME_M15, "M15", 2.2, 5.0, 4.0, 3.0, 0.55, 0.85, 7, 16, False, None),
        ("EURUSD", mt5.TIMEFRAME_M30, "M30", 2.2, 8.0, 2.5, 3.5, 0.55, 0.85, 7, 16, False, None),
        ("GERMANY40", mt5.TIMEFRAME_M30, "M30", 2.2, 5.0, 4.0, 12.0, 0.45, 0.75, 7, 15, True, None),
        ("[SP500]", mt5.TIMEFRAME_M30, "M30", 1.8, 5.0, 4.0, 4.0, 0.45, 0.75, 13, 20, False, 0.12),
        ("[IBEX35]", mt5.TIMEFRAME_M15, "M15", 2.2, 5.0, 3.5, 15.0, 0.55, 0.75, 7, 11, False, 0.12),
    ]

    dfs = []
    print(f"\n{'ACTIVO':<11} | {'TF':<4} | {'PERIODO AUDITADO':<23} | {'AÑOS':<5} | {'BARRAS':<6} | {'TRADES':<6} | {'G / P':<9} | {'WIN RATE':<8} | {'PF':<5} | {'SUM R'}")
    print("-" * 108)
    for cfg in assets_cfg:
        tdf, info = get_asset_trades_99k(*cfg)
        if len(tdf) > 0:
            dfs.append(tdf)
            gp = f"{info['wins']:3d}/{info['losses']:2d}"
            periodo = f"{info['start']} a {info['end']}"
            print(f"{info['sym']:<11} | {info['tf']:<4} | {periodo:<23} | {info['years']:4.1f}  | {info['bars']:<6d} | {info['n']:<6d} | {gp:<9} | {info['wr']:6.2f}%  | {info['pf']:5.2f} | {info['sum_r']:+6.2f}R")

    all_df = pd.concat(dfs, ignore_index=True).sort_values("entry_time").reset_index(drop=True)
    all_records = all_df.to_dict("records")

    # 1. Simulación a 6 Años (Octubre 2020 a Octubre 2026, equivalente al horizonte de 6 años de Ismael)
    records_6y = [r for r in all_records if r["entry_time"] >= pd.Timestamp("2020-10-27", tz="UTC")]
    # 2. Simulación a ~8.9 Años completos (2018 a 2026, todo el histórico disponible en MT5)
    records_full = [r for r in all_records if r["entry_time"] >= pd.Timestamp("2018-01-01", tz="UTC")]

    for title, dataset in [
        ("HORIZONTE DE 6 AÑOS DE ISMAEL (Oct 2020 – Oct 2026)", records_6y),
        ("HISTÓRICO COMPLETO MT5 DE ~8.9 AÑOS (2018 – 2026)", records_full),
    ]:
        print(f"\n===============================================================================================================")
        print(f"SIMULACIÓN CON 2.000,00 € INICIALES — {title}")
        print(f"===============================================================================================================")
        for r_pct, r_lbl in [
            (0.005, "1. Riesgo DEMO Ultra-Conservador (0.50% por operación)"),
            (0.015, "2. Riesgo Institucional Estándar (1.50% por operación)"),
            (0.025, "3. Riesgo Compuesto Dinámico (2.50% por operación)"),
        ]:
            sim = simulate_portfolio_compounding(dataset, initial_capital=2000.0, risk_pct=r_pct)
            print(f"\n>> {r_lbl}:")
            print(f"   Capital Inicial: 2.000,00 €  --->  Capital Final: {sim['final_capital']:,.2f} €  (Beneficio Neto: +{sim['net_profit']:,.2f} € | ROI: +{sim['roi_pct']:.2f}%)")
            print(f"   Operaciones: {sim['total_trades']} ({sim['wins']} Ganadas / {sim['losses']} Perdidas) | Win Rate Global: {sim['wr']:.2f}% | Max Drawdown: {sim['max_dd_pct']:.2f}% ({sim['max_dd_eur']:.2f} €)")

            if r_pct == 0.015:
                print(f"\n   EVOLUCIÓN AÑO A AÑO (Con 2.000,00 € iniciales al 1.50% de riesgo por operación):")
                print(f"   {'AÑO':<6} | {'SALDO INICIAL':<14} | {'TRADES':<7} | {'G / P':<9} | {'WIN RATE':<9} | {'BENEFICIO (€)':<14} | {'SALDO FINAL'}")
                print("   " + "-" * 80)
                for yr, yd in sorted(sim["yearly"].items()):
                    wr_y = (yd["wins"] / yd["trades"] * 100.0) if yd["trades"] > 0 else 0.0
                    gp_y = f"{yd['wins']:3d}/{yd['losses']:2d}"
                    print(f"   {yr:<6} | {yd['start_cap']:11,.2f} € | {yd['trades']:<7d} | {gp_y:<9} | {wr_y:6.2f}%   | {yd['pnl_eur']:+11,.2f} € | {yd['end_cap']:11,.2f} €")

    mt5.shutdown()


if __name__ == "__main__":
    main()
