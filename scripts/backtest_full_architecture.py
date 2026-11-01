import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from trading_v2.backtesting.contract_specs import get_contract_spec, calculate_lot_size
from trading_v2.strategies.micro_scalping import SniperScalpConfig, generate_sniper_signals

mt5.initialize()

start_fetch = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
end_sim = datetime(2026, 10, 31, 0, 0, tzinfo=timezone.utc)
oct_start = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)

ASSETS = {
    "GERMANY40": {"tgt": 12.0, "sl": 35.0, "sw": 8.0, "ss": 7, "se": 15, "mw": 0.45, "keltner": True, "opp": None, "short": False},
    "[IBEX35]": {"tgt": 15.0, "sl": 25.0, "sw": 5.0, "ss": 7, "se": 11, "mw": 0.55, "keltner": False, "opp": None, "short": False},
    "[DJI30]": {"tgt": 55.0, "sl": 110.0, "sw": 25.0, "ss": 13, "se": 20, "mw": 0.45, "keltner": False, "opp": 0.12, "short": False},
    "GOLD": {"tgt": 4.0, "sl": 12.0, "sw": 2.0, "ss": 12, "se": 19, "mw": 0.45, "keltner": False, "opp": 0.12, "short": False},
    "[SP500]": {"tgt": 4.0, "sl": 7.5, "sw": 2.5, "ss": 13, "se": 20, "mw": 0.45, "keltner": False, "opp": 0.12, "short": False},
    "EURUSD": {"tgt": 3.0, "sl": 5.0, "sw": 1.5, "ss": 7, "se": 16, "mw": 0.55, "keltner": False, "opp": None, "short": True}
}

dfs_m15 = {}
dfs_h1 = {}
signals_dict = {}

for sym, p in ASSETS.items():
    r_m15 = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M15, start_fetch, end_sim)
    r_h1 = mt5.copy_rates_range(sym, mt5.TIMEFRAME_H1, start_fetch, end_sim)
    if r_m15 is None or r_h1 is None:
        continue
    
    df15 = pd.DataFrame(r_m15)
    df15['time'] = pd.to_datetime(df15['time'], unit='s', utc=True)
    df15.set_index('time', inplace=True)
    df15.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'tick_volume': 'Volume'}, inplace=True)
    
    dfh1 = pd.DataFrame(r_h1)
    dfh1['time'] = pd.to_datetime(dfh1['time'], unit='s', utc=True)
    dfh1.set_index('time', inplace=True)
    # H1 trend: Close > SMA50
    h1_sma = dfh1['close'].rolling(50, min_periods=20).mean()
    dfh1['h1_trend'] = np.where(dfh1['close'] > h1_sma, 1, np.where(dfh1['close'] < h1_sma, -1, 0))
    # Align H1 to M15 backward
    dfh1['h1_close_time'] = dfh1.index + pd.Timedelta(hours=1)
    df15_reset = df15.reset_index()
    merged = pd.merge_asof(
        df15_reset,
        dfh1[['h1_close_time', 'h1_trend']].reset_index(drop=True),
        left_on='time',
        right_on='h1_close_time',
        direction='backward'
    )
    merged.set_index('time', inplace=True)
    df15['h1_trend'] = merged['h1_trend'].fillna(0).astype(int)
    
    cfg = SniperScalpConfig(
        symbol=sym,
        target_units=p['tgt'],
        stop_units=p['sl'],
        session_start_h=p['ss'],
        session_end_h=p['se'],
        max_holding_bars=4,
        min_sweep_units=p['sw'],
        min_rejection_wick=p['mw'],
        use_h1_filter=True, # Active H1 filter!
        use_keltner_filter=p['keltner'],
        max_opposite_wick=p['opp'],
        allow_short=p['short'],
        cooldown_bars=6, # 1.5h cooldown between trades
        max_trades_per_day=2, # max 2 trades a day per asset
        enable_m4_fade=False,
        enable_yeboster_reclaim=False
    )
    sig_df = generate_sniper_signals(df15, cfg)
    dfs_m15[sym] = df15
    signals_dict[sym] = sig_df['signal']

all_times = sorted(list(set.union(*[set(dfs_m15[s].loc[oct_start:end_sim].index) for s in dfs_m15])))

balance = 3000.0
initial_balance = balance
risk_fraction = 0.0100

open_positions = []
trades_history = []
max_concurrent = 2
eurusd_df = dfs_m15.get("EURUSD")

for t in all_times:
    remaining_pos = []
    for pos in open_positions:
        sym = pos['symbol']
        df_sym = dfs_m15[sym]
        if t not in df_sym.index:
            remaining_pos.append(pos)
            continue
            
        bar = df_sym.loc[t]
        bar_l = bar['Low']
        bar_h = bar['High']
        bar_c = bar['Close']
        side = pos['side']
        entry = pos['entry']
        tp = pos['tp']
        sl = pos['sl']
        be_trig = pos['be_trig']
        be_lock = pos['be_lock']
        spec = pos['spec']
        lots = pos['lots']
        bars_held = pos['bars_held'] + 1
        pos['bars_held'] = bars_held
        
        exit_price = None
        exit_reason = None
        
        if side == 'BUY':
            if bar_l <= sl and bar_h >= tp:
                exit_price = sl; exit_reason = "STOP_LOSS"
            elif bar_l <= sl:
                exit_price = sl; exit_reason = "STOP_LOSS"
            elif bar_h >= tp:
                exit_price = tp; exit_reason = "TAKE_PROFIT"
            elif bar_c >= be_trig and pos['sl'] < be_lock:
                pos['sl'] = be_lock
                
            if exit_price is None and bars_held >= 6:
                exit_price = bar_c; exit_reason = "TIME_EXIT"
        else: # SELL
            if bar_h >= sl and bar_l <= tp:
                exit_price = sl; exit_reason = "STOP_LOSS"
            elif bar_h >= sl:
                exit_price = sl; exit_reason = "STOP_LOSS"
            elif bar_l <= tp:
                exit_price = tp; exit_reason = "TAKE_PROFIT"
            elif bar_c <= be_trig and pos['sl'] > be_lock:
                pos['sl'] = be_lock
                
            if exit_price is None and bars_held >= 6:
                exit_price = bar_c; exit_reason = "TIME_EXIT"
                
        if exit_price is not None:
            point = spec.point
            pts_diff = (exit_price - entry) if side == 'BUY' else (entry - exit_price)
            if spec.profit_currency == 'EUR':
                pnl_eur = pts_diff * lots * spec.contract_size
            else:
                eurusd_px = float(eurusd_df.loc[t]['Close']) if (eurusd_df is not None and t in eurusd_df.index) else 1.12
                pnl_usd = pts_diff * lots * spec.contract_size
                pnl_eur = pnl_usd / eurusd_px
                
            balance += pnl_eur
            trades_history.append({
                'entry_time': pos['entry_time'],
                'exit_time': t,
                'symbol': sym,
                'side': side,
                'lots': lots,
                'entry': entry,
                'exit': exit_price,
                'pnl_eur': round(pnl_eur, 2),
                'reason': exit_reason,
                'balance': round(balance, 2)
            })
        else:
            remaining_pos.append(pos)
            
    open_positions = remaining_pos
    
    # Enter new signals
    for sym in ASSETS:
        if len(open_positions) >= max_concurrent:
            break
        if any(p['symbol'] == sym for p in open_positions):
            continue
            
        df_sym = dfs_m15[sym]
        if t not in df_sym.index:
            continue
            
        loc_idx = df_sym.index.get_loc(t)
        if loc_idx < 1:
            continue
        prev_t = df_sym.index[loc_idx - 1]
        sig = signals_dict[sym].loc[prev_t]
        
        if sig == 0:
            continue
            
        bar_t = df_sym.loc[t]
        spec = get_contract_spec(sym)
        spread_pts = spec.point * (120 if 'GER' in sym else 350 if 'IBEX' in sym else 250 if 'DJI' in sym else 50 if 'GOLD' in sym else 8 if 'EUR' in sym else 60)
        
        side = 'BUY' if sig > 0 else 'SELL'
        cfg_p = ASSETS[sym]
        unit = 0.00010 if sym == "EURUSD" else 1.0
        tgt_dist = cfg_p['tgt'] * unit
        sl_dist = cfg_p['sl'] * unit
        
        entry = bar_t['Open'] + (spread_pts * 0.5 if side == 'BUY' else -spread_pts * 0.5)
        tp = entry + (tgt_dist if side == 'BUY' else -tgt_dist)
        sl = entry - (sl_dist if side == 'BUY' else -sl_dist)
        
        be_trig = entry + (tgt_dist * 0.45 if side == 'BUY' else -tgt_dist * 0.45)
        be_lock = entry + (spread_pts * 1.5 if side == 'BUY' else -spread_pts * 1.5)
        
        eurusd_px = float(eurusd_df.loc[t]['Close']) if (eurusd_df is not None and t in eurusd_df.index) else 1.12
        lot_res = calculate_lot_size(
            spec=spec,
            account_equity=balance,
            risk_fraction=risk_fraction,
            stop_distance_price=sl_dist,
            entry_price=entry,
            eurusd_rate=eurusd_px,
            leverage=100.0,
            account_currency="EUR"
        )
        if lot_res.status != "OK" or lot_res.lots < spec.lot_min:
            continue
            
        open_positions.append({
            'symbol': sym,
            'side': side,
            'entry_time': t,
            'entry': entry,
            'tp': tp,
            'sl': sl,
            'be_trig': be_trig,
            'be_lock': be_lock,
            'lots': lot_res.lots,
            'spec': spec,
            'bars_held': 0
        })

print(f"=== FULL ARCHITECTURE BACKTEST (H1 MACRO + COOLDOWN + RISK 1.0%) ===")
print(f"Capital Inicial: {initial_balance:.2f} EUR")
print(f"Capital Final:   {balance:.2f} EUR")
net_pnl = balance - initial_balance
roi_pct = (net_pnl / initial_balance) * 100.0
print(f"Beneficio Neto:  {net_pnl:+.2f} EUR ({roi_pct:+.2f}%)")

tdf = pd.DataFrame(trades_history)
if not tdf.empty:
    n_trades = len(tdf)
    wins = tdf[tdf['pnl_eur'] > 0]
    losses = tdf[tdf['pnl_eur'] < 0]
    wr = (len(wins) / n_trades) * 100.0
    tot_win = wins['pnl_eur'].sum()
    tot_loss = abs(losses['pnl_eur'].sum())
    pf = tot_win / tot_loss if tot_loss > 0 else float('inf')
    
    print(f"\nTotal Operaciones: {n_trades}")
    print(f"Ganadoras:         {len(wins)} ({wr:.1f}%)")
    print(f"Perdedoras:        {len(losses)} ({len(losses)/n_trades*100.0:.1f}%)")
    print(f"Profit Factor:     {pf:.2f}")
    
    print("\nDesglose por Activo:")
    by_sym = tdf.groupby('symbol').agg(
        trades=('pnl_eur', 'count'),
        wins=('pnl_eur', lambda x: (x > 0).sum()),
        pnl=('pnl_eur', 'sum')
    )
    by_sym['wr_%'] = (by_sym['wins'] / by_sym['trades']) * 100.0
    print(by_sym.to_string())
    
    print("\nDetalle de Operaciones:")
    for _, r in tdf.iterrows():
        print(f"  {r['entry_time'].strftime('%Y-%m-%d %H:%M')} | {r['symbol']:10} | {r['side']} {r['lots']:4.2f} | {r['pnl_eur']:+6.2f} EUR | {r['reason']:11} | Bal: {r['balance']:.2f}")

mt5.shutdown()
