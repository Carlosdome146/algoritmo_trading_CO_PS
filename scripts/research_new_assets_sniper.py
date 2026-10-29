import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from trading_v2.research.regime_lab_v3 import metrics

mt5.initialize()

def backtest_sniper_asset(symbol, tf_mt5, tf_name, cfg):
    rates = mt5.copy_rates_from_pos(symbol, tf_mt5, 0, 40000)
    if rates is None or len(rates) < 500:
        return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
    df.set_index('time', inplace=True)

    c = df['close'].values.astype(float)
    h = df['high'].values.astype(float)
    l = df['low'].values.astype(float)
    o = df['open'].values.astype(float)
    n = len(df)

    spec = mt5.symbol_info(symbol)
    if not spec:
        return None
    point = spec.point
    ref_px = c[-1]
    spr_cost = spec.spread * point

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
    k_pos_hi = (h - k_lb) / k_rng

    rng = np.maximum(h - l, 1e-9)
    lower_wick = (np.minimum(o, c) - l) / rng
    upper_wick = (h - np.maximum(o, c)) / rng
    clv = (c - l) / rng

    rec_lo_8 = pd.Series(l).shift(1).rolling(8, min_periods=3).min().values
    rec_hi_8 = pd.Series(h).shift(1).rolling(8, min_periods=3).max().values
    rec_lo_16 = pd.Series(l).shift(1).rolling(16, min_periods=5).min().values
    rec_hi_16 = pd.Series(h).shift(1).rolling(16, min_periods=5).max().values

    hrs = df.index.hour.values
    dow = df.index.dayofweek.values

    trades = []
    i = 210
    while i < n - 1:
        if dow[i] >= 5 or not (cfg['s_start'] <= hrs[i] <= cfg['s_end']):
            i += 1
            continue
        cur_atr = atr14[i]
        if not np.isfinite(cur_atr) or cur_atr <= 0:
            i += 1
            continue

        tgt_dist = cfg['tp_mult'] * cur_atr
        sl_dist = cfg['sl_mult'] * cur_atr

        bull_struct = (c[i] > sma200[i]) and (ema20[i] > sma200[i])

        # Trigger 1: Ismael Reclaim (8-bar sweep + Reclaim Close > EMA20)
        t1_long = bull_struct and (l[i] <= rec_lo_8[i]) and (c[i] > ema20[i]) and (lower_wick[i] >= cfg['min_wick']) and (clv[i] >= cfg['clv_th'])
        # Trigger 2: Spagnola M4 Session Fade (16-bar extreme sweep + close green inside)
        t2_long = bull_struct and (l[i] <= rec_lo_16[i]) and (c[i] > rec_lo_16[i]) and (c[i] > o[i]) and (lower_wick[i] >= 0.35) and (clv[i] >= 0.65)
        # Trigger 3: Yeboster Keltner Reclaim (touch Keltner low but closes green)
        t3_long = bull_struct and (k_pos[i] <= 0.35) and (c[i] > o[i]) and (lower_wick[i] >= 0.30) and (clv[i] >= 0.65)

        long_sig = (t1_long or t2_long or t3_long)
        short_sig = False

        if cfg.get('allow_short', False):
            bear_struct = (c[i] < sma200[i]) and (ema20[i] < sma200[i])
            t1_short = bear_struct and (h[i] >= rec_hi_8[i]) and (c[i] < ema20[i]) and (upper_wick[i] >= cfg['min_wick']) and (clv[i] <= (1.0 - cfg['clv_th']))
            t2_short = bear_struct and (h[i] >= rec_hi_16[i]) and (c[i] < rec_hi_16[i]) and (c[i] < o[i]) and (upper_wick[i] >= 0.35) and (clv[i] <= 0.35)
            short_sig = (t1_short or t2_short)

        if cfg.get('max_opp_wick') is not None:
            long_sig = long_sig and (upper_wick[i] <= cfg['max_opp_wick'])
            short_sig = short_sig and (lower_wick[i] <= cfg['max_opp_wick'])

        side = 1 if long_sig else (-1 if short_sig else 0)
        if side == 0:
            i += 1
            continue

        k = i + 1
        entry = o[k] + side * spr_cost * 0.5
        tp_px = entry + side * tgt_dist
        sl_px = entry - side * sl_dist

        be_trig = entry + side * (tgt_dist * 0.45)
        be_lock = entry + side * (spr_cost * 1.5)
        cur_sl = sl_px
        exit_px = None

        for j in range(k, min(n, k + cfg['holding_bars'])):
            eval_lo = l[j]; eval_hi = h[j]
            hit_sl = (eval_lo <= cur_sl) if side == 1 else (eval_hi >= cur_sl)
            hit_tp = (eval_hi >= tp_px) if side == 1 else (eval_lo <= tp_px)
            if hit_sl and hit_tp:
                exit_px = cur_sl; break
            elif hit_sl:
                exit_px = cur_sl; break
            elif hit_tp:
                exit_px = tp_px; break
            if (side == 1 and c[j] >= be_trig) or (side == -1 and c[j] <= be_trig):
                if (side == 1 and cur_sl < be_lock) or (side == -1 and cur_sl > be_lock):
                    cur_sl = be_lock

        if exit_px is None:
            j = min(n - 1, k + cfg['holding_bars'] - 1)
            exit_px = c[j] - side * spr_cost * 0.5

        pnl = side * (exit_px - entry) - spr_cost * 0.5
        r_val = pnl / sl_dist
        trades.append({
            'symbol': symbol, 'tf': tf_name, 'time': df.index[k],
            'win': 1 if pnl > 0 else 0, 'r': r_val
        })
        i = j + 1

    if not trades:
        return None
    tdf = pd.DataFrame(trades)
    n_t = len(tdf)
    wr = tdf['win'].mean() * 100.0
    r_arr = tdf['r'].values
    m = metrics(r_arr)
    pf = m['profit_factor']
    sum_r = float(r_arr.sum())
    years = (df.index[-1] - df.index[210]).days / 365.25
    trades_per_year = n_t / years if years > 0 else 0

    return {
        'symbol': symbol,
        'tf': tf_name,
        'bars': n,
        'years': round(years, 1),
        'trades': n_t,
        'trades_yr': round(trades_per_year, 1),
        'wr': round(wr, 2),
        'pf': round(pf, 2),
        'sum_r': round(sum_r, 2),
    }

# Candidate assets configurations
tests = [
    # Commodities
    ('GOLD', 'M15', {'tp_mult': 0.60, 'sl_mult': 1.80, 'min_wick': 0.45, 'clv_th': 0.75, 's_start': 7, 's_end': 18, 'holding_bars': 8, 'allow_short': True, 'max_opp_wick': 0.15}),
    ('GOLD', 'M30', {'tp_mult': 0.65, 'sl_mult': 1.80, 'min_wick': 0.45, 'clv_th': 0.75, 's_start': 7, 's_end': 18, 'holding_bars': 8, 'allow_short': True, 'max_opp_wick': 0.15}),
    # US Tech
    ('US100', 'M15', {'tp_mult': 0.55, 'sl_mult': 2.00, 'min_wick': 0.45, 'clv_th': 0.75, 's_start': 13, 's_end': 20, 'holding_bars': 8, 'allow_short': False, 'max_opp_wick': 0.12}),
    ('US100', 'M30', {'tp_mult': 0.60, 'sl_mult': 2.00, 'min_wick': 0.45, 'clv_th': 0.75, 's_start': 13, 's_end': 20, 'holding_bars': 8, 'allow_short': False, 'max_opp_wick': 0.12}),
    # Dow Jones
    ('[DJI30]', 'M15', {'tp_mult': 0.50, 'sl_mult': 2.00, 'min_wick': 0.45, 'clv_th': 0.75, 's_start': 13, 's_end': 20, 'holding_bars': 8, 'allow_short': False, 'max_opp_wick': 0.14}),
    ('[DJI30]', 'M30', {'tp_mult': 0.55, 'sl_mult': 2.00, 'min_wick': 0.45, 'clv_th': 0.75, 's_start': 13, 's_end': 20, 'holding_bars': 8, 'allow_short': False, 'max_opp_wick': 0.14}),
    # Forex Majors
    ('GBPUSD', 'M15', {'tp_mult': 0.50, 'sl_mult': 1.80, 'min_wick': 0.50, 'clv_th': 0.80, 's_start': 7, 's_end': 16, 'holding_bars': 8, 'allow_short': True, 'max_opp_wick': 0.20}),
    ('GBPUSD', 'M30', {'tp_mult': 0.55, 'sl_mult': 1.80, 'min_wick': 0.50, 'clv_th': 0.80, 's_start': 7, 's_end': 16, 'holding_bars': 8, 'allow_short': True, 'max_opp_wick': 0.20}),
    ('USDJPY', 'M15', {'tp_mult': 0.50, 'sl_mult': 1.80, 'min_wick': 0.50, 'clv_th': 0.80, 's_start': 6, 's_end': 16, 'holding_bars': 8, 'allow_short': True, 'max_opp_wick': 0.20}),
    ('USDJPY', 'M30', {'tp_mult': 0.55, 'sl_mult': 1.80, 'min_wick': 0.50, 'clv_th': 0.80, 's_start': 6, 's_end': 16, 'holding_bars': 8, 'allow_short': True, 'max_opp_wick': 0.20}),
    # Crypto CFDs
    ('BTCUSD', 'M15', {'tp_mult': 0.60, 'sl_mult': 1.80, 'min_wick': 0.45, 'clv_th': 0.75, 's_start': 0, 's_end': 24, 'holding_bars': 8, 'allow_short': False, 'max_opp_wick': 0.15}),
    ('BTCUSD', 'M30', {'tp_mult': 0.65, 'sl_mult': 1.80, 'min_wick': 0.45, 'clv_th': 0.75, 's_start': 0, 's_end': 24, 'holding_bars': 8, 'allow_short': False, 'max_opp_wick': 0.15}),
    # Oil
    ('BRENT', 'M15', {'tp_mult': 0.55, 'sl_mult': 1.80, 'min_wick': 0.45, 'clv_th': 0.75, 's_start': 7, 's_end': 18, 'holding_bars': 8, 'allow_short': True, 'max_opp_wick': 0.15}),
]

results = []
print(f"{'Symbol':<10} {'TF':<5} {'Bars':<7} {'Years':<6} {'Trades':<8} {'Tr/Yr':<7} {'WinRate':<9} {'ProfitFact':<11} {'Sum(R)':<8}")
print("-" * 75)

for sym, tf_s, cfg in tests:
    tf_code = mt5.TIMEFRAME_M15 if tf_s == 'M15' else mt5.TIMEFRAME_M30
    res = backtest_sniper_asset(sym, tf_code, tf_s, cfg)
    if res:
        results.append(res)
        print(f"{res['symbol']:<10} {res['tf']:<5} {res['bars']:<7} {res['years']:<6} {res['trades']:<8} {res['trades_yr']:<7} {res['wr']:<8.2f}% {res['pf']:<11.2f} {res['sum_r']:<+8.2f}R")

df_res = pd.DataFrame(results)
df_res.to_csv('scripts/research_new_assets_results.csv', index=False)
