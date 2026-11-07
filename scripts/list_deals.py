import MetaTrader5 as mt5
from datetime import datetime, timezone

mt5.initialize()
deals = mt5.history_deals_get(datetime(2026, 11, 1, tzinfo=timezone.utc), datetime(2026, 11, 7, tzinfo=timezone.utc))
for d in deals:
    t = datetime.fromtimestamp(d.time, tz=timezone.utc)
    print(f"{t} | ticket={d.ticket} order={d.order} sym={d.symbol} type={d.type} vol={d.volume} px={d.price} pnl={d.profit} comm={d.comment}")
