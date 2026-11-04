#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import MetaTrader5 as mt5
import pandas as pd
from scripts.backtest_4years_portfolio import load_4year_bars
from trading_v2.strategies.micro_scalping import SniperScalpConfig, generate_sniper_signals

mt5.initialize()

# Configuraciones optimizadas y calibradas por activo
ASSETS = {
    "GERMANY40": {
        "target_u": 12.0, "stop_u": 35.0, "sweep_u": 8.0,
        "s_start": 7, "s_end": 15, "min_wick": 0.45,
        "use_keltner": True, "max_opp_wick": None, "allow_short": False,
        "spread": 1.2, "tf": mt5.TIMEFRAME_M30
    },
    "[SP500]": {
        "target_u": 4.0, "stop_u": 12.0, "sweep_u": 2.5,
        "s_start": 13, "s_end": 20, "min_wick": 0.45,
        "use_keltner": False, "max_opp_wick": 0.12, "allow_short": False,
        "spread": 0.5, "tf": mt5.TIMEFRAME_M30
    },
    "[DJI30]": {
        "target_u": 45.0, "stop_u": 90.0, "sweep_u": 20.0,
        "s_start": 13, "s_end": 20, "min_wick": 0.45,
        "use_keltner": False, "max_opp_wick": 0.12, "allow_short": False,
        "spread": 2.5, "tf": mt5.TIMEFRAME_M30
    },
    "US100": {
        "target_u": 25.0, "stop_u": 60.0, "sweep_u": 10.0,
        "s_start": 13, "s_end": 20, "min_wick": 0.40,
        "use_keltner": False, "max_opp_wick": 0.15, "allow_short": False,
        "spread": 1.0, "tf": mt5.TIMEFRAME_M30
    },
    "GOLD": {
        "target_u": 4.0, "stop_u": 12.0, "sweep_u": 2.0,
        "s_start": 12, "s_end": 19, "min_wick": 0.45,
        "use_keltner": False, "max_opp_wick": 0.12, "allow_short": False,
        "spread": 0.35, "tf": mt5.TIMEFRAME_M30
    },
    "EURUSD": {
        "target_u": 3.5, "stop_u": 5.5, "sweep_u": 0.0,
        "s_start": 7, "s_end": 17, "min_wick": 0.40,
        "use_keltner": False, "max_opp_wick": None, "allow_short": True,
        "spread": 0.00010, "tf": mt5.TIMEFRAME_M15
    },
    "[IBEX35]": {
        "target_u": 20.0, "stop_u": 45.0, "sweep_u": 5.0,
        "s_start": 7, "s_end": 15, "min_wick": 0.45,
        "use_keltner": False, "max_opp_wick": None, "allow_short": False,
        "spread": 5.0, "tf": mt5.TIMEFRAME_M30
    },
}

all_portfolio_trades = []

for sym, p in ASSETS.items():
    df = load_4year_bars(sym, p["tf"])
    if df.empty or len(df) < 500:
        continue

    is_fx = sym == "EURUSD"
    unit = 0.00010 if is_fx else 1.0
    tp_dist = p["target_u"] * unit
    sl_dist = p["stop_u"] * unit
    spread = p["spread"]
    risk_eur = 46.15

    cfg = SniperScalpConfig(
        symbol=sym,
        target_units=p["target_u"],
        stop_units=p["stop_u"],
        session_start_h=p["s_start"],
        session_end_h=p["s_end"],
        max_holding_bars=6,
        min_sweep_units=p["sweep_u"],
        min_rejection_wick=p["min_wick"],
        use_h1_filter=True,
        use_keltner_filter=p["use_keltner"],
        max_opposite_wick=p["max_opp_wick"],
        allow_short=p["allow_short"],
        use_ker_filter=True,
        max_ker_trend=0.45,
        enable_m4_fade=True,
        enable_yeboster_reclaim=True,
    )

    sig_df = generate_sniper_signals(df, cfg)
    signals = sig_df["signal"].to_numpy()
    times = df.index
    opens = df["Open"].to_numpy()
    highs = df["High"].to_numpy()
    lows = df["Low"].to_numpy()
    closes = df["Close"].to_numpy()
    n = len(df)

    trades = []
    i = 0
    while i < n - 1:
        sig = signals[i]
        if sig != 0:
            entry_time = times[i + 1]
            if sig == 1:
                entry_price = opens[i + 1] + spread
                sl_price = entry_price - sl_dist
                tp_price = entry_price + tp_dist
            else:
                entry_price = opens[i + 1]
                sl_price = entry_price + sl_dist
                tp_price = entry_price - tp_dist

            be_active = False
            be_trig = 0.45 * tp_dist if not is_fx else 2.0 * 0.00010
            be_lock = 0.10 * tp_dist if not is_fx else 0.5 * 0.00010

            exit_time = None
            exit_price = None
            exit_reason = None

            for j in range(i + 1, min(i + 1 + 8, n)):
                bar_h = highs[j]
                bar_l = lows[j]
                bar_c = closes[j]

                if sig == 1:
                    hit_sl = bar_l <= sl_price
                    hit_tp = bar_h >= tp_price

                    if hit_sl and hit_tp:
                        exit_price = sl_price
                        exit_reason = "STOP_LOSS" if not be_active else "BREAKEVEN"
                        exit_time = times[j]
                        break
                    elif hit_tp:
                        exit_price = tp_price
                        exit_reason = "TAKE_PROFIT"
                        exit_time = times[j]
                        break
                    elif hit_sl:
                        exit_price = sl_price
                        exit_reason = "STOP_LOSS" if not be_active else "BREAKEVEN"
                        exit_time = times[j]
                        break

                    if not be_active and (bar_h - entry_price) >= be_trig:
                        be_active = True
                        sl_price = max(sl_price, entry_price + be_lock)
                else:
                    current_ask_low = bar_l + spread
                    current_ask_high = bar_h + spread
                    hit_sl = current_ask_high >= sl_price
                    hit_tp = current_ask_low <= tp_price

                    if hit_sl and hit_tp:
                        exit_price = sl_price
                        exit_reason = "STOP_LOSS" if not be_active else "BREAKEVEN"
                        exit_time = times[j]
                        break
                    elif hit_tp:
                        exit_price = tp_price
                        exit_reason = "TAKE_PROFIT"
                        exit_time = times[j]
                        break
                    elif hit_sl:
                        exit_price = sl_price
                        exit_reason = "STOP_LOSS" if not be_active else "BREAKEVEN"
                        exit_time = times[j]
                        break

                    if not be_active and (entry_price - bar_l) >= be_trig:
                        be_active = True
                        sl_price = min(sl_price, entry_price - be_lock)

            if exit_price is None:
                j_end = min(i + 1 + 8, n - 1)
                exit_time = times[j_end]
                exit_price = closes[j_end] if sig == 1 else (closes[j_end] + spread)
                exit_reason = "TIME_EXIT"

            price_delta = (exit_price - entry_price) if sig == 1 else (entry_price - exit_price)
            r_return = price_delta / sl_dist
            pnl_eur = r_return * risk_eur
            trades.append({
                "symbol": sym,
                "direction": "BUY" if sig == 1 else "SELL",
                "entry_time": entry_time,
                "exit_time": exit_time,
                "pnl_eur": pnl_eur,
                "exit_reason": exit_reason,
                "year": entry_time.year,
            })
            i = j
        else:
            i += 1

    all_portfolio_trades.extend(trades)
    df_t = pd.DataFrame(trades)
    wins = df_t[df_t["pnl_eur"] > 0]
    losses = df_t[df_t["pnl_eur"] < 0]
    n_t = len(df_t)
    wr = (len(wins) / n_t) * 100 if n_t > 0 else 0
    pnl = df_t["pnl_eur"].sum()
    gp = wins["pnl_eur"].sum() if len(wins) > 0 else 0
    gl = abs(losses["pnl_eur"].sum()) if len(losses) > 0 else 1e-6
    pf = gp / gl
    print(f"{sym:12s} | Trades: {n_t:4d} | Win Rate: {wr:5.1f}% | PF: {pf:4.2f} | PnL: {pnl:+9.2f} EUR")

# Consolidado Cartera
df_all = pd.DataFrame(all_portfolio_trades).sort_values("entry_time")
wins_all = df_all[df_all["pnl_eur"] > 0]
losses_all = df_all[df_all["pnl_eur"] < 0]
n_all = len(df_all)
wr_all = (len(wins_all) / n_all) * 100
total_pnl = df_all["pnl_eur"].sum()
gp = wins_all["pnl_eur"].sum()
gl = abs(losses_all["pnl_eur"].sum())
pf = gp / gl

df_all["cum_pnl"] = df_all["pnl_eur"].cumsum()
peak = df_all["cum_pnl"].cummax()
max_dd = (peak - df_all["cum_pnl"]).max()

print("\n" + "=" * 80)
print("AUDITORIA CONSOLIDADA CARTERA INSTITUCIONAL SNIPER (2022 - 2026)")
print("=" * 80)
print(f"Total Operaciones: {n_all}")
print(f"Ganadoras: {len(wins_all)} | Perdedoras: {len(losses_all)}")
print(f"Tasa de Acierto Global (Win Rate): {wr_all:.2f}%")
print(f"Factor de Beneficio (Profit Factor): {pf:.2f}")
print(f"Beneficio Neto Total: {total_pnl:+,.2f} EUR")
print(f"Drawdown Maximo: {max_dd:.2f} EUR ({(max_dd / 3000.0) * 100:.2f}%)")

print("\nDesglose por anos:")
for y in sorted(df_all["year"].unique()):
    df_y = df_all[df_all["year"] == y]
    w = len(df_y[df_y["pnl_eur"] > 0])
    n_y = len(df_y)
    wr_y = (w / n_y) * 100 if n_y > 0 else 0
    pnl_y = df_y["pnl_eur"].sum()
    gp_y = df_y[df_y["pnl_eur"] > 0]["pnl_eur"].sum()
    gl_y = abs(df_y[df_y["pnl_eur"] < 0]["pnl_eur"].sum())
    pf_y = gp_y / gl_y if gl_y > 0 else float("inf")
    print(f"  {y} | Trades: {n_y:4d} | Win Rate: {wr_y:5.1f}% | PF: {pf_y:4.2f} | PnL: {pnl_y:+9.2f} EUR")

mt5.shutdown()
