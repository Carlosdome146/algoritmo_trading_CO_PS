"""Simulación Retrospectiva de Máxima Profundidad Histórica en MT5 (99.999 barras: hasta 8.9 años)
con Capital Inicial de 2.000,00 EUR aplicando el Modelo Francotirador Definitivo (con mejoras de Carlos y Vault)."""
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


def extract_asset_trades_max_history(
    symbol: str,
    tf_code: int,
    tf_label: str,
    target_u: float,
    sl_mult: float,
    min_wick: float,
    clv_th: float,
    s_start: int,
    s_end: int,
    use_keltner: bool = False,
    max_opp_wick: float | None = None,
) -> tuple[list[dict], dict]:
    r = mt5.copy_rates_from_pos(symbol, tf_code, 0, 99999)
    if r is None or len(r) == 0:
        return [], {}

    df = pd.DataFrame(r)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    df.sort_index(inplace=True)
    df = df[~df.index.duplicated(keep="first")]

    c = df["close"].values
    h = df["high"].values
    l = df["low"].values
    o = df["open"].values
    n = len(df)

    start_dt = df.index[0]
    end_dt = df.index[-1]
    years = (end_dt - start_dt).total_seconds() / (365.25 * 86400)

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

    k_ub = ema20 + 1.5 * atr10
    k_lb = ema20 - 1.5 * atr10
    k_rng = np.maximum(k_ub - k_lb, 1e-9)
    k_pos_lo = (l - k_lb) / k_rng
    k_pos_hi = (h - k_lb) / k_rng

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

        if is_fx:
            long_sig = (
                (c[i] > sma200[i])
                and (ema20[i] > sma200[i])
                and (c[i] > ema20[i])
                and (l[i] <= recent_lo[i])
                and (lower_wick[i] >= min_wick)
                and (clv[i] >= clv_th)
            )
            short_sig = (
                (c[i] < sma200[i])
                and (ema20[i] < sma200[i])
                and (c[i] < ema20[i])
                and (h[i] >= recent_hi[i])
                and (upper_wick[i] >= min_wick)
                and (clv[i] <= (1.0 - clv_th))
            )
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

        if use_keltner:
            long_sig = long_sig and (k_pos_lo[i] <= 0.35)
            short_sig = short_sig and (k_pos_hi[i] >= 0.65)

        if max_opp_wick is not None:
            long_sig = long_sig and (upper_wick[i] <= max_opp_wick)
            short_sig = short_sig and (lower_wick[i] <= max_opp_wick)

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
        win = pnl > 0
        if win:
            wins += 1
        else:
            losses += 1

        trades.append({
            "entry_time": df.index[k],
            "exit_time": df.index[j],
            "symbol": symbol,
            "tf": tf_label,
            "side": "LONG" if side == 1 else "SHORT",
            "r": float(r_val),
            "win": win,
        })
        i = j + 1

    tot = wins + losses
    wr = (wins / tot * 100.0) if tot > 0 else 0.0
    r_arr = np.array([t["r"] for t in trades]) if tot > 0 else np.array([0.0])
    m = metrics(r_arr) if tot > 0 else {"profit_factor": 0.0}

    summary = {
        "symbol": symbol,
        "tf": tf_label,
        "bars": n,
        "start": start_dt.strftime("%Y-%m-%d"),
        "end": end_dt.strftime("%Y-%m-%d"),
        "years": years,
        "total": tot,
        "wins": wins,
        "losses": losses,
        "wr": wr,
        "pf": m["profit_factor"],
        "sum_r": float(r_arr.sum()) if tot > 0 else 0.0,
    }
    return trades, summary


def simulate_portfolio_compounding(all_trades: list[dict], initial_capital: float = 2000.0, risk_pct: float = 0.015) -> dict:
    df_t = pd.DataFrame(all_trades).sort_values("entry_time").reset_index(drop=True)
    capital = initial_capital
    peak = initial_capital
    max_dd_pct = 0.0
    max_dd_eur = 0.0

    yearly = {}
    for _, row in df_t.iterrows():
        yr = row["entry_time"].year
        if yr not in yearly:
            yearly[yr] = {"start_cap": capital, "trades": 0, "wins": 0, "losses": 0, "pnl_eur": 0.0, "sum_r": 0.0}

        risk_eur = capital * risk_pct
        pnl_eur = float(row["r"]) * risk_eur
        capital += pnl_eur

        if capital > peak:
            peak = capital
        dd_eur = peak - capital
        dd_pct = (dd_eur / peak) * 100.0 if peak > 0 else 0.0
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
        if dd_eur > max_dd_eur:
            max_dd_eur = dd_eur

        yearly[yr]["trades"] += 1
        if row["win"]:
            yearly[yr]["wins"] += 1
        else:
            yearly[yr]["losses"] += 1
        yearly[yr]["pnl_eur"] += pnl_eur
        yearly[yr]["sum_r"] += float(row["r"])
        yearly[yr]["end_cap"] = capital

    return {
        "initial_capital": initial_capital,
        "final_capital": capital,
        "net_profit": capital - initial_capital,
        "roi_pct": ((capital - initial_capital) / initial_capital) * 100.0,
        "max_dd_pct": max_dd_pct,
        "max_dd_eur": max_dd_eur,
        "total_trades": len(df_t),
        "wins": int(df_t["win"].sum()),
        "losses": int((~df_t["win"]).sum()),
        "wr": float(df_t["win"].mean() * 100.0) if len(df_t) > 0 else 0.0,
        "yearly": yearly,
    }


def main():
    if not mt5.initialize():
        return

    print("=====================================================================================================")
    print("SIMULACIÓN FRANCOTIRADOR PURO EN MÁXIMA PROFUNDIDAD MT5 (99.999 BARRAS: 2018-2026) CON 2.000 €")
    print("=====================================================================================================")

    streams = [
        ("EURUSD", mt5.TIMEFRAME_M30, "M30 (8.1 años)", 3.5, 2.5, 0.55, 0.85, 7, 16, False, None),
        ("GERMANY40", mt5.TIMEFRAME_M15, "M15 (4.5 años)", 12.0, 2.5, 0.45, 0.75, 7, 15, True, None),
        ("[IBEX35]", mt5.TIMEFRAME_M15, "M15 (8.9 años)", 15.0, 2.5, 0.55, 0.70, 7, 11, False, None),
        ("[SP500]", mt5.TIMEFRAME_M15, "M15 (4.2 años)", 4.0, 2.5, 0.45, 0.75, 13, 20, False, 0.12),
    ]

    all_t = []
    for s in streams:
        tr, info = extract_asset_trades_max_history(*s)
        all_t.extend(tr)
        print(f"{info['symbol']:<10} | {info['tf']:<15} | {info['start']} -> {info['end']} | N={info['total']:3d} ({info['wins']}G/{info['losses']}P) | WR={info['wr']:.2f}% | PF={info['pf']:.2f} | R={info['sum_r']:+6.2f}R")

    for r_pct in [0.005, 0.015, 0.025]:
        sim = simulate_portfolio_compounding(all_t, 2000.0, r_pct)
        print(f"\n>> Riesgo {r_pct*100:.2f}% / trade: 2.000,00 € -> {sim['final_capital']:,.2f} € (+{sim['net_profit']:,.2f} € | +{sim['roi_pct']:.2f}%) | N={sim['total_trades']} ({sim['wins']}G/{sim['losses']}P) | WR={sim['wr']:.2f}% | MaxDD={sim['max_dd_pct']:.2f}%")
        if r_pct == 0.015:
            for yr, yd in sorted(sim["yearly"].items()):
                wr_y = yd["wins"] / yd["trades"] * 100
                print(f"   Año {yr} | Saldo Inicial: {yd['start_cap']:8,.2f} € | Trades: {yd['trades']:3d} ({yd['wins']:2d}G/{yd['losses']:2d}P) | WR: {wr_y:5.1f}% | PnL: {yd['pnl_eur']:+8.2f} € | Saldo Final: {yd['end_cap']:8,.2f} €")

    mt5.shutdown()


if __name__ == "__main__":
    main()
