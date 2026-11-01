import MetaTrader5 as mt5
import pandas as pd
from trading_v2.strategies.micro_scalping import compute_sniper_indicators

mt5.initialize()
for s in ["[DJI30]", "GOLD", "[SP500]"]:
    rates = mt5.copy_rates_from_pos(s, mt5.TIMEFRAME_M15, 0, 150)
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "tick_volume": "Volume"}, inplace=True)
    ind = compute_sniper_indicators(df)
    last_bars = ind.tail(8)
    print(f"=== {s} Últimas 8 barras M15 (UTC) ===")
    for t, r in last_bars.iterrows():
        c = r["Close"]
        s200 = r["sma200"]
        e20 = r["ema20"]
        lw = r["lower_wick"]
        clv = r["clv"]
        time_str = t.strftime("%H:%M")
        c_gt_sma = c > s200 if pd.notna(s200) else False
        print(f"{time_str} | C: {c:8.2f} | EMA20: {e20:8.2f} | SMA200: {s200:8.2f} | C>SMA: {c_gt_sma} | LW: {lw:.2f} | CLV: {clv:.2f}")

mt5.shutdown()
