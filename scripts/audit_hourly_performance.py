import sys
sys.path.insert(0, ".")
import pandas as pd
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime, timezone

from trading_v2.strategies.micro_scalping import (
    SniperScalpConfig,
    generate_sniper_signals,
    compute_sniper_indicators,
)

mt5.initialize()
d_from = datetime(2022, 1, 1, tzinfo=timezone.utc)
d_to = datetime(2026, 11, 7, tzinfo=timezone.utc)
rates = mt5.copy_rates_range("GERMANY40", mt5.TIMEFRAME_M30, d_from, d_to)
df = pd.DataFrame(rates)
df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
df.set_index("time", inplace=True)
df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close"}, inplace=True)

cfg = SniperScalpConfig(
    symbol="GERMANY40", target_units=22.0, stop_units=35.0,
    session_start_h=7, session_end_h=17, min_rejection_wick=0.35,
    use_h1_filter=True, use_ker_filter=True, max_ker_trend=0.45,
    cooldown_bars=2, use_climax_filter=True, allow_short=True
)
sig_df = generate_sniper_signals(df, cfg)
signals = sig_df["signal"].to_numpy().copy()

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
        entry_px = opens[i + 1] + (1.2 if sig == 1 else 0)
        sl_px = entry_px - 35.0 if sig == 1 else entry_px + 35.0
        tp_px = entry_px + 22.0 if sig == 1 else entry_px - 22.0
        exit_px = None
        for j in range(i + 1, min(i + 9, n)):
            if sig == 1:
                if lows[j] <= sl_px and highs[j] >= tp_px:
                    exit_px = tp_px if closes[j] > opens[j] else sl_px
                    break
                elif highs[j] >= tp_px:
                    exit_px = tp_px
                    break
                elif lows[j] <= sl_px:
                    exit_px = sl_px
                    break
            else:
                if highs[j] + 1.2 >= sl_px and lows[j] + 1.2 <= tp_px:
                    exit_px = tp_px if closes[j] < opens[j] else sl_px
                    break
                elif lows[j] + 1.2 <= tp_px:
                    exit_px = tp_px
                    break
                elif highs[j] + 1.2 >= sl_px:
                    exit_px = sl_px
                    break
        if exit_px is None:
            exit_px = closes[min(i + 8, n - 1)]
        pnl = ((exit_px - entry_px) / 35.0) * 30.58 if sig == 1 else ((entry_px - exit_px) / 35.0) * 30.58
        trades.append({
            "entry_time": entry_time,
            "hour_utc": entry_time.hour,
            "minute_utc": entry_time.minute,
            "pnl": pnl,
            "win": pnl > 0
        })
        i = j + 2
    else:
        i += 1

df_t = pd.DataFrame(trades)
print("TOTAL TRADES:", len(df_t))

# Agrupar por hora de entrada UTC
print("\nESTADISTICAS POR HORA DE ENTRADA (UTC):")
print("Hora UTC | Hora CET  | Trades | Win Rate | PnL Total (EUR)")
print("-" * 55)
for h in range(7, 18):
    sub = df_t[df_t["hour_utc"] == h]
    if len(sub) > 0:
        wr = sub["win"].mean() * 100
        tot_pnl = sub["pnl"].sum()
        print(f"{h:02d}:00    | {h+1:02d}:00    | {len(sub):6d} | {wr:7.1f}% | {tot_pnl:+10.2f} EUR")

# Desglose especifico de la hora 07:00 UTC (08:00 CET)
sub_07 = df_t[df_t["hour_utc"] == 7]
print("\nDESGLOSE DE LA HORA 07:00 UTC (08:00 CET):")
for m in [0, 30]:
    sub_m = sub_07[sub_07["minute_utc"] == m]
    if len(sub_m) > 0:
        wr = sub_m["win"].mean() * 100
        tot = sub_m["pnl"].sum()
        print(f"07:{m:02d} UTC (08:{m:02d} CET) | Trades: {len(sub_m):4d} | Win Rate: {wr:5.1f}% | PnL: {tot:+8.2f} EUR")
