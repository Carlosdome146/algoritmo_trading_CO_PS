import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from trading_v2.research.regime_lab_v3 import metrics

mt5.initialize()

def test_isolated_triggers(symbol, tf_code, tgt_pts, sl_pts, s_start, s_end, bars=40000):
    rates = mt5.copy_rates_from_pos(symbol, tf_code, 0, bars)
    if rates is None or len(rates) < 1000:
        return []
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
    df.set_index('time', inplace=True)
    spec = mt5.symbol_info(symbol)
    spread = spec.spread * spec.point
    
    c = df['close'].values.astype(float)
    h = df['high'].values.astype(float)
    l = df['low'].values.astype(float)
    o = df['open'].values.astype(float)
    n = len(df)
    
    prev_c = pd.Series(c).shift(1).fillna(c[0]).values
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    atr10 = pd.Series(tr).rolling(10, min_periods=3).mean().values
    
    sma200 = pd.Series(c).rolling(200, min_periods=50).mean().values
    ema20 = pd.Series(c).ewm(span=20, adjust=False).mean().values
    
    k_ub = ema20 + 1.5 * atr10
    k_lb = ema20 - 1.5 * atr10
    k_rng = np.maximum(k_ub - k_lb, 1e-9)
    k_pos = (l - k_lb) / k_rng
    
    rng = np.maximum(h - l, 1e-9)
    lower_wick = (np.minimum(o, c) - l) / rng
    upper_wick = (h - np.maximum(o, c)) / rng
    clv = (c - l) / rng
    
    delta = pd.Series(c).diff().values
    up = pd.Series(np.clip(delta, 0, None)).ewm(alpha=0.5, adjust=False).mean().values
    dn = pd.Series(-np.clip(delta, None, 0)).ewm(alpha=0.5, adjust=False).mean().values
    rsi2 = 100.0 - 100.0 / (1.0 + up / np.maximum(dn, 1e-9))
    
    rec_lo_8 = pd.Series(l).shift(1).rolling(8, min_periods=3).min().values
    rec_lo_16 = pd.Series(l).shift(1).rolling(16, min_periods=4).min().values
    
    hrs = df.index.hour.values
    dow = df.index.dayofweek.values
    years = (df.index[-1] - df.index[210]).days / 365.25
    
    results = []
    
    # We define 4 trigger styles:
    # 1: Pure Ismael Reclaim (Bullish, sweep 8 bars, Close > EMA20, lower_wick >= 0.45, CLV >= 0.70, opp_wick <= 0.12)
    # 2: Spagnola M4 Session Fade (Bullish, sweep 16 bars, Close > Open, lower_wick >= 0.35, CLV >= 0.65)
    # 3: Yeboster Keltner Reclaim (Bullish, k_pos <= 0.35, Close > Open, lower_wick >= 0.30, CLV >= 0.65, RSI2 < 35)
    # 4: Bollinger Extreme Rebound (Bullish, l <= k_lb, RSI2 < 10, lower_wick >= 0.40)
    
    trigger_names = [
        "1_Ismael_Reclaim",
        "2_Spagnola_M4_Fade",
        "3_Yeboster_Keltner",
        "4_Bollinger_Extreme"
    ]
    
    for t_idx, t_name in enumerate(trigger_names, start=1):
        trades = []
        i = 210
        while i < n - 1:
            if dow[i] >= 5 or not (s_start <= hrs[i] <= s_end):
                i += 1
                continue
            
            bull = (c[i] > sma200[i]) and (ema20[i] > sma200[i])
            if not bull:
                i += 1
                continue
                
            sig = False
            if t_idx == 1:
                sig = (l[i] <= rec_lo_8[i]) and (c[i] > ema20[i]) and (lower_wick[i] >= 0.45) and (clv[i] >= 0.70) and (upper_wick[i] <= 0.12) and (k_pos[i] <= 0.40)
            elif t_idx == 2:
                sig = (l[i] <= rec_lo_16[i]) and (c[i] > rec_lo_16[i]) and (c[i] > o[i]) and (lower_wick[i] >= 0.35) and (clv[i] >= 0.65) and (k_pos[i] <= 0.40)
            elif t_idx == 3:
                sig = (k_pos[i] <= 0.35) and (c[i] > o[i]) and (lower_wick[i] >= 0.30) and (clv[i] >= 0.65) and (rsi2[i] < 35.0)
            elif t_idx == 4:
                sig = (k_pos[i] <= 0.10) and (rsi2[i] < 10.0) and (c[i] > o[i] or lower_wick[i] >= 0.40)
                
            if not sig:
                i += 1
                continue
                
            k = i + 1
            entry = o[k] + spread * 0.5
            tp_px = entry + tgt_pts
            sl_px = entry - sl_pts
            be_trig = entry + (tgt_pts * 0.45)
            be_lock = entry + (spread * 1.5)
            cur_sl = sl_px
            exit_px = None
            
            for j in range(k, min(n, k + 8)):
                bar_l = l[j]; bar_h = h[j]
                if bar_l <= cur_sl and bar_h >= tp_px:
                    exit_px = cur_sl; break
                elif bar_l <= cur_sl:
                    exit_px = cur_sl; break
                elif bar_h >= tp_px:
                    exit_px = tp_px; break
                if c[j] >= be_trig and cur_sl < be_lock:
                    cur_sl = be_lock
                    
            if exit_px is None:
                j = min(n - 1, k + 7)
                exit_px = c[j] - spread * 0.5
                
            pnl = (exit_px - entry) - spread * 0.5
            trades.append({'win': 1 if pnl > 0 else 0, 'r': pnl / sl_pts})
            i = j + 1
            
        if len(trades) >= 10:
            tdf = pd.DataFrame(trades)
            wr = tdf['win'].mean() * 100.0
            r_arr = tdf['r'].values
            met = metrics(r_arr)
            results.append({
                'symbol': symbol,
                'trigger': t_name,
                'trades': len(trades),
                'tr_yr': len(trades) / years,
                'wr': wr,
                'pf': met['profit_factor'],
                'sum_r': r_arr.sum(),
                'tgt': tgt_pts,
                'sl': sl_pts
            })
    return results

print("Testing triggers across key assets...")
all_trig = []
assets = [
    ('GERMANY40', mt5.TIMEFRAME_M30, 15.0, 30.0, 7, 16),
    ('GERMANY40', mt5.TIMEFRAME_M15, 12.0, 25.0, 7, 16),
    ('[SP500]', mt5.TIMEFRAME_M30, 5.0, 10.0, 13, 20),
    ('[SP500]', mt5.TIMEFRAME_M15, 4.0, 7.5, 13, 20),
    ('[IBEX35]', mt5.TIMEFRAME_M30, 18.0, 35.0, 7, 16),
    ('[IBEX35]', mt5.TIMEFRAME_M15, 15.0, 25.0, 7, 11),
    ('US100', mt5.TIMEFRAME_M30, 30.0, 60.0, 13, 20),
    ('US100', mt5.TIMEFRAME_M15, 20.0, 45.0, 13, 20),
    ('[DJI30]', mt5.TIMEFRAME_M30, 40.0, 80.0, 13, 20),
    ('[DJI30]', mt5.TIMEFRAME_M15, 30.0, 65.0, 13, 20),
    ('GOLD', mt5.TIMEFRAME_M30, 5.0, 10.0, 12, 19),
]

for sym, tf_c, tgt, sl, ss, se in assets:
    tf_str = 'M30' if tf_c == mt5.TIMEFRAME_M30 else 'M15'
    r_list = test_isolated_triggers(sym, tf_c, tgt, sl, ss, se)
    for r in r_list:
        r['tf'] = tf_str
        all_trig.append(r)

tdf = pd.DataFrame(all_trig)
print(tdf[['symbol', 'tf', 'trigger', 'trades', 'tr_yr', 'wr', 'pf', 'sum_r']].to_string(index=False))
mt5.shutdown()
