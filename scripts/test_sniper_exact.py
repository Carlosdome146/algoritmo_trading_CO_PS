import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from trading_v2.strategies.micro_scalping import SniperScalpConfig, generate_sniper_signals
from trading_v2.research.regime_lab_v3 import metrics

mt5.initialize()

def backtest_sniper_exact(symbol, tf_code, target_u, stop_u, sweep_u, s_start, s_end,
                          min_wick, max_opp_wick, use_keltner, bars=40000):
    rates = mt5.copy_rates_from_pos(symbol, tf_code, 0, bars)
    if rates is None or len(rates) < 1000:
        return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
    df.set_index('time', inplace=True)
    df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'tick_volume': 'Volume'}, inplace=True)
    
    spec = mt5.symbol_info(symbol)
    spread = spec.spread * spec.point
    
    cfg = SniperScalpConfig(
        symbol=symbol,
        target_units=target_u,
        stop_units=stop_u,
        session_start_h=s_start,
        session_end_h=s_end,
        max_holding_bars=6,
        min_sweep_units=sweep_u,
        min_rejection_wick=min_wick,
        use_h1_filter=False,
        use_keltner_filter=use_keltner,
        max_opposite_wick=max_opp_wick,
        enable_m4_fade=True,
        enable_yeboster_reclaim=True
    )
    
    signals_df = generate_sniper_signals(df, cfg)
    sig = signals_df['signal'].values
    c = df['Close'].values
    h = df['High'].values
    l = df['Low'].values
    o = df['Open'].values
    n = len(df)
    
    trades = []
    i = 210
    while i < n - 1:
        if sig[i] == 0:
            i += 1
            continue
            
        k = i + 1
        side = 'BUY' if sig[i] > 0 else 'SELL'
        
        if side == 'BUY':
            entry = o[k] + spread * 0.5
            tp_px = entry + target_u
            sl_px = entry - stop_u
            be_trig = entry + (target_u * 0.45)
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
            trades.append({'time': df.index[k], 'pnl': pnl, 'r': pnl / stop_u, 'win': 1 if pnl > 0 else 0})
            i = j + 1
        else:
            entry = o[k] - spread * 0.5
            tp_px = entry - target_u
            sl_px = entry + stop_u
            be_trig = entry - (target_u * 0.45)
            be_lock = entry - (spread * 1.5)
            cur_sl = sl_px
            exit_px = None
            
            for j in range(k, min(n, k + 8)):
                bar_l = l[j]; bar_h = h[j]
                if bar_h >= cur_sl and bar_l <= tp_px:
                    exit_px = cur_sl; break
                elif bar_h >= cur_sl:
                    exit_px = cur_sl; break
                elif bar_l <= tp_px:
                    exit_px = tp_px; break
                if c[j] <= be_trig and cur_sl > be_lock:
                    cur_sl = be_lock
                    
            if exit_px is None:
                j = min(n - 1, k + 7)
                exit_px = c[j] + spread * 0.5
                
            pnl = (entry - exit_px) - spread * 0.5
            trades.append({'time': df.index[k], 'pnl': pnl, 'r': pnl / stop_u, 'win': 1 if pnl > 0 else 0})
            i = j + 1
            
    if not trades:
        return None
    tdf = pd.DataFrame(trades)
    wr = tdf['win'].mean() * 100.0
    r_arr = tdf['r'].values
    met = metrics(r_arr)
    years = (df.index[-1] - df.index[210]).days / 365.25
    return {
        'symbol': symbol,
        'trades': len(trades),
        'tr_yr': len(trades) / years,
        'wr': wr,
        'pf': met['profit_factor'],
        'sum_r': r_arr.sum(),
        'exp_r': r_arr.mean(),
        'target_u': target_u,
        'stop_u': stop_u,
        'sweep_u': sweep_u,
        'keltner': use_keltner,
        'opp_wick': max_opp_wick
    }

print("Running parameter tests on US100, [DJI30], GOLD...")
test_configs = [
    # US100 M30
    ('US100', mt5.TIMEFRAME_M30, 20.0, 45.0, 10.0, 13, 20, 0.45, 0.12, True),
    ('US100', mt5.TIMEFRAME_M30, 25.0, 50.0, 15.0, 13, 20, 0.45, 0.12, True),
    ('US100', mt5.TIMEFRAME_M30, 30.0, 60.0, 15.0, 13, 20, 0.45, 0.12, True),
    ('US100', mt5.TIMEFRAME_M30, 25.0, 50.0, 12.0, 13, 20, 0.40, 0.15, False),
    # US100 M15
    ('US100', mt5.TIMEFRAME_M15, 15.0, 35.0, 8.0, 13, 20, 0.45, 0.12, True),
    ('US100', mt5.TIMEFRAME_M15, 20.0, 40.0, 10.0, 13, 20, 0.45, 0.12, True),
    
    # [DJI30] M30
    ('[DJI30]', mt5.TIMEFRAME_M30, 35.0, 75.0, 20.0, 13, 20, 0.45, 0.12, True),
    ('[DJI30]', mt5.TIMEFRAME_M30, 40.0, 80.0, 25.0, 13, 20, 0.45, 0.12, True),
    ('[DJI30]', mt5.TIMEFRAME_M30, 50.0, 100.0, 25.0, 13, 20, 0.45, 0.12, True),
    # [DJI30] M15
    ('[DJI30]', mt5.TIMEFRAME_M15, 30.0, 65.0, 15.0, 13, 20, 0.45, 0.12, True),
    ('[DJI30]', mt5.TIMEFRAME_M15, 35.0, 70.0, 20.0, 13, 20, 0.45, 0.12, True),

    # GOLD M30
    ('GOLD', mt5.TIMEFRAME_M30, 4.0, 8.0, 2.0, 12, 19, 0.45, 0.12, True),
    ('GOLD', mt5.TIMEFRAME_M30, 5.0, 10.0, 2.5, 12, 19, 0.45, 0.12, True),
    ('GOLD', mt5.TIMEFRAME_M30, 6.0, 12.0, 3.0, 12, 19, 0.45, 0.12, True),
    ('GOLD', mt5.TIMEFRAME_M15, 3.0, 6.0, 1.5, 12, 19, 0.45, 0.12, True),
]

res = []
for sym, tf_c, tgt, sl, sw, ss, se, mw, mow, uk in test_configs:
    r = backtest_sniper_exact(sym, tf_c, tgt, sl, sw, ss, se, mw, mow, uk)
    if r:
        r['tf'] = 'M30' if tf_c == mt5.TIMEFRAME_M30 else 'M15'
        res.append(r)

rdf = pd.DataFrame(res)
print(rdf[['symbol', 'tf', 'trades', 'tr_yr', 'wr', 'pf', 'sum_r', 'target_u', 'stop_u']].to_string(index=False))
mt5.shutdown()
