import os
import sys
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from scripts.simular_cartera_completa_octubre import PORTFOLIO_CONFIGS, generate_signals_for_asset, metrics

def simulate_portfolio(portfolio_configs, risk_per_trade=0.015, max_concurrent_indices=2):
    dfs = {}
    for sym, cfg in portfolio_configs.items():
        dfs[sym] = generate_signals_for_asset(sym, cfg)
        
    all_trades = []
    for sym, cfg in portfolio_configs.items():
        df = dfs[sym]
        c = df["close"].values
        h = df["high"].values
        l = df["low"].values
        o = df["open"].values
        sigs = df["signal"].values
        n = len(df)
        
        spread = cfg["spread"]
        tgt = cfg["tgt"]
        sl = cfg["sl"]
        be_trig = tgt * cfg["be_r"]
        be_lock = cfg["be_l"]
        
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
                entry_px = o[k] + spread * 0.5
                tp_px = entry_px + tgt
                sl_px = entry_px - sl
                cur_sl = sl_px
                be_trig_px = entry_px + be_trig
                be_lock_px = entry_px + be_lock
                exit_px = None
                exit_t = None
                reason = None
                for j in range(k, min(n, k + 8)):
                    if l[j] <= cur_sl and h[j] >= tp_px:
                        exit_px = cur_sl if c[j] < o[j] else tp_px
                        exit_t = df.index[j]
                        reason = "SL" if c[j] < o[j] else "TP"
                        break
                    elif l[j] <= cur_sl:
                        exit_px = cur_sl
                        exit_t = df.index[j]
                        reason = "SL"
                        break
                    elif h[j] >= tp_px:
                        exit_px = tp_px
                        exit_t = df.index[j]
                        reason = "TP"
                        break
                    if h[j] >= be_trig_px and cur_sl < be_lock_px:
                        cur_sl = be_lock_px
                if exit_px is None:
                    j = min(n - 1, k + 7)
                    exit_px = c[j] - spread * 0.5
                    exit_t = df.index[j]
                    reason = "TIME"
                pnl = exit_px - entry_px - spread * 0.5
                r_mult = pnl / sl
                all_trades.append({
                    "symbol": sym, "entry_t": entry_t, "exit_t": exit_t,
                    "dir": "BUY", "pnl": pnl, "r": r_mult, "win": 1 if pnl > 0 else 0, "reason": reason
                })
                i = j + 1
            elif s == -1:
                entry_px = o[k] - spread * 0.5
                tp_px = entry_px - tgt
                sl_px = entry_px + sl
                cur_sl = sl_px
                be_trig_px = entry_px - be_trig
                be_lock_px = entry_px - be_lock
                exit_px = None
                exit_t = None
                reason = None
                for j in range(k, min(n, k + 8)):
                    if h[j] >= cur_sl and l[j] <= tp_px:
                        exit_px = cur_sl if c[j] > o[j] else tp_px
                        exit_t = df.index[j]
                        reason = "SL" if c[j] > o[j] else "TP"
                        break
                    elif h[j] >= cur_sl:
                        exit_px = cur_sl
                        exit_t = df.index[j]
                        reason = "SL"
                        break
                    elif l[j] <= tp_px:
                        exit_px = tp_px
                        exit_t = df.index[j]
                        reason = "TP"
                        break
                    if l[j] <= be_trig_px and cur_sl > be_lock_px:
                        cur_sl = be_lock_px
                if exit_px is None:
                    j = min(n - 1, k + 7)
                    exit_px = c[j] + spread * 0.5
                    exit_t = df.index[j]
                    reason = "TIME"
                pnl = entry_px - exit_px - spread * 0.5
                r_mult = pnl / sl
                all_trades.append({
                    "symbol": sym, "entry_t": entry_t, "exit_t": exit_t,
                    "dir": "SELL", "pnl": pnl, "r": r_mult, "win": 1 if pnl > 0 else 0, "reason": reason
                })
                i = j + 1
                
    tdf = pd.DataFrame(all_trades).sort_values(by="entry_t").reset_index(drop=True)
    
    # Simulación cronológica con filtro de correlación concurrente
    initial_balance = 3000.0
    balance = initial_balance
    equity_curve = [balance]
    
    INDEX_SYMBOLS = {"GERMANY40", "[SP500]", "US100", "[DJI30]", "[IBEX35]"}
    active_trades = []
    executed_trades = []
    
    for idx, row in tdf.iterrows():
        t_entry = row["entry_t"]
        active_trades = [tr for tr in active_trades if tr["exit_t"] > t_entry]
        
        sym = row["symbol"]
        is_index = sym in INDEX_SYMBOLS
        active_indices = [tr for tr in active_trades if tr["symbol"] in INDEX_SYMBOLS]
        
        if is_index and len(active_indices) >= max_concurrent_indices:
            continue
            
        risk_budget = balance * risk_per_trade
        pnl_eur = row["r"] * risk_budget
        balance += pnl_eur
        equity_curve.append(balance)
        
        tr_rec = dict(row)
        tr_rec["balance"] = balance
        tr_rec["pnl_eur"] = pnl_eur
        executed_trades.append(tr_rec)
        active_trades.append(row)
        
    ex_df = pd.DataFrame(executed_trades)
    peak = np.maximum.accumulate(equity_curve)
    drawdowns = (peak - equity_curve) / peak
    max_dd = np.max(drawdowns) * 100.0
    m = metrics(ex_df["r"].to_numpy())
    
    return {
        "trades": len(ex_df),
        "win_rate": m["win_rate"],
        "profit_factor": m["profit_factor"],
        "ret_eur": balance - initial_balance,
        "ret_pct": (balance / initial_balance - 1) * 100,
        "max_dd": max_dd,
        "executed_df": ex_df
    }

def main():
    if not mt5.initialize():
        print("MT5 init failed")
        return
        
    print("Testing different configurations to reduce Drawdown < 5%...")
    
    res_base = simulate_portfolio(PORTFOLIO_CONFIGS, risk_per_trade=0.015, max_concurrent_indices=10)
    print(f"\n[BASE (1.5% risk, unconstrained)] Trades: {res_base['trades']} | WR: {res_base['win_rate']:.1f}% | PF: {res_base['profit_factor']:.2f} | Ret: +{res_base['ret_eur']:.2f} EUR (+{res_base['ret_pct']:.1f}%) | Max DD: {res_base['max_dd']:.2f}%")
    
    res_1pct = simulate_portfolio(PORTFOLIO_CONFIGS, risk_per_trade=0.010, max_concurrent_indices=10)
    print(f"[1.0% risk, unconstrained] Trades: {res_1pct['trades']} | WR: {res_1pct['win_rate']:.1f}% | PF: {res_1pct['profit_factor']:.2f} | Ret: +{res_1pct['ret_eur']:.2f} EUR (+{res_1pct['ret_pct']:.1f}%) | Max DD: {res_1pct['max_dd']:.2f}%")

    gold_opt_configs = {k: dict(v) for k, v in PORTFOLIO_CONFIGS.items()}
    gold_opt_configs["GOLD"]["s_start"] = 12
    gold_opt_configs["GOLD"]["s_end"] = 19
    gold_opt_configs["GOLD"]["sl"] = 12.0
    
    for r in [0.010, 0.008, 0.0075]:
        for c in [2, 3]:
            res = simulate_portfolio(gold_opt_configs, risk_per_trade=r, max_concurrent_indices=c)
            print(f"[GOLD Opt + {r*100:.2f}% risk + Max {c} indices] Trades: {res['trades']} | WR: {res['win_rate']:.1f}% | PF: {res['profit_factor']:.2f} | Ret: +{res['ret_eur']:.2f} EUR (+{res['ret_pct']:.1f}%) | Max DD: {res['max_dd']:.2f}%")

    mt5.shutdown()

if __name__ == '__main__':
    main()
