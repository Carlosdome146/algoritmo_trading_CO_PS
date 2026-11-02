"""Simulación exacta de M30 para los 6 índices y materias primas en Octubre 2026."""
from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from trading_v2.strategies.micro_scalping import SniperScalpConfig, generate_sniper_signals
from trading_v2.research.regime_lab_v3 import metrics

def simulate_trade(df, sigs, tgt_pts, sl_pts, spread_pts, be_ratio=0.45, be_lock_pts=1.0, max_hold=6):
    c = df["Close"].values
    h = df["High"].values
    l = df["Low"].values
    o = df["Open"].values
    n = len(df)
    
    be_trig_pts = tgt_pts * be_ratio
    trades = []
    i = 0
    while i < n - 1:
        s = sigs[i]
        if s == 0:
            i += 1
            continue
        k = i + 1
        if k >= n: break
        
        entry_t = df.index[k]
        if s == 1:
            entry_px = o[k] + spread_pts * 0.5
            tp_px = entry_px + tgt_pts
            sl_px = entry_px - sl_pts
            cur_sl = sl_px
            be_trig_px = entry_px + be_trig_pts
            be_lock_px = entry_px + be_lock_pts
            exit_px = None
            exit_reason = None
            for j in range(k, min(n, k + max_hold)):
                if l[j] <= cur_sl and h[j] >= tp_px:
                    exit_px = cur_sl if c[j] < o[j] else tp_px
                    exit_reason = "SL" if c[j] < o[j] else "TP"
                    break
                elif l[j] <= cur_sl:
                    exit_px = cur_sl
                    exit_reason = "SL"
                    break
                elif h[j] >= tp_px:
                    exit_px = tp_px
                    exit_reason = "TP"
                    break
                if h[j] >= be_trig_px and cur_sl < be_lock_px:
                    cur_sl = be_lock_px
            if exit_px is None:
                j = min(n - 1, k + max_hold - 1)
                exit_px = c[j] - spread_pts * 0.5
                exit_reason = "TIME"
            pnl = exit_px - entry_px - spread_pts * 0.5
            trades.append({"time": entry_t, "pnl": pnl, "r": pnl / sl_pts, "win": 1 if pnl > 0 else 0, "reason": exit_reason})
            i = j + 1
        elif s == -1:
            entry_px = o[k] - spread_pts * 0.5
            tp_px = entry_px - tgt_pts
            sl_px = entry_px + sl_pts
            cur_sl = sl_px
            be_trig_px = entry_px - be_trig_pts
            be_lock_px = entry_px - be_lock_pts
            exit_px = None
            exit_reason = None
            for j in range(k, min(n, k + max_hold)):
                if h[j] >= cur_sl and l[j] <= tp_px:
                    exit_px = cur_sl if c[j] > o[j] else tp_px
                    exit_reason = "SL" if c[j] > o[j] else "TP"
                    break
                elif h[j] >= cur_sl:
                    exit_px = cur_sl
                    exit_reason = "SL"
                    break
                elif l[j] <= tp_px:
                    exit_px = tp_px
                    exit_reason = "TP"
                    break
                if l[j] <= be_trig_px and cur_sl > be_lock_px:
                    cur_sl = be_lock_px
            if exit_px is None:
                j = min(n - 1, k + max_hold - 1)
                exit_px = c[j] + spread_pts * 0.5
                exit_reason = "TIME"
            pnl = entry_px - exit_px - spread_pts * 0.5
            trades.append({"time": entry_t, "pnl": pnl, "r": pnl / sl_pts, "win": 1 if pnl > 0 else 0, "reason": exit_reason})
            i = j + 1
            
    return pd.DataFrame(trades)

def main():
    if not mt5.initialize():
        return
        
    configs = [
        ("GERMANY40", 12.0, 25.0, 8.0, 1.2, 0.40, 1.5, True, None, False, 7, 17),
        ("[IBEX35]", 15.0, 25.0, 5.0, 5.0, 0.40, 5.5, False, None, False, 7, 17),
        ("[SP500]", 4.0, 7.5, 2.5, 0.50, 0.45, 0.6, False, 0.12, False, 12, 21),
        ("US100", 25.0, 50.0, 15.0, 1.8, 0.40, 2.5, True, 0.12, False, 12, 21),
        ("[DJI30]", 55.0, 110.0, 25.0, 3.0, 0.40, 4.0, False, 0.12, False, 12, 21),
        ("GOLD", 4.0, 12.0, 2.0, 0.30, 0.40, 0.4, False, 0.12, False, 6, 21),
    ]
    
    print(f"{'Activo':11s} | {'Trades':6s} | {'WinRate':7s} | {'ProfitFactor':12s} | {'Retorno R':9s} | {'Pts / USD':9s}")
    print("-" * 68)
    
    for sym, tgt, sl, sw, spr, be_r, be_l, uk, mow, ash, ss, se in configs:
        r = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M30, 0, 5000)
        df = pd.DataFrame(r)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.set_index("time", inplace=True)
        df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close"}, inplace=True)
        
        cfg = SniperScalpConfig(
            symbol=sym,
            target_units=tgt,
            stop_units=sl,
            min_sweep_units=sw,
            session_start_h=ss,
            session_end_h=se,
            max_holding_bars=4,
            min_rejection_wick=0.45,
            use_h1_filter=True,
            use_keltner_filter=uk,
            max_opposite_wick=mow,
            allow_short=ash,
            max_trades_per_day=None,
            cooldown_bars=3,
        )
        sig_df = generate_sniper_signals(df, cfg)
        tdf = simulate_trade(df, sig_df["signal"].values, tgt_pts=tgt, sl_pts=sl, spread_pts=spr, be_ratio=be_r, be_lock_pts=be_l, max_hold=6)
        
        tdf_oct = tdf[tdf["time"] >= "2026-10-01"]
        if not tdf_oct.empty:
            m = metrics(tdf_oct["r"].to_numpy())
            pf_str = f"{m['profit_factor']:.2f}" if m['profit_factor'] is not None else "INF"
            print(f"{sym:11s} | {len(tdf_oct):6d} | {m['win_rate']:6.1f}% | {pf_str:12s} | {tdf_oct['r'].sum():+8.2f}R | {tdf_oct['pnl'].sum():+8.1f}")
        else:
            print(f"{sym:11s} | 0 trades en Octubre 2026")
            
    mt5.shutdown()

if __name__ == "__main__":
    main()
