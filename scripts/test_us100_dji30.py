import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from trading_v2.research.regime_lab_v3 import metrics

mt5.initialize()

def test_refined_asset(symbol, tf_code, tgt_pts, sl_pts, mw, clv_th, s_start, s_end, use_keltner, max_opp_wick):
    rates = mt5.copy_rates_from_pos(symbol, tf_code, 0, 40000)
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
    spr_cost = spec.spread * spec.point

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

    rec_lo_8 = pd.Series(l).shift(1).rolling(8, min_periods=3).min().values
    hrs = df.index.hour.values
    dow = df.index.dayofweek.values

    trades = []
    i = 210
    while i < n - 1:
        if dow[i] >= 5 or not (s_start <= hrs[i] <= s_end):
            i += 1
            continue
        cur_atr = atr14[i]
        if not np.isfinite(cur_atr) or cur_atr <= 0:
            i += 1
            continue

        bull_struct = (c[i] > sma200[i]) and (ema20[i] > sma200[i])
        long_sig = bull_struct and (l[i] <= rec_lo_8[i]) and (c[i] > ema20[i]) and (lower_wick[i] >= mw) and (clv[i] >= clv_th)

        if use_keltner:
            long_sig = long_sig and (k_pos[i] <= 0.35)
        if max_opp_wick is not None:
            long_sig = long_sig and (upper_wick[i] <= max_opp_wick)

        if not long_sig:
            i += 1
            continue

        k = i + 1
        entry = o[k] + spr_cost * 0.5
        tp_px = entry + tgt_pts
        sl_px = entry - sl_pts

        be_trig = entry + (tgt_pts * 0.45)
        be_lock = entry + (spr_cost * 1.5)
        cur_sl = sl_px
        exit_px = None

        for j in range(k, min(n, k + 8)):
            eval_lo = l[j]; eval_hi = h[j]
            if eval_lo <= cur_sl and eval_hi >= tp_px:
                exit_px = cur_sl; break
            elif eval_lo <= cur_sl:
                exit_px = cur_sl; break
            elif eval_hi >= tp_px:
                exit_px = tp_px; break
            if c[j] >= be_trig and cur_sl < be_lock:
                cur_sl = be_lock

        if exit_px is None:
            j = min(n - 1, k + 7)
            exit_px = c[j] - spr_cost * 0.5

        pnl = (exit_px - entry) - spr_cost * 0.5
        r_val = pnl / sl_pts
        trades.append({'time': df.index[k], 'win': 1 if pnl > 0 else 0, 'r': r_val})
        i = j + 1

    if not trades:
        return None
    tdf = pd.DataFrame(trades)
    n_t = len(tdf)
    wr = tdf['win'].mean() * 100.0
    r_arr = tdf['r'].values
    pf = metrics(r_arr)['profit_factor']
    years = (df.index[-1] - df.index[210]).days / 365.25
    return {'symbol': symbol, 'trades': n_t, 'tr_yr': n_t / years, 'wr': wr, 'pf': pf, 'sum_r': r_arr.sum()}

print("Refined test for US100 and [DJI30]:")
for sym, tf_code, tgt, sl, mw, clv, ss, se, uk, uow in [
    ('US100', mt5.TIMEFRAME_M30, 25.0, 50.0, 0.45, 0.75, 13, 20, True, 0.12),
    ('US100', mt5.TIMEFRAME_M15, 20.0, 45.0, 0.45, 0.75, 13, 20, True, 0.12),
    ('[DJI30]', mt5.TIMEFRAME_M30, 40.0, 80.0, 0.45, 0.75, 13, 20, True, 0.12),
    ('[DJI30]', mt5.TIMEFRAME_M15, 30.0, 70.0, 0.45, 0.75, 13, 20, True, 0.12),
]:
    r = test_refined_asset(sym, tf_code, tgt, sl, mw, clv, ss, se, uk, uow)
    if r:
        tf_name = 'M30' if tf_code == mt5.TIMEFRAME_M30 else 'M15'
        print(f"{sym} {tf_name}: N={r['trades']}, Tr/Yr={r['tr_yr']:.1f}, WR={r['wr']:.2f}%, PF={r['pf']:.2f}, SumR={r['sum_r']:+.2f}R")
