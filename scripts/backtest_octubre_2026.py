import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from trading_v2.backtesting.contract_specs import get_contract_spec, calculate_lot_size
from trading_v2.strategies.micro_scalping import SniperScalpConfig, generate_sniper_signals

mt5.initialize()

# Define portfolio assets and their exact SniperScalpConfig
ASSET_CONFIGS = {
    "GERMANY40": {
        "target_u": 12.0, "stop_u": 35.0, "sweep_u": 8.0,
        "s_start": 7, "s_end": 15, "min_wick": 0.45,
        "use_keltner": True, "max_opp_wick": None, "allow_short": False
    },
    "[IBEX35]": {
        "target_u": 15.0, "stop_u": 25.0, "sweep_u": 5.0,
        "s_start": 7, "s_end": 11, "min_wick": 0.55,
        "use_keltner": False, "max_opp_wick": None, "allow_short": False
    },
    "EURUSD": {
        "target_u": 3.0, "stop_u": 5.0, "sweep_u": 1.5,
        "s_start": 7, "s_end": 16, "min_wick": 0.55,
        "use_keltner": False, "max_opp_wick": None, "allow_short": True
    },
    "[DJI30]": {
        "target_u": 55.0, "stop_u": 110.0, "sweep_u": 25.0,
        "s_start": 13, "s_end": 20, "min_wick": 0.45,
        "use_keltner": False, "max_opp_wick": 0.12, "allow_short": False
    },
    "GOLD": {
        "target_u": 4.0, "stop_u": 12.0, "sweep_u": 2.0,
        "s_start": 12, "s_end": 19, "min_wick": 0.45,
        "use_keltner": False, "max_opp_wick": 0.12, "allow_short": False
    },
    "[SP500]": {
        "target_u": 4.0, "stop_u": 7.5, "sweep_u": 2.5,
        "s_start": 13, "s_end": 20, "min_wick": 0.45,
        "use_keltner": False, "max_opp_wick": 0.12, "allow_short": False
    }
}

# Fetch data with warmup (from mid-September to end of October 2026)
start_fetch = datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc)
end_sim = datetime(2026, 10, 31, 0, 0, tzinfo=timezone.utc)
oct_start = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)

dfs = {}
signals_dict = {}

for sym, p in ASSET_CONFIGS.items():
    rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M15, start_fetch, end_sim)
    if rates is None or len(rates) < 250:
        continue
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
    df.set_index('time', inplace=True)
    df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'tick_volume': 'Volume'}, inplace=True)
    
    cfg = SniperScalpConfig(
        symbol=sym,
        target_units=p['target_u'],
        stop_units=p['stop_u'],
        session_start_h=p['s_start'],
        session_end_h=p['s_end'],
        max_holding_bars=4,
        min_sweep_units=p['sweep_u'],
        min_rejection_wick=p['min_wick'],
        use_h1_filter=False,
        use_keltner_filter=p['use_keltner'],
        max_opposite_wick=p['max_opp_wick'],
        allow_short=p['allow_short'],
        enable_m4_fade=True,
        enable_yeboster_reclaim=True
    )
    sig_df = generate_sniper_signals(df, cfg)
    dfs[sym] = df
    signals_dict[sym] = sig_df['signal']

# Merge all timestamps in October
all_times = sorted(list(set.union(*[set(dfs[s].loc[oct_start:end_sim].index) for s in dfs])))

balance = 3000.0
initial_balance = balance
risk_fraction = 0.0100 # 1.0%

open_positions = []
trades_history = []
max_concurrent = 2

eurusd_df = dfs.get("EURUSD")

for t in all_times:
    # 1. Update open positions
    remaining_pos = []
    for pos in open_positions:
        sym = pos['symbol']
        df_sym = dfs[sym]
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
                exit_price = sl
                exit_reason = "STOP_LOSS"
            elif bar_l <= sl:
                exit_price = sl
                exit_reason = "STOP_LOSS"
            elif bar_h >= tp:
                exit_price = tp
                exit_reason = "TAKE_PROFIT"
            elif bar_c >= be_trig and pos['sl'] < be_lock:
                pos['sl'] = be_lock
                
            if exit_price is None and bars_held >= 6:
                exit_price = bar_c
                exit_reason = "TIME_EXIT"
        else: # SELL
            if bar_h >= sl and bar_l <= tp:
                exit_price = sl
                exit_reason = "STOP_LOSS"
            elif bar_h >= sl:
                exit_price = sl
                exit_reason = "STOP_LOSS"
            elif bar_l <= tp:
                exit_price = tp
                exit_reason = "TAKE_PROFIT"
            elif bar_c <= be_trig and pos['sl'] > be_lock:
                pos['sl'] = be_lock
                
            if exit_price is None and bars_held >= 6:
                exit_price = bar_c
                exit_reason = "TIME_EXIT"
                
        if exit_price is not None:
            # Calculate profit in EUR
            point = spec.point
            pts_diff = (exit_price - entry) if side == 'BUY' else (entry - exit_price)
            # order_calc_profit emulation
            if spec.profit_currency == 'EUR':
                pnl_eur = pts_diff * lots * spec.contract_size
            else: # USD
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
    
    # 2. Check new signals at bar close (enter at next bar open, which is t)
    for sym in ASSET_CONFIGS:
        if len(open_positions) >= max_concurrent:
            break
        if any(p['symbol'] == sym for p in open_positions):
            continue
            
        df_sym = dfs[sym]
        if t not in df_sym.index:
            continue
            
        # Get signal from previous bar
        loc_idx = df_sym.index.get_loc(t)
        if loc_idx < 1:
            continue
        prev_t = df_sym.index[loc_idx - 1]
        sig = signals_dict[sym].loc[prev_t]
        
        if sig == 0:
            continue
            
        bar_t = df_sym.loc[t]
        spec = get_contract_spec(sym)
        spread_pts = spec.typical_spread_points * spec.point if spec.typical_spread_points > 0 else (spec.point * (120 if 'GER' in sym else 350 if 'IBEX' in sym else 250 if 'DJI' in sym else 50 if 'GOLD' in sym else 8 if 'EUR' in sym else 60))
        
        side = 'BUY' if sig > 0 else 'SELL'
        cfg_p = ASSET_CONFIGS[sym]
        unit = 0.00010 if sym == "EURUSD" else 1.0
        tgt_dist = cfg_p['target_u'] * unit
        sl_dist = cfg_p['stop_u'] * unit
        
        entry = bar_t['Open'] + (spread_pts * 0.5 if side == 'BUY' else -spread_pts * 0.5)
        tp = entry + (tgt_dist if side == 'BUY' else -tgt_dist)
        sl = entry - (sl_dist if side == 'BUY' else -sl_dist)
        
        be_trig = entry + (tgt_dist * 0.45 if side == 'BUY' else -tgt_dist * 0.45)
        be_lock = entry + (spread_pts * 1.5 if side == 'BUY' else -spread_pts * 1.5)
        
        # Position sizing (1% risk)
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

print(f"=== BACKTEST RESULT: OCTUBRE 2026 (PORTAFOLIO SNIPER 1.0% RIESGO) ===")
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
    be_trades = tdf[tdf['pnl_eur'] == 0]
    wr = (len(wins) / n_trades) * 100.0
    tot_win = wins['pnl_eur'].sum()
    tot_loss = abs(losses['pnl_eur'].sum())
    pf = tot_win / tot_loss if tot_loss > 0 else float('inf')
    
    print(f"\nTotal Operaciones: {n_trades}")
    print(f"Ganadoras:         {len(wins)} ({wr:.1f}%)")
    print(f"Perdedoras:        {len(losses)} ({len(losses)/n_trades*100.0:.1f}%)")
    print(f"Breakeven / Cero:  {len(be_trades)}")
    print(f"Profit Factor:     {pf:.2f}")
    print(f"Ganancia Media Win: {wins['pnl_eur'].mean():.2f} EUR")
    print(f"Pérdida Media Loss: {losses['pnl_eur'].mean() if len(losses)>0 else 0:.2f} EUR")
    
    print("\nDesglose por Activo:")
    by_sym = tdf.groupby('symbol').agg(
        trades=('pnl_eur', 'count'),
        wins=('pnl_eur', lambda x: (x > 0).sum()),
        pnl=('pnl_eur', 'sum')
    )
    by_sym['wr_%'] = (by_sym['wins'] / by_sym['trades']) * 100.0
    print(by_sym.to_string())
    
    print("\nDetalle de Operaciones en Octubre:")
    for _, r in tdf.iterrows():
        print(f"  {r['entry_time'].strftime('%Y-%m-%d %H:%M')} -> {r['exit_time'].strftime('%H:%M')} | {r['symbol']:10} | {r['side']} {r['lots']:4.2f} lots | {r['pnl_eur']:+6.2f} EUR | {r['reason']:11} | Bal: {r['balance']:.2f}")
else:
    print("No se generaron operaciones en el periodo.")

mt5.shutdown()
