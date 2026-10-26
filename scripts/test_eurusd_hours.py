import MetaTrader5 as mt5
import pandas as pd
import numpy as np

def main():
    if not mt5.initialize():
        return
    r = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_M15, 0, 35000)
    df = pd.DataFrame(r)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    c, h, l, o = df["close"].values, df["high"].values, df["low"].values, df["open"].values
    n = len(df)
    tr = np.maximum(h - l, np.abs(h - pd.Series(c).shift(1).fillna(c[0]).values))
    atr = pd.Series(tr).rolling(14, min_periods=5).mean().values
    sma200 = pd.Series(c).rolling(200, min_periods=50).mean().values
    ema20 = pd.Series(c).ewm(span=20, adjust=False).mean().values
    rng = np.maximum(h - l, 1e-9)
    lower_wick = (np.minimum(o, c) - l) / rng
    clv = (c - l) / rng
    recent_lo = pd.Series(l).shift(1).rolling(8, min_periods=3).min().values
    hrs = df.index.hour.values
    spr_cost = 0.00006

    for end_hr in [14, 15, 16]:
        wins, losses = 0, 0
        trades = []
        i = 210
        while i < n - 1:
            if not (7 <= hrs[i] <= end_hr):
                i += 1
                continue
            cur_atr = atr[i]
            trig = (
                (l[i] <= recent_lo[i])
                and (c[i] > sma200[i])
                and (ema20[i] > sma200[i])
                and (c[i] > ema20[i])
                and (lower_wick[i] >= 0.55)
                and (clv[i] >= 0.85)
            )
            if not trig:
                i += 1
                continue
            k = i + 1
            entry = o[k] + spr_cost * 0.5
            tp_px = entry + 0.65 * cur_atr
            cur_sl = entry - 2.5 * cur_atr
            be_trig = entry + 0.30 * cur_atr
            be_lock = entry + 0.05 * cur_atr
            exit_px = None
            for j in range(k, min(n, k + 8)):
                if l[j] <= cur_sl:
                    exit_px = cur_sl - spr_cost * 0.5
                    break
                if h[j] >= tp_px:
                    exit_px = tp_px
                    break
                if c[j] >= be_trig and cur_sl < be_lock:
                    cur_sl = be_lock
            if exit_px is None:
                j = min(n - 1, k + 7)
                exit_px = c[j] - spr_cost * 0.5
            win = exit_px > entry
            if win: wins += 1
            else: losses += 1
            trades.append(win)
            i = j + 1
        print(f"Hours 07:00 - {end_hr:02d}:00 UTC -> Trades: {len(trades)} | Wins: {wins} | Losses: {losses} | WinRate: {wins/len(trades)*100:.2f}%")
    mt5.shutdown()

if __name__ == "__main__":
    main()
