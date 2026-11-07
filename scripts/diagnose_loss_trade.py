import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timezone
import sys
sys.path.insert(0, '.')

mt5.initialize()

from trading_v2.strategies.micro_scalping import SniperScalpConfig, generate_sniper_signals, compute_sniper_indicators

# Copy M30 rates for GERMANY40
rates = mt5.copy_rates_from_pos('GERMANY40', mt5.TIMEFRAME_M30, 0, 50)
df = pd.DataFrame(rates)
df['time_dt'] = pd.to_datetime(df['time'], unit='s')
print('Last 10 bars (Broker time):')
for _, r in df.tail(10).iterrows():
    print(f"{r['time_dt']} | O={r['open']:.1f} H={r['high']:.1f} L={r['low']:.1f} C={r['close']:.1f} Vol={r['tick_volume']}")

# Run indicators
df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'tick_volume': 'Volume'}, inplace=True)
df.set_index('time_dt', inplace=True)

cfg = SniperScalpConfig(
    symbol='GERMANY40', target_units=22.0, stop_units=35.0,
    session_start_h=7, session_end_h=17, min_rejection_wick=0.35,
    cooldown_bars=2, use_h1_filter=True, use_ker_filter=True, max_ker_trend=0.45,
    use_climax_filter=True, allow_short=True
)
sig_df = generate_sniper_signals(df, cfg)
ind = compute_sniper_indicators(df)

print('\nSignals and Indicators at 09:00 broker time (07:00 UTC / 08:00 CET):')
for idx in sig_df.index[-10:]:
    s = sig_df.loc[idx, 'signal']
    c = df.loc[idx, 'Close']
    o = df.loc[idx, 'Open']
    h = df.loc[idx, 'High']
    l = df.loc[idx, 'Low']
    lw = ind.loc[idx, 'lower_wick']
    clv = ind.loc[idx, 'clv']
    rsi2 = ind.loc[idx, 'rsi2']
    print(f"{idx} | Sig={s:2d} | O={o:.1f} H={h:.1f} L={l:.1f} C={c:.1f} | lower_wick={lw:.2f} | CLV={clv:.2f} | RSI2={rsi2:.1f}")
