import MetaTrader5 as mt5
import numpy as np
import pandas as pd
import sys

if not mt5.initialize():
    print("Failed to initialize MT5")
    sys.exit(1)

def run_simulation(symbol, tf_code, tf_name, bars=40000,
                   s_start=13, s_end=20,
                   sma_period=200, ema_period=20,
                   keltner_mult=1.5,
                   min_wick=0.45, max_opp_wick=0.12, clv_th=0.70,
                   tp_atr_mult=0.70, sl_atr_mult=1.40,
                   be_trigger_ratio=0.45,
                   allow_short=False,
                   lookback_sweep=8):
    rates = mt5.copy_rates_from_pos(symbol, tf_code, 0, bars)
    if rates is None or len(rates) < 600:
        return None
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
    df.set_index('time', inplace=True)
    
    spec = mt5.symbol_info(symbol)
    if spec is None:
        return None
    spread_pts = spec.spread * spec.point
    
    c = df['close'].values.astype(float)
    h = df['high'].values.astype(float)
    l = df['low'].values.astype(float)
    o = df['open'].values.astype(float)
    n = len(df)
    
    prev_c = pd.Series(c).shift(1).fillna(c[0]).values
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    atr14 = pd.Series(tr).rolling(14, min_periods=5).mean().values
    atr10 = pd.Series(tr).rolling(10, min_periods=3).mean().values
    
    sma = pd.Series(c).rolling(sma_period, min_periods=50).mean().values
    ema = pd.Series(c).ewm(span=ema_period, adjust=False).mean().values
    
    k_ub = ema + keltner_mult * atr10
    k_lb = ema - keltner_mult * atr10
    k_rng = np.maximum(k_ub - k_lb, 1e-9)
    k_pos = (l - k_lb) / k_rng
    
    rng = np.maximum(h - l, 1e-9)
    lower_wick = (np.minimum(o, c) - l) / rng
    upper_wick = (h - np.maximum(o, c)) / rng
    clv = (c - l) / rng
    
    rec_lo = pd.Series(l).shift(1).rolling(lookback_sweep, min_periods=3).min().values
    rec_hi = pd.Series(h).shift(1).rolling(lookback_sweep, min_periods=3).max().values
    
    hrs = df.index.hour.values
    dow = df.index.dayofweek.values
    
    trades = []
    i = max(sma_period + 10, 210)
    
    while i < n - 1:
        if dow[i] >= 5 or not (s_start <= hrs[i] <= s_end):
            i += 1
            continue
        
        cur_atr = atr14[i]
        if not np.isfinite(cur_atr) or cur_atr <= 0:
            i += 1
            continue
        
        # Long condition
        bull_struct = (c[i] > sma[i]) and (ema[i] > sma[i])
        long_sig = (bull_struct and 
                    (l[i] <= rec_lo[i]) and 
                    (c[i] > ema[i]) and 
                    (lower_wick[i] >= min_wick) and 
                    (clv[i] >= clv_th) and 
                    (k_pos[i] <= 0.40) and 
                    (upper_wick[i] <= max_opp_wick))
        
        # Short condition (if allowed)
        short_sig = False
        if allow_short:
            bear_struct = (c[i] < sma[i]) and (ema[i] < sma[i])
            short_sig = (bear_struct and 
                         (h[i] >= rec_hi[i]) and 
                         (c[i] < ema[i]) and 
                         (upper_wick[i] >= min_wick) and 
                         (clv[i] <= (1.0 - clv_th)) and 
                         (k_pos[i] >= 0.60) and 
                         (lower_wick[i] <= max_opp_wick))
        
        if not (long_sig or short_sig):
            i += 1
            continue
        
        side = 'BUY' if long_sig else 'SELL'
        k = i + 1
        
        # Target and Stop Loss in price units
        tp_dist = cur_atr * tp_atr_mult
        sl_dist = cur_atr * sl_atr_mult
        
        if side == 'BUY':
            entry = o[k] + spread_pts * 0.5
            tp_px = entry + tp_dist
            sl_px = entry - sl_dist
            be_trig = entry + (tp_dist * be_trigger_ratio)
            be_lock = entry + (spread_pts * 1.5)
            cur_sl = sl_px
            exit_px = None
            
            for j in range(k, min(n, k + 10)):
                bar_l = l[j]
                bar_h = h[j]
                
                # Check adverse stop first
                if bar_l <= cur_sl and bar_h >= tp_px:
                    exit_px = cur_sl
                    break
                elif bar_l <= cur_sl:
                    exit_px = cur_sl
                    break
                elif bar_h >= tp_px:
                    exit_px = tp_px
                    break
                
                # Check causal breakeven
                if c[j] >= be_trig and cur_sl < be_lock:
                    cur_sl = be_lock
            
            if exit_px is None:
                j = min(n - 1, k + 9)
                exit_px = c[j] - spread_pts * 0.5
                
            pnl_pts = (exit_px - entry) - spread_pts * 0.5
            r_val = pnl_pts / sl_dist
            trades.append({
                'time': df.index[k],
                'side': side,
                'win': 1 if pnl_pts > 0 else 0,
                'pnl_pts': pnl_pts,
                'r': r_val
            })
            i = j + 1
            
        else: # SELL
            entry = o[k] - spread_pts * 0.5
            tp_px = entry - tp_dist
            sl_px = entry + sl_dist
            be_trig = entry - (tp_dist * be_trigger_ratio)
            be_lock = entry - (spread_pts * 1.5)
            cur_sl = sl_px
            exit_px = None
            
            for j in range(k, min(n, k + 10)):
                bar_l = l[j]
                bar_h = h[j]
                
                if bar_h >= cur_sl and bar_l <= tp_px:
                    exit_px = cur_sl
                    break
                elif bar_h >= cur_sl:
                    exit_px = cur_sl
                    break
                elif bar_l <= tp_px:
                    exit_px = tp_px
                    break
                    
                if c[j] <= be_trig and cur_sl > be_lock:
                    cur_sl = be_lock
                    
            if exit_px is None:
                j = min(n - 1, k + 9)
                exit_px = c[j] + spread_pts * 0.5
                
            pnl_pts = (entry - exit_px) - spread_pts * 0.5
            r_val = pnl_pts / sl_dist
            trades.append({
                'time': df.index[k],
                'side': side,
                'win': 1 if pnl_pts > 0 else 0,
                'pnl_pts': pnl_pts,
                'r': r_val
            })
            i = j + 1

    if not trades:
        return None
        
    tdf = pd.DataFrame(trades)
    n_t = len(tdf)
    wr = tdf['win'].mean() * 100.0
    r_arr = tdf['r'].values
    wins = r_arr[r_arr > 0]
    losses = np.abs(r_arr[r_arr < 0])
    sum_w = wins.sum() if len(wins) > 0 else 0.0
    sum_l = losses.sum() if len(losses) > 0 else 1e-9
    pf = sum_w / sum_l
    
    start_dt = df.index[max(sma_period + 10, 210)]
    end_dt = df.index[-1]
    years = max(0.1, (end_dt - start_dt).days / 365.25)
    tr_yr = n_t / years
    
    # Cumulative R and Max Drawdown in R
    cum_r = np.cumsum(r_arr)
    peak = np.maximum.accumulate(cum_r)
    dd = peak - cum_r
    max_dd_r = np.max(dd) if len(dd) > 0 else 0.0
    
    return {
        'symbol': symbol,
        'tf': tf_name,
        'trades': n_t,
        'years': round(years, 2),
        'tr_yr': round(tr_yr, 1),
        'wr': round(wr, 2),
        'pf': round(pf, 2),
        'sum_r': round(float(cum_r[-1]), 2),
        'exp_r': round(float(np.mean(r_arr)), 3),
        'max_dd_r': round(float(max_dd_r), 2)
    }

print("Running deep multi-asset scan...")
symbols_config = [
    # symbol, tf_code, tf_name, s_start, s_end, min_wick, opp_wick, clv, tp_mult, sl_mult, allow_short
    ('GERMANY40', mt5.TIMEFRAME_M30, 'M30', 7, 16, 0.45, 0.12, 0.70, 0.65, 1.30, False),
    ('GERMANY40', mt5.TIMEFRAME_M15, 'M15', 7, 16, 0.45, 0.12, 0.70, 0.60, 1.25, False),
    ('[SP500]', mt5.TIMEFRAME_M30, 'M30', 13, 20, 0.45, 0.12, 0.70, 0.65, 1.30, False),
    ('[SP500]', mt5.TIMEFRAME_M15, 'M15', 13, 20, 0.45, 0.12, 0.70, 0.60, 1.25, False),
    ('[IBEX35]', mt5.TIMEFRAME_M30, 'M30', 7, 16, 0.45, 0.12, 0.70, 0.65, 1.30, False),
    ('[IBEX35]', mt5.TIMEFRAME_M15, 'M15', 7, 16, 0.45, 0.12, 0.70, 0.60, 1.25, False),
    ('US100', mt5.TIMEFRAME_M30, 'M30', 13, 20, 0.45, 0.12, 0.70, 0.65, 1.30, False),
    ('US100', mt5.TIMEFRAME_M15, 'M15', 13, 20, 0.45, 0.12, 0.70, 0.60, 1.25, False),
    ('[DJI30]', mt5.TIMEFRAME_M30, 'M30', 13, 20, 0.45, 0.12, 0.70, 0.65, 1.30, False),
    ('[DJI30]', mt5.TIMEFRAME_M15, 'M15', 13, 20, 0.45, 0.12, 0.70, 0.60, 1.25, False),
    ('EURUSD', mt5.TIMEFRAME_M30, 'M30', 7, 17, 0.45, 0.12, 0.70, 0.60, 1.20, True),
    ('EURUSD', mt5.TIMEFRAME_M15, 'M15', 7, 17, 0.45, 0.12, 0.70, 0.55, 1.20, True),
    ('GOLD', mt5.TIMEFRAME_M30, 'M30', 12, 20, 0.45, 0.12, 0.70, 0.65, 1.30, False),
    ('GOLD', mt5.TIMEFRAME_M15, 'M15', 12, 20, 0.45, 0.12, 0.70, 0.60, 1.25, False),
    ('[FTSE100]', mt5.TIMEFRAME_M30, 'M30', 8, 16, 0.45, 0.12, 0.70, 0.65, 1.30, False),
    ('GBPUSD', mt5.TIMEFRAME_M30, 'M30', 7, 17, 0.45, 0.12, 0.70, 0.60, 1.20, True),
]

results = []
for sym, tf_c, tf_n, ss, se, mw, mow, clv, tp_m, sl_m, ash in symbols_config:
    res = run_simulation(sym, tf_c, tf_n, s_start=ss, s_end=se, min_wick=mw, max_opp_wick=mow,
                         clv_th=clv, tp_atr_mult=tp_m, sl_atr_mult=sl_m, allow_short=ash)
    if res:
        results.append(res)

rdf = pd.DataFrame(results)
print(rdf.to_string(index=False))
mt5.shutdown()
