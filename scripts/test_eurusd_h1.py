import MetaTrader5 as mt5
import pandas as pd
import numpy as np

mt5.initialize()
r = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_H1, 0, 30000)
df = pd.DataFrame(r)
df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
df.set_index("time", inplace=True)
df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close"}, inplace=True)

# Indicadores H1: Bollinger 2.5 sigma, RSI(2), KER10
c = df["Close"]
sma20 = c.rolling(20).mean()
std20 = c.rolling(20).std()
bb_hi = sma20 + 2.5 * std20
bb_lo = sma20 - 2.5 * std20

delta = c.diff()
up = delta.clip(lower=0)
down = -delta.clip(upper=0)
rs = up.rolling(2).mean() / down.rolling(2).mean().replace(0, np.nan)
rsi2 = 100 - (100 / (1 + rs))

direction = (c - c.shift(10)).abs()
volatility = c.diff().abs().rolling(10).sum()
ker10 = direction / volatility.replace(0, np.nan)

# Señales H1 Mean Reversion: Comprar si c < bb_lo y rsi2 < 10 y ker10 < 0.40; Vender si c > bb_hi y rsi2 > 90 y ker10 < 0.40
signals = np.zeros(len(df))
for i in range(len(df)):
    if c.iloc[i] < bb_lo.iloc[i] and rsi2.iloc[i] < 10.0 and ker10.iloc[i] < 0.40:
        signals[i] = 1
    elif c.iloc[i] > bb_hi.iloc[i] and rsi2.iloc[i] > 90.0 and ker10.iloc[i] < 0.40:
        signals[i] = -1

# Simular trades: TP = 40 pips (0.0040), SL = 35 pips (0.0035), Spread = 0.8 pips
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
        entry_px = opens[i+1] + (0.00008 if sig == 1 else 0)
        tp_px = entry_px + 0.0040 if sig == 1 else entry_px - 0.0040
        sl_px = entry_px - 0.0035 if sig == 1 else entry_px + 0.0035
        exit_px = None
        for j in range(i+1, min(i+1+24, n)):
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
                if highs[j] >= sl_px and lows[j] <= tp_px:
                    exit_px = tp_px if closes[j] < opens[j] else sl_px
                    break
                elif lows[j] <= tp_px:
                    exit_px = tp_px
                    break
                elif highs[j] >= sl_px:
                    exit_px = sl_px
                    break
        if exit_px is None:
            exit_px = closes[min(i+24, n-1)]
        gain = (exit_px - entry_px) if sig == 1 else (entry_px - exit_px)
        pnl = (gain / 0.0035) * 30.58
        trades.append(pnl)
        i = j + 2
    else:
        i += 1

s = pd.Series(trades)
wins = s[s > 0]
losses = s[s < 0]
print(f"EURUSD H1 Mean Reversion: Trades={len(s)}, WR={len(wins)/len(s)*100:.1f}%, PF={wins.sum()/abs(losses.sum()):.2f}, PnL={s.sum():+.2f} EUR, DD={(s.cumsum().cummax() - s.cumsum()).max():.2f} EUR")
