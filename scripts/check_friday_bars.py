import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timezone
import sys
sys.path.insert(0, ".")
from trading_v2.strategies.micro_scalping import SniperScalpConfig, generate_sniper_signals, compute_sniper_indicators

mt5.initialize()
bars = mt5.copy_rates_from_pos("GERMANY40", mt5.TIMEFRAME_M30, 0, 100)
df = pd.DataFrame(bars)
df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
df.set_index("dt", inplace=True)
df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close"}, inplace=True)

fri = df.loc["2026-11-06 05:00:00":"2026-11-06 12:00:00"]
cfg = SniperScalpConfig(
    symbol="GERMANY40", target_units=22.0, stop_units=35.0,
    session_start_h=7, session_end_h=17, min_rejection_wick=0.35,
    cooldown_bars=2, use_h1_filter=True, use_ker_filter=True,
    max_ker_trend=0.45, use_climax_filter=True, allow_short=True
)
sig_df = generate_sniper_signals(df, cfg)
ind = compute_sniper_indicators(df)

for t, row in fri.iterrows():
    sig = sig_df.loc[t, "signal"] if t in sig_df.index else 0
    rsi2 = ind.loc[t, "rsi2"] if t in ind.index else 0
    lw = ind.loc[t, "lower_wick"] if t in ind.index else 0
    clv = ind.loc[t, "clv"] if t in ind.index else 0
    print(f"{t} | Sig={sig:2d} | O={row.Open:7.1f} H={row.High:7.1f} L={row.Low:7.1f} C={row.Close:7.1f} | LW={lw:.2f} CLV={clv:.2f} RSI2={rsi2:.1f}")
