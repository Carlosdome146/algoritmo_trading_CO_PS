import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timezone

mt5.initialize()

# Ticks around order execution
# Order ticket: 1235038350
d_from = datetime(2026, 11, 6, 8, 59, 50)
d_to = datetime(2026, 11, 6, 9, 2, 0)
ticks = mt5.copy_ticks_range('GERMANY40', d_from, d_to, mt5.COPY_TICKS_ALL)
df_t = pd.DataFrame(ticks)
if not df_t.empty:
    df_t['time_dt'] = pd.to_datetime(df_t['time_msc'], unit='ms')
    print(f'Total ticks: {len(df_t)}')
    print('First 10 ticks:')
    for _, r in df_t.head(10).iterrows():
        print(f"{r['time_dt']} | Bid={r['bid']} Ask={r['ask']} Flags={r['flags']}")
    print('\nTicks around Low (Min Bid):')
    min_bid_idx = df_t['bid'].idxmin()
    subset = df_t.loc[max(0, min_bid_idx-5):min(len(df_t)-1, min_bid_idx+5)]
    for _, r in subset.iterrows():
        print(f"{r['time_dt']} | Bid={r['bid']} Ask={r['ask']}")
else:
    print('No ticks found with broker time. Trying UTC...')
