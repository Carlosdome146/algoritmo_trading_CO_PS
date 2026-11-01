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

# Power Hours Only:
# Europe: 07:00 - 09:30 UTC (09:00 - 11:30 CET)
# US: 13:30 - 16:30 UTC (15:30 - 18:30 CET)
ASSETS = {
    "[DJI30]": {"tgt": 55.0, "sl": 110.0, "sw": 25.0, "ss": 13, "se": 17, "mw": 0.45, "keltner": False, "opp": 0.12},
    "GOLD": {"tgt": 4.0, "sl": 12.0, "sw": 2.0, "ss": 13, "se": 17, "mw": 0.45, "keltner": False, "opp": 0.12},
    "GERMANY40": {"tgt": 12.0, "sl": 25.0, "sw": 8.0, "ss": 7, "se": 9, "mw": 0.45, "keltner": True, "opp": None},
    "[IBEX35]": {"tgt": 15.0, "sl": 25.0, "sw": 5.0, "ss": 7, "se": 9, "mw": 0.55, "keltner": False, "opp": None},
}

dfs = {}
signals = {}

for sym, p in ASSETS.items():
    r = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M15, start_fetch, end_sim)
    df = pd.DataFrame(r)
    df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
    df.set_index('time', inplace=True)
    df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'tick_volume': 'Volume'}, inplace=True)
    
    cfg = SniperScalpConfig(
        symbol=sym, target_units=p['tgt'], stop_units=p['sl'],
        session_start_h=p['ss'], session_end_h=p['se'],
        max_holding_bars=4, min_sweep_units=p['sw'], min_rejection_wick=p['mw'],
        use_h1_filter=False, use_keltner_filter=p['keltner'], max_opposite_wick=p['opp'],
        allow_short=False, cooldown_bars=8, max_trades_per_day=1, # 1 trade per day!
        enable_m4_fade=False, enable_yeboster_reclaim=False
    )
    sig_df = generate_sniper_signals(df, cfg)
    dfs[sym] = df
    signals[sym] = sig_df['signal']

all_times = sorted(list(set.union(*[set(dfs[s].loc[oct_start:end_sim].index) for s in dfs])))
r_eur = mt5.copy_rates_range("EURUSD", mt5.TIMEFRAME_M15, start_fetch, end_sim)
eur_df = pd.DataFrame(r_eur)
eur_df['time'] = pd.to_datetime(eur_df['time'], unit='s', utc=True)
eur_df.set_index('time', inplace=True)

balance = 3000.0
initial_balance = balance
risk_fraction = 0.0100
open_positions = []
trades_history = []

for t in all_times:
    remaining_pos = []
    for pos in open_positions:
        sym = pos['symbol']
        df_sym = dfs[sym]
        if t not in df_sym.index:
            remaining_pos.append(pos); continue
        bar = df_sym.loc[t]
        bar_l = bar['Low']; bar_h = bar['High']; bar_c = bar['Close']
        side = pos['side']; entry = pos['entry']; tp = pos['tp']; sl = pos['sl']
        be_trig = pos['be_trig']; be_lock = pos['be_lock']
        spec = pos['spec']; lots = pos['lots']
        pos['bars_held'] += 1
        
        exit_price = None; exit_reason = None
        if bar_l <= sl and bar_h >= tp: exit_price = sl; exit_reason = "STOP_LOSS"
        elif bar_l <= sl: exit_price = sl; exit_reason = "STOP_LOSS"
        elif bar_h >= tp: exit_price = tp; exit_reason = "TAKE_PROFIT"
        elif bar_c >= be_trig and pos['sl'] < be_lock: pos['sl'] = be_lock
        if exit_price is None and pos['bars_held'] >= 6: exit_price = bar_c; exit_reason = "TIME_EXIT"
        
        if exit_price is not None:
            pts_diff = exit_price - entry
            if spec.profit_currency == 'EUR':
                pnl_eur = pts_diff * lots * spec.contract_size
            else:
                eur_px = float(eur_df.loc[t]['close']) if t in eur_df.index else 1.12
                pnl_usd = pts_diff * lots * spec.contract_size
                pnl_eur = pnl_usd / eur_px
            balance += pnl_eur
            trades_history.append({
                'entry_time': pos['entry_time'], 'exit_time': t, 'symbol': sym,
                'lots': lots, 'pnl_eur': round(pnl_eur, 2), 'reason': exit_reason, 'balance': round(balance, 2)
            })
        else:
            remaining_pos.append(pos)
    open_positions = remaining_pos
    
    for sym in ASSETS:
        if len(open_positions) >= 2: break
        if any(p['symbol'] == sym for p in open_positions): continue
        df_sym = dfs[sym]
        if t not in df_sym.index: continue
        loc_idx = df_sym.index.get_loc(t)
        if loc_idx < 1: continue
        prev_t = df_sym.index[loc_idx - 1]
        sig = signals[sym].loc[prev_t]
        if sig <= 0: continue
        
        bar_t = df_sym.loc[t]
        spec = get_contract_spec(sym)
        spread_pts = spec.point * (120 if 'GER' in sym else 350 if 'IBEX' in sym else 250 if 'DJI' in sym else 50)
        cfg_p = ASSETS[sym]
        tgt_dist = cfg_p['tgt']
        sl_dist = cfg_p['sl']
        entry = bar_t['Open'] + spread_pts * 0.5
        tp = entry + tgt_dist
        sl = entry - sl_dist
        be_trig = entry + tgt_dist * 0.45
        be_lock = entry + spread_pts * 1.5
        
        eur_px = float(eur_df.loc[t]['close']) if t in eur_df.index else 1.12
        lot_res = calculate_lot_size(
            spec=spec, account_equity=balance, risk_fraction=risk_fraction,
            stop_distance_price=sl_dist, entry_price=entry,
            eurusd_rate=eur_px, leverage=100.0, account_currency="EUR"
        )
        if lot_res.status != "OK" or lot_res.lots < spec.lot_min: continue
        
        open_positions.append({
            'symbol': sym, 'side': 'BUY', 'entry_time': t, 'entry': entry,
            'tp': tp, 'sl': sl, 'be_trig': be_trig, 'be_lock': be_lock,
            'lots': lot_res.lots, 'spec': spec, 'bars_held': 0
        })

print("=== POWER-HOURS SNIPER (1 TRADE/DAY MAX, OPENING SESSIONS ONLY) ===")
print(f"Capital Inicial: {initial_balance:.2f} EUR")
print(f"Capital Final:   {balance:.2f} EUR")
print(f"Beneficio Neto:  {balance - initial_balance:+.2f} EUR ({(balance - initial_balance)/initial_balance*100:+.2f}%)")

tdf = pd.DataFrame(trades_history)
if not tdf.empty:
    n_trades = len(tdf)
    wins = tdf[tdf['pnl_eur'] > 0]
    losses = tdf[tdf['pnl_eur'] < 0]
    wr = (len(wins) / n_trades) * 100.0
    tot_win = wins['pnl_eur'].sum()
    tot_loss = abs(losses['pnl_eur'].sum())
    pf = tot_win / tot_loss if tot_loss > 0 else float('inf')
    print(f"Total Operaciones: {n_trades}")
    print(f"Win Rate:          {wr:.2f}% ({len(wins)}W / {len(losses)}L)")
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
        print(f"  {r['entry_time'].strftime('%Y-%m-%d %H:%M')} | {r['symbol']:10} | {r['lots']:4.2f} lots | {r['pnl_eur']:+6.2f} EUR | {r['reason']:11} | Bal: {r['balance']:.2f}")

mt5.shutdown()
