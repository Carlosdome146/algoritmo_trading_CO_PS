import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from itertools import product
import sys

if not mt5.initialize():
    print("MT5 init failed")
    sys.exit(1)

def evaluate_sniper_grid(symbol, tf_code, tf_name, bars=40000):
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
    atr14 = pd.Series(tr).rolling(14, min_periods=5).mean().values
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
    
    rec_lo_6 = pd.Series(l).shift(1).rolling(6, min_periods=3).min().values
    rec_lo_10 = pd.Series(l).shift(1).rolling(10, min_periods=3).min().values
    
    hrs = df.index.hour.values
    dow = df.index.dayofweek.values
    
    # Let's test combinations
    param_grid = [
        # (tp_ratio, sl_ratio, be_ratio, min_w, max_ow, clv_th, s_start, s_end, lookback)
        (0.50, 1.20, 0.40, 0.40, 0.15, 0.65, 13, 20, 8),
        (0.60, 1.20, 0.45, 0.45, 0.12, 0.70, 13, 20, 8),
        (0.50, 1.00, 0.40, 0.45, 0.12, 0.70, 13, 20, 8),
        (0.65, 1.30, 0.45, 0.50, 0.10, 0.72, 13, 20, 6),
        (0.40, 1.00, 0.35, 0.45, 0.12, 0.70, 13, 20, 8),
        (0.55, 1.10, 0.40, 0.45, 0.12, 0.70, 13, 20, 8),
        # European session variants
        (0.50, 1.20, 0.40, 0.40, 0.15, 0.65, 7, 16, 8),
        (0.60, 1.20, 0.45, 0.45, 0.12, 0.70, 7, 16, 8),
        (0.40, 1.00, 0.35, 0.45, 0.12, 0.70, 7, 16, 8),
    ]
    
    results = []
    years = (df.index[-1] - df.index[210]).days / 365.25
    
    for (tp_m, sl_m, be_m, mw, mow, clv_t, ss, se, lb) in param_grid:
        rec_lo = rec_lo_6 if lb == 6 else rec_lo_10
        trades = []
        i = 210
        while i < n - 1:
            if dow[i] >= 5 or not (ss <= hrs[i] <= se):
                i += 1
                continue
            cur_atr = atr14[i]
            if not np.isfinite(cur_atr) or cur_atr <= 0:
                i += 1
                continue
            
            # Long condition
            bull = (c[i] > sma200[i]) and (ema20[i] > sma200[i])
            long_sig = (bull and 
                        (l[i] <= rec_lo[i]) and 
                        (c[i] > ema20[i]) and 
                        (lower_wick[i] >= mw) and 
                        (clv[i] >= clv_t) and 
                        (k_pos[i] <= 0.40) and 
                        (upper_wick[i] <= mow))
            
            if not long_sig:
                i += 1
                continue
                
            k = i + 1
            tp_dist = cur_atr * tp_m
            sl_dist = cur_atr * sl_m
            entry = o[k] + spread * 0.5
            tp_px = entry + tp_dist
            sl_px = entry - sl_dist
            be_trig = entry + (tp_dist * be_m)
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
            trades.append({'win': 1 if pnl > 0 else 0, 'r': pnl / sl_dist})
            i = j + 1
            
        if len(trades) >= 15:
            tdf = pd.DataFrame(trades)
            wr = tdf['win'].mean() * 100.0
            r_arr = tdf['r'].values
            w_sum = r_arr[r_arr > 0].sum()
            l_sum = np.abs(r_arr[r_arr < 0]).sum()
            pf = w_sum / (l_sum if l_sum > 0 else 1e-9)
            if wr >= 75.0 and pf >= 1.20:
                results.append({
                    'symbol': symbol, 'tf': tf_name, 'trades': len(trades),
                    'tr_yr': len(trades) / years, 'wr': wr, 'pf': pf,
                    'sum_r': r_arr.sum(), 'exp_r': np.mean(r_arr),
                    'tp_m': tp_m, 'sl_m': sl_m, 'be_m': be_m, 'ss': ss, 'se': se
                })
    return results

print("Scanning for top performers...")
all_res = []
for sym in ['GERMANY40', '[SP500]', 'US100', '[DJI30]', '[IBEX35]', 'GOLD', 'EURUSD']:
    for tf_c, tf_n in [(mt5.TIMEFRAME_M30, 'M30'), (mt5.TIMEFRAME_M15, 'M15')]:
        r = evaluate_sniper_grid(sym, tf_c, tf_n)
        all_res.extend(r)

if all_res:
    res_df = pd.DataFrame(all_res)
    res_df = res_df.sort_values(by=['pf', 'wr'], ascending=False)
    print(res_df.to_string(index=False))
else:
    print("No strategies met criteria WR >= 75% and PF >= 1.20 in this grid.")

mt5.shutdown()
