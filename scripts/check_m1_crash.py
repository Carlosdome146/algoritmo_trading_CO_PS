import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timezone

mt5.initialize()

d_from = datetime(2026, 11, 6, 6, 58, tzinfo=timezone.utc)
d_to = datetime(2026, 11, 6, 7, 10, tzinfo=timezone.utc)
r = mt5.copy_rates_range('GERMANY40', mt5.TIMEFRAME_M1, d_from, d_to)
df = pd.DataFrame(r)
df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
for _, row in df.iterrows():
    t_cet = row['time'] + pd.Timedelta(hours=1)
    print(f"{t_cet.strftime('%H:%M:%S')} CET | O={row['open']:.1f} H={row['high']:.1f} L={row['low']:.1f} C={row['close']:.1f} Vol={row['tick_volume']}")
