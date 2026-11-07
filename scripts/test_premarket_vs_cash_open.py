import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import sys
sys.path.insert(0, '.')

mt5.initialize()
from scripts.forensic_auditor_4years import load_bars_m30
from trading_v2.strategies.micro_scalping import SniperScalpConfig, generate_sniper_signals

df_dax = load_bars_m30('GERMANY40')
print('DAX bars loaded:', len(df_dax))

for start_h in [7, 8]:
    cfg = SniperScalpConfig(
        symbol='GERMANY40', target_units=22.0, stop_units=35.0,
        session_start_h=start_h, session_end_h=17, min_rejection_wick=0.35,
        cooldown_bars=2, use_h1_filter=True, use_ker_filter=True, max_ker_trend=0.45,
        use_climax_filter=True, allow_short=True
    )
    sig_df = generate_sniper_signals(df_dax, cfg)
    signals = sig_df['signal'].to_numpy()
    
    opens = df_dax['Open'].to_numpy()
    highs = df_dax['High'].to_numpy()
    lows = df_dax['Low'].to_numpy()
    closes = df_dax['Close'].to_numpy()
    times = df_dax.index
    n = len(df_dax)
    
    trades = []
    i = 0
    while i < n - 1:
        sig = signals[i]
        if sig != 0:
            entry_px = opens[i+1] + (1.2 if sig==1 else 0)
            sl_px = entry_px - 35.0 if sig==1 else entry_px + 35.0
            tp_px = entry_px + 22.0 if sig==1 else entry_px - 22.0
            exit_px = None
            for j in range(i+1, min(i+9, n)):
                if sig == 1:
                    if lows[j] <= sl_px and highs[j] >= tp_px:
                        exit_px = tp_px if closes[j] > opens[j] else sl_px
                        break
                    elif highs[j] >= tp_px:
                        exit_px = tp_px
                        break
                    elif lows[j] <= sl_px:
                        exit_px = sl_px
                        break
                else:
                    if highs[j]+1.2 >= sl_px and lows[j]+1.2 <= tp_px:
                        exit_px = tp_px if closes[j] < opens[j] else sl_px
                        break
                    elif lows[j]+1.2 <= tp_px:
                        exit_px = tp_px
                        break
                    elif highs[j]+1.2 >= sl_px:
                        exit_px = sl_px
                        break
            if exit_px is None:
                exit_px = closes[min(i+8, n-1)]
            pnl = ((exit_px - entry_px)/35.0)*45.0 if sig==1 else ((entry_px - exit_px)/35.0)*45.0
            trades.append(pnl)
            i = j + 2
        else:
            i += 1
            
    df_res = pd.Series(trades)
    wins = df_res[df_res > 0]
    wr = len(wins)/len(df_res)*100
    pf = wins.sum() / abs(df_res[df_res < 0].sum())
    pnl = df_res.sum()
    cum = df_res.cumsum()
    dd = (cum.cummax() - cum).max()
    lbl = '08:00 CET (Con Pre-Apertura)' if start_h == 7 else '09:00 CET (Apertura Real Xetra)'
    print(f'{lbl:<32s} | Trades: {len(df_res):4d} | WR: {wr:5.1f}% | PF: {pf:4.2f} | PnL: {pnl:+9.2f} EUR | Max DD: {dd:7.2f} EUR')
