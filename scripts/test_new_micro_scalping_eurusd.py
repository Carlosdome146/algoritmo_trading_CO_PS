"""Verifica que generate_sniper_signals() produzca los resultados exactos esperados en EURUSD."""
from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from trading_v2.research.regime_lab_v3 import metrics
from trading_v2.strategies.micro_scalping import SniperScalpConfig, generate_sniper_signals

def main():
    if not mt5.initialize():
        return
        
    rates = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_M15, 0, 5000)
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "spread": "Spread"}, inplace=True)
    
    cfg = SniperScalpConfig(
        symbol="EURUSD",
        target_units=3.5,
        stop_units=5.5,
        session_start_h=6,
        session_end_h=20,
        max_holding_bars=8,
        min_sweep_units=0.0,
        min_rejection_wick=0.35,
        max_trades_per_day=None,
        cooldown_bars=2,
        use_h1_filter=False,
        allow_short=True,
    )
    
    sig_df = generate_sniper_signals(df, cfg)
    sigs = sig_df["signal"].values
    
    c = df["Close"].values
    h = df["High"].values
    l = df["Low"].values
    o = df["Open"].values
    n = len(df)
    
    pip = 0.00010
    spr_d = 0.8 * pip
    tgt_d = 3.5 * pip
    sl_d = 5.5 * pip
    be_trig_d = 2.0 * pip
    be_lock_d = 0.5 * pip
    
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
            entry_px = o[k] + spr_d * 0.5
            tp_px = entry_px + tgt_d
            sl_px = entry_px - sl_d
            cur_sl = sl_px
            be_trig_px = entry_px + be_trig_d
            be_lock_px = entry_px + be_lock_d
            exit_px = None
            for j in range(k, min(n, k + 8)):
                if l[j] <= cur_sl and h[j] >= tp_px:
                    exit_px = cur_sl if c[j] < o[j] else tp_px
                    break
                elif l[j] <= cur_sl:
                    exit_px = cur_sl
                    break
                elif h[j] >= tp_px:
                    exit_px = tp_px
                    break
                if h[j] >= be_trig_px and cur_sl < be_lock_px:
                    cur_sl = be_lock_px
            if exit_px is None:
                j = min(n - 1, k + 7)
                exit_px = c[j] - spr_d * 0.5
            pnl_p = (exit_px - entry_px - spr_d * 0.5) / pip
            trades.append({"entry_time": entry_t, "pnl": pnl_p, "r": pnl_p / 5.5, "win": 1 if pnl_p > 0 else 0})
            i = j + 1
        elif s == -1:
            entry_px = o[k] - spr_d * 0.5
            tp_px = entry_px - tgt_d
            sl_px = entry_px + sl_d
            cur_sl = sl_px
            be_trig_px = entry_px - be_trig_d
            be_lock_px = entry_px - be_lock_d
            exit_px = None
            for j in range(k, min(n, k + 8)):
                if h[j] >= cur_sl and l[j] <= tp_px:
                    exit_px = cur_sl if c[j] > o[j] else tp_px
                    break
                elif h[j] >= cur_sl:
                    exit_px = cur_sl
                    break
                elif l[j] <= tp_px:
                    exit_px = tp_px
                    break
                if l[j] <= be_trig_px and cur_sl > be_lock_px:
                    cur_sl = be_lock_px
            if exit_px is None:
                j = min(n - 1, k + 7)
                exit_px = c[j] + spr_d * 0.5
            pnl_p = (entry_px - exit_px - spr_d * 0.5) / pip
            trades.append({"entry_time": entry_t, "pnl": pnl_p, "r": pnl_p / 5.5, "win": 1 if pnl_p > 0 else 0})
            i = j + 1
            
    tdf = pd.DataFrame(trades)
    tdf_oct = tdf[tdf["entry_time"] >= "2026-10-01"]
    m_oct = metrics(tdf_oct["r"].to_numpy())
    print(f"OCTUBRE 2026 EURUSD CON GENERATE_SNIPER_SIGNALS:")
    print(f"  Operaciones: {len(tdf_oct)}")
    print(f"  Win Rate: {m_oct['win_rate']:.1f}%")
    print(f"  Profit Factor: {m_oct['profit_factor']:.2f}")
    print(f"  Pips netos: {tdf_oct['pnl'].sum():+.1f} pips")
    print(f"  Retorno en R: {tdf_oct['r'].sum():+.2f} R")
    
    mt5.shutdown()

if __name__ == "__main__":
    main()
