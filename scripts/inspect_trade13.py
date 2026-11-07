import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timezone

mt5.initialize()

# M30 bars
r_m30 = mt5.copy_rates_from_pos('GERMANY40', mt5.TIMEFRAME_M30, 0, 15)
df30 = pd.DataFrame(r_m30)
df30['time'] = pd.to_datetime(df30['time'], unit='s', utc=True)
print('--- M30 Candles around 07:00 UTC (08:00 CET) ---')
for _, row in df30.tail(8).iterrows():
    t = row['time'].strftime('%Y-%m-%d %H:%M')
    print(f"{t} | O={row['open']:.1f} H={row['high']:.1f} L={row['low']:.1f} C={row['close']:.1f}")

# M1 bars around 07:00 UTC
r_m1 = mt5.copy_rates_from_pos('GERMANY40', mt5.TIMEFRAME_M1, 0, 150)
df1 = pd.DataFrame(r_m1)
df1['time'] = pd.to_datetime(df1['time'], unit='s', utc=True)
df1_open = df1[(df1['time'] >= '2026-11-06 06:55:00') & (df1['time'] <= '2026-11-06 07:10:00')]
print('\n--- M1 Candles between 06:55 and 07:10 UTC (07:55 - 08:10 CET) ---')
for _, row in df1_open.iterrows():
    t = row['time'].strftime('%H:%M:%S')
    print(f"{t} | O={row['open']:.1f} H={row['high']:.1f} L={row['low']:.1f} C={row['close']:.1f}")
