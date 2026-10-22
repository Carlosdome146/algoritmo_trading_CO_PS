"""Test H1-anchored M15/M30 precision model across the Trinidad of 3 assets."""
from __future__ import annotations

import math
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

from trading_v2.research.regime_lab_v3 import metrics


def run_test():
    if not mt5.initialize():
        print("MT5 no disponible")
        return

    for sym in ["GERMANY40", "[SP500]", "EURUSD"]:
        r15 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 30000)
        df15 = pd.DataFrame(r15)
        df15["time"] = pd.to_datetime(df15["time"], unit="s", utc=True)
        df15.set_index("time", inplace=True)
        
        # H1 trend
        rh1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 5000)
        dfh1 = pd.DataFrame(rh1)
        dfh1["time"] = pd.to_datetime(dfh1["time"], unit="s", utc=True)
        dfh1.set_index("time", inplace=True)
        dfh1["ema20"] = dfh1["close"].ewm(span=20, adjust=False).mean()
        dfh1["ema50"] = dfh1["close"].ewm(span=50, adjust=False).mean()
        dfh1["sma200"] = dfh1["close"].rolling(200, min_periods=50).mean()
        dfh1["h1_trend"] = np.where(
            (dfh1["close"] > dfh1["sma200"]) & (dfh1["ema20"] > dfh1["ema50"]), 1,
            np.where((dfh1["close"] < dfh1["sma200"]) & (dfh1["ema20"] < dfh1["ema50"]), -1, 0)
        )
        dfh1["close_time"] = dfh1.index + pd.Timedelta(hours=1)
        
        m15_times = pd.DataFrame({"m15_time": df15.index + pd.Timedelta(minutes=15), "idx": np.arange(len(df15))})
        aligned = pd.merge_asof(
            m15_times.sort_values("m15_time"),
            dfh1[["close_time", "h1_trend"]].sort_values("close_time"),
            left_on="m15_time",
            right_on="close_time",
            direction="backward"
        ).sort_values("idx")
        df15["h1_trend"] = aligned["h1_trend"].fillna(0).to_numpy()
        
        c, h, l, o = df15["close"], df15["high"], df15["low"], df15["open"]
        tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14, min_periods=5).mean().to_numpy()
        
        delta = c.diff()
        up = delta.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
        dn = (-delta.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
        rsi2 = (100 - 100 / (1 + up / dn.replace(0, np.nan))).to_numpy()
        
        sma20 = c.rolling(20, min_periods=10).mean()
        std20 = c.rolling(20, min_periods=10).std(ddof=0)
        bb_lo = (sma20 - 2.0 * std20).to_numpy()
        bb_up = (sma20 + 2.0 * std20).to_numpy()
        
        rng = (h - l).replace(0, np.nan)
        lower_wick = ((np.minimum(o, c) - l) / rng).fillna(0.0).to_numpy()
        upper_wick = ((h - np.maximum(o, c)) / rng).fillna(0.0).to_numpy()
        
        hours = df15.index.hour.to_numpy()
        point = 0.01 if ("GERMANY" in sym or "SP500" in sym) else 0.00001
        comm = 0.00007 if sym == "EURUSD" else 0.0
        spr_arr = df15["spread"].to_numpy()
        c_arr, o_arr, h_arr, l_arr = c.to_numpy(), o.to_numpy(), h.to_numpy(), l.to_numpy()
        h1_tr = df15["h1_trend"].to_numpy()
        n = len(df15)
        
        s_start, s_end = (7, 16) if "GERMANY" in sym else ((13, 20) if "SP500" in sym else (7, 16))
        
        print(f"\n=== RESULTADOS {sym} CON H1 ANCHOR ===")
        found = 0
        for rsi_cut in [5, 10, 15]:
            for tp_atr in [0.4, 0.5, 0.7, 1.0]:
                for sl_atr in [0.8, 1.0, 1.2, 1.5]:
                    for be_trigger in [0.25, 0.35, 0.5, None]:
                        trades = []
                        i = 50
                        while i < n - 1:
                            if not (s_start <= hours[i] <= s_end):
                                i += 1
                                continue
                            cur_atr = atr[i]
                            if not math.isfinite(cur_atr) or cur_atr <= 0:
                                i += 1
                                continue
                                
                            buy = (h1_tr[i] == 1) and (rsi2[i] < rsi_cut) and (c_arr[i] <= bb_lo[i] or lower_wick[i] >= 0.35)
                            sell = (h1_tr[i] == -1) and (rsi2[i] > (100 - rsi_cut)) and (c_arr[i] >= bb_up[i] or upper_wick[i] >= 0.35)
                            side = 1 if buy else (-1 if sell else 0)
                            if side == 0:
                                i += 1
                                continue
                                
                            k = i + 1
                            entry = o_arr[k] + side * (spr_arr[k] * point / 2.0)
                            tp = entry + side * (tp_atr * cur_atr)
                            sl = entry - side * (sl_atr * cur_atr)
                            be_active = False
                            exit_px = None
                            
                            for j in range(k, min(n, k + 12)):
                                hit_sl = (l_arr[j] <= sl) if side == 1 else (h_arr[j] >= sl)
                                hit_tp = (h_arr[j] >= tp) if side == 1 else (l_arr[j] <= tp)
                                if hit_sl and hit_tp:
                                    exit_px = sl
                                    break
                                elif hit_sl:
                                    exit_px = sl
                                    break
                                elif hit_tp:
                                    exit_px = tp
                                    break
                                    
                                if be_trigger and not be_active:
                                    unrl = side * (c_arr[j] - entry)
                                    if unrl >= be_trigger * cur_atr:
                                        be_active = True
                                        sl = entry + side * (0.05 * cur_atr)
                                        
                            if exit_px is None:
                                j = min(n - 1, k + 11)
                                exit_px = c_arr[j] - side * (spr_arr[j] * point / 2.0)
                                
                            net = side * (exit_px - entry) - comm
                            r_val = net / (sl_atr * cur_atr)
                            trades.append(r_val)
                            i = j + 1
                            
                        if len(trades) >= 20:
                            m = metrics(np.array(trades))
                            if m["win_rate"] >= 65.0:
                                found += 1
                                be_str = f"{be_trigger}" if be_trigger else "None"
                                star = " [*** TOP ***]" if m["win_rate"] >= 75.0 and m["profit_factor"] >= 1.15 else (" [*]" if m["win_rate"] >= 70.0 else "")
                                print(f"RSI<{rsi_cut:<2d} | TP={tp_atr:.1f} | SL={sl_atr:.1f} | BE={be_str:<5s} | N={m['n']:<4d} | WR={m['win_rate']:5.1f}% | PF={m['profit_factor']:5.2f} | R={m['mean_r']:+7.4f}{star}")
        if found == 0:
            print("Ninguna combinación superó el 65% de win rate en este activo.")

    mt5.shutdown()


if __name__ == "__main__":
    run_test()
