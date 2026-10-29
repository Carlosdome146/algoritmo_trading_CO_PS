import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from trading_v2.research.regime_lab_v3 import metrics

mt5.initialize()

def optimize_sniper_ismael(symbol, tf_code, tf_name, bars=40000):
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
    
    rec_lo_6 = pd.Series(l).shift(1).rolling(6, min_periods=3).min().values
    rec_lo_8 = pd.Series(l).shift(1).rolling(8, min_periods=3).min().values
    rec_lo_12 = pd.Series(l).shift(1).rolling(12, min_periods=3).min().values
    
    hrs = df.index.hour.values
    dow = df.index.dayofweek.values
    years = (df.index[-1] - df.index[210]).days / 365.25
    
    # Grid of candidate parameters
    # Symbol specific price scales
    if symbol in ['[DJI30]', 'US30']:
        tgt_list = [35.0, 45.0, 55.0]
        sl_list = [70.0, 90.0, 110.0]
        ss, se = 13, 20
    elif symbol in ['GERMANY40', 'DE40']:
        tgt_list = [12.0, 15.0, 18.0]
        sl_list = [22.0, 28.0, 35.0]
        ss, se = 7, 16
    elif symbol in ['GOLD', 'XAUUSD']:
        tgt_list = [4.0, 5.0, 6.0]
        sl_list = [8.0, 10.0, 12.0]
        ss, se = 12, 19
    elif symbol in ['US100', 'USTEC']:
        tgt_list = [25.0, 35.0, 45.0]
        sl_list = [50.0, 70.0, 90.0]
        ss, se = 13, 20
    elif symbol in ['[SP500]', 'US500']:
        tgt_list = [4.0, 5.5, 7.0]
        sl_list = [7.5, 10.0, 13.0]
        ss, se = 13, 20
    elif symbol == 'EURUSD':
        tgt_list = [0.00030, 0.00045]
        sl_list = [0.00050, 0.00075]
        ss, se = 7, 16
    else:
        return []
        
    be_ratios = [0.40, 0.45]
    wick_thresholds = [(0.45, 0.12, 0.70), (0.50, 0.10, 0.75)]
    
    grid_results = []
    
    for tgt_pts in tgt_list:
        for sl_pts in sl_list:
            for be_r in be_ratios:
                for (mw, mow, clv_t) in wick_thresholds:
                    trades = []
                    i = 210
                    while i < n - 1:
                        if dow[i] >= 5 or not (ss <= hrs[i] <= se):
                            i += 1
                            continue
                        
                        bull = (c[i] > sma200[i]) and (ema20[i] > sma200[i])
                        if not bull:
                            i += 1
                            continue
                            
                        # High-conviction Ismael Reclaim
                        sig = ((l[i] <= rec_lo_8[i]) and 
                               (c[i] > ema20[i]) and 
                               (lower_wick[i] >= mw) and 
                               (clv[i] >= clv_t) and 
                               (upper_wick[i] <= mow) and 
                               (k_pos[i] <= 0.40))
                        
                        if not sig:
                            i += 1
                            continue
                            
                        k = i + 1
                        entry = o[k] + spread * 0.5
                        tp_px = entry + tgt_pts
                        sl_px = entry - sl_pts
                        be_trig = entry + (tgt_pts * be_r)
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
                        
                    if len(trades) >= 12:
                        tdf = pd.DataFrame(trades)
                        wr = tdf['win'].mean() * 100.0
                        r_arr = tdf['r'].values
                        met = metrics(r_arr)
                        pf = met['profit_factor']
                        if wr >= 75.0 and pf >= 1.20:
                            grid_results.append({
                                'symbol': symbol,
                                'tf': tf_name,
                                'trades': len(trades),
                                'tr_yr': round(len(trades) / years, 1),
                                'wr': round(wr, 2),
                                'pf': round(pf, 2),
                                'sum_r': round(float(r_arr.sum()), 2),
                                'exp_r': round(float(r_arr.mean()), 3),
                                'tgt': tgt_pts,
                                'sl': sl_pts,
                                'be_r': be_r,
                                'mw': mw,
                                'mow': mow,
                                'clv': clv_t
                            })
    return grid_results

print("Optimizing high-precision sniper across key assets...")
all_best = []
for sym in ['[DJI30]', 'GOLD', 'GERMANY40', 'US100', '[SP500]']:
    for tf_c, tf_n in [(mt5.TIMEFRAME_M30, 'M30'), (mt5.TIMEFRAME_M15, 'M15')]:
        res = optimize_sniper_ismael(sym, tf_c, tf_n)
        all_best.extend(res)

bdf = pd.DataFrame(all_best)
if not bdf.empty:
    bdf = bdf.sort_values(by=['symbol', 'pf'], ascending=[True, False])
    # Pick top 2 for each symbol
    top = bdf.groupby(['symbol', 'tf']).first().reset_index()
    print(top[['symbol', 'tf', 'trades', 'tr_yr', 'wr', 'pf', 'sum_r', 'tgt', 'sl', 'be_r']].to_string(index=False))
else:
    print("No configurations met the strict filter.")
mt5.shutdown()
