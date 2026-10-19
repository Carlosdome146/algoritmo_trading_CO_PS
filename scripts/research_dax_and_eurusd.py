import zipfile
import io
import math
import pandas as pd
import numpy as np
from trading_v2.research.regime_lab_v3 import load_long_history, add_indicators, metrics

def test_dax():
    print("=== ESTUDIO DAX 40: idx_dax_bollinger_dip ===")
    df = load_long_history('admirals_historial_largo_local.zip', 'DAX40', 'D1')
    df = add_indicators(df)
    c = df['Close']
    sma200 = df['sma200']
    rsi2 = df['rsi2']
    bb_mid = c.rolling(20).mean()
    bb_std = c.rolling(20).std(ddof=0)
    
    # Probar diferentes factores sigma: 1.5, 1.8, 2.0 y umbrales RSI: 10, 15
    for sigma in [1.5, 1.8, 2.0]:
        bb_lower = bb_mid - sigma * bb_std
        for rsi_th in [10, 15, 20]:
            trades = []
            i = 250
            n = len(df)
            o, h, l, c_arr = df['Open'].values, df['High'].values, df['Low'].values, df['Close'].values
            atr = df['atr20'].values
            idx = df.index
            spr = df['Spread'].values * 0.01

            while i < n - 1:
                cond = (c_arr[i] > sma200.iloc[i]) and (rsi2.iloc[i] < rsi_th) and (c_arr[i] <= bb_lower.iloc[i])
                if not cond or not math.isfinite(atr[i]) or atr[i] <= 0:
                    i += 1
                    continue
                k = i + 1
                entry = o[k] + spr[k] * 1.5
                stop_dist = 2.5 * atr[i]
                stop = entry - stop_dist
                exit_px, reason, j = None, 'TIME', k
                for j in range(k, min(n, k + 10)):
                    if l[j] <= stop:
                        exit_px = stop - 0.5 * spr[j]
                        reason = 'STOP'
                        break
                    if c_arr[j] > df['sma5'].iloc[j] and j + 1 < n:
                        exit_px = o[j+1] - 0.5 * spr[j+1]
                        reason = 'RULE'
                        j = j + 1
                        break
                if exit_px is None:
                    j = min(n - 1, k + 9)
                    exit_px = c_arr[j]
                pnl = exit_px - entry
                r = pnl / stop_dist
                trades.append({'entry_time': idx[k], 'r': r, 'reason': reason})
                i = j
            tdf = pd.DataFrame(trades)
            m = metrics(tdf['r'].to_numpy())
            print(f"Sigma={sigma:.1f} | RSI_th={rsi_th:<2d} | N={m['n']:<3d} | WR={m['win_rate']}% | PF={m['profit_factor']} | Mean_R={m['mean_r']:+.4f} | MaxDD={m['max_dd_r']} R")

def test_eurusd():
    print("\n=== ESTUDIO EUR/USD: Búsqueda de Alta Tasa de Acierto (>= 75%) ===")
    df = load_long_history('admirals_historial_largo_local.zip', 'EURUSD', 'D1')
    df = add_indicators(df)
    c = df['Close']
    h = df['High']
    l = df['Low']
    o = df['Open']
    atr = df['atr20']
    idx = df.index
    point = 0.00001
    
    # Costes IC Markets Raw Spread:
    # 0.1 pip spread typical + 0.05 pip slippage + $7.00/lote commission
    # En 1 lote EURUSD (100,000 EUR), $7 comisión equivale a 0.00007 / 1.10 ~ 0.64 pips ~ 6.4 puntos MT5.
    # Spread total con comisión en puntos: ~ 1 (spread) + 6.4 (comisión) + 0.5 (slip) ~ 8 puntos (0.8 pips).
    cost_pts = 8.0 * point

    bb_mid = c.rolling(20).mean()
    bb_std = c.rolling(20).std(ddof=0)

    # Probamos varias familias:
    # 1. Reversión extrema a la media en bandas de Bollinger (Long en banda inf, Short en sup)
    # 2. Reversión con filtro de tendencia (SMA 50 o 200)
    # 3. IBS extremo
    # 4. RSI(2) extremo (< 5 o > 95)
    
    print("\n--- Familia 1: RSI(2) Extremo con Filtro de Tendencia SMA (Both sides) ---")
    for sma_len in [50, 100, 200]:
        sma = df[f'sma{sma_len}']
        for rsi_th in [5, 10]:
            for max_b in [3, 5, 7]:
                trades = []
                i = 250
                n = len(df)
                while i < n - 1:
                    long_sig = (c.iloc[i] > sma.iloc[i]) and (df['rsi2'].iloc[i] < rsi_th)
                    short_sig = (c.iloc[i] < sma.iloc[i]) and (df['rsi2'].iloc[i] > (100 - rsi_th))
                    side = 1 if long_sig else (-1 if short_sig else 0)
                    if side == 0 or not math.isfinite(atr.iloc[i]) or atr.iloc[i] <= 0:
                        i += 1
                        continue
                    k = i + 1
                    entry = o.iloc[k] + side * cost_pts
                    stop_dist = 2.0 * atr.iloc[i]
                    stop = entry - side * stop_dist
                    exit_px, reason, j = None, 'TIME', k
                    for j in range(k, min(n, k + max_b)):
                        # Stop loss hit
                        if (side == 1 and l.iloc[j] <= stop) or (side == -1 and h.iloc[j] >= stop):
                            exit_px = stop - side * cost_pts * 0.5
                            reason = 'STOP'
                            break
                        # Exit rule: Close crosses SMA5
                        if side == 1 and c.iloc[j] > df['sma5'].iloc[j] and j + 1 < n:
                            exit_px = o.iloc[j+1] - cost_pts * 0.5
                            reason = 'RULE'
                            j = j + 1
                            break
                        elif side == -1 and c.iloc[j] < df['sma5'].iloc[j] and j + 1 < n:
                            exit_px = o.iloc[j+1] + cost_pts * 0.5
                            reason = 'RULE'
                            j = j + 1
                            break
                    if exit_px is None:
                        j = min(n - 1, k + max_b - 1)
                        exit_px = c.iloc[j] - side * cost_pts * 0.5
                    pnl = side * (exit_px - entry)
                    r = pnl / stop_dist
                    trades.append({'entry_time': idx[k], 'r': r, 'reason': reason})
                    i = j
                tdf = pd.DataFrame(trades)
                if len(tdf) > 10:
                    m = metrics(tdf['r'].to_numpy())
                    if m['win_rate'] >= 65:
                        print(f"SMA{sma_len:<3d} | RSI_th={rsi_th:<2d} | MaxB={max_b} | N={m['n']:<3d} | WR={m['win_rate']}% | PF={m['profit_factor']} | Mean_R={m['mean_r']:+.4f} | MaxDD={m['max_dd_r']} R")

    print("\n--- Familia 2: Bollinger 2.0 Sigma + RSI(2) Extremes (Both Sides Reversion) ---")
    for sigma in [2.0, 2.2, 2.5]:
        bb_up = bb_mid + sigma * bb_std
        bb_lo = bb_mid - sigma * bb_std
        for rsi_th in [10, 15]:
            for max_b in [3, 5, 8]:
                trades = []
                i = 250
                n = len(df)
                while i < n - 1:
                    long_sig = (c.iloc[i] <= bb_lo.iloc[i]) and (df['rsi2'].iloc[i] < rsi_th)
                    short_sig = (c.iloc[i] >= bb_up.iloc[i]) and (df['rsi2'].iloc[i] > (100 - rsi_th))
                    side = 1 if long_sig else (-1 if short_sig else 0)
                    if side == 0 or not math.isfinite(atr.iloc[i]) or atr.iloc[i] <= 0:
                        i += 1
                        continue
                    k = i + 1
                    entry = o.iloc[k] + side * cost_pts
                    stop_dist = 2.0 * atr.iloc[i]
                    stop = entry - side * stop_dist
                    exit_px, reason, j = None, 'TIME', k
                    for j in range(k, min(n, k + max_b)):
                        if (side == 1 and l.iloc[j] <= stop) or (side == -1 and h.iloc[j] >= stop):
                            exit_px = stop - side * cost_pts * 0.5
                            reason = 'STOP'
                            break
                        if side == 1 and c.iloc[j] > df['sma5'].iloc[j] and j + 1 < n:
                            exit_px = o.iloc[j+1] - cost_pts * 0.5
                            reason = 'RULE'
                            j = j + 1
                            break
                        elif side == -1 and c.iloc[j] < df['sma5'].iloc[j] and j + 1 < n:
                            exit_px = o.iloc[j+1] + cost_pts * 0.5
                            reason = 'RULE'
                            j = j + 1
                            break
                    if exit_px is None:
                        j = min(n - 1, k + max_b - 1)
                        exit_px = c.iloc[j] - side * cost_pts * 0.5
                    pnl = side * (exit_px - entry)
                    r = pnl / stop_dist
                    trades.append({'entry_time': idx[k], 'r': r, 'reason': reason})
                    i = j
                tdf = pd.DataFrame(trades)
                if len(tdf) > 5:
                    m = metrics(tdf['r'].to_numpy())
                    if m['win_rate'] >= 65:
                        print(f"BB_sigma={sigma:.1f} | RSI_th={rsi_th:<2d} | MaxB={max_b} | N={m['n']:<3d} | WR={m['win_rate']}% | PF={m['profit_factor']} | Mean_R={m['mean_r']:+.4f} | MaxDD={m['max_dd_r']} R")

    print("\n--- Familia 3: Reversión en Rango / Compresión (Kaufman Efficiency Ratio / ATR Regime) ---")
    # Kaufman Efficiency Ratio = |Close - Close[10]| / Sum(|Close[i] - Close[i-1]|, 10)
    change_10 = (c - c.shift(10)).abs()
    sum_diffs_10 = c.diff().abs().rolling(10).sum()
    ker10 = change_10 / sum_diffs_10.replace(0, np.nan)
    df['ker10'] = ker10
    
    # 3 o más cierres consecutivos bajistas / alcistas
    down3 = (c < c.shift(1)) & (c.shift(1) < c.shift(2)) & (c.shift(2) < c.shift(3))
    up3 = (c > c.shift(1)) & (c.shift(1) > c.shift(2)) & (c.shift(2) > c.shift(3))

    for ker_cap in [0.35, 0.40, 0.50]:
        for rsi_th in [5, 8, 10]:
            for exit_mode in ['sma3', 'sma5']:
                trades = []
                i = 250
                n = len(df)
                while i < n - 1:
                    is_ranging = ker10.iloc[i] < ker_cap
                    # Pullback contra la microtendencia en rango
                    long_sig = is_ranging and (df['rsi2'].iloc[i] < rsi_th) and (c.iloc[i] <= bb_lo.iloc[i] or down3.iloc[i])
                    short_sig = is_ranging and (df['rsi2'].iloc[i] > (100 - rsi_th)) and (c.iloc[i] >= bb_up.iloc[i] or up3.iloc[i])
                    side = 1 if long_sig else (-1 if short_sig else 0)
                    if side == 0 or not math.isfinite(atr.iloc[i]) or atr.iloc[i] <= 0:
                        i += 1
                        continue
                    k = i + 1
                    entry = o.iloc[k] + side * cost_pts
                    stop_dist = 2.0 * atr.iloc[i]
                    stop = entry - side * stop_dist
                    exit_px, reason, j = None, 'TIME', k
                    sma_exit = df['sma5'] if exit_mode == 'sma5' else c.rolling(3).mean()
                    for j in range(k, min(n, k + 6)):
                        if (side == 1 and l.iloc[j] <= stop) or (side == -1 and h.iloc[j] >= stop):
                            exit_px = stop - side * cost_pts * 0.5
                            reason = 'STOP'
                            break
                        if side == 1 and c.iloc[j] > sma_exit.iloc[j] and j + 1 < n:
                            exit_px = o.iloc[j+1] - cost_pts * 0.5
                            reason = 'RULE'
                            j = j + 1
                            break
                        elif side == -1 and c.iloc[j] < sma_exit.iloc[j] and j + 1 < n:
                            exit_px = o.iloc[j+1] + cost_pts * 0.5
                            reason = 'RULE'
                            j = j + 1
                            break
                    if exit_px is None:
                        j = min(n - 1, k + 5)
                        exit_px = c.iloc[j] - side * cost_pts * 0.5
                    pnl = side * (exit_px - entry)
                    r = pnl / stop_dist
                    trades.append({'entry_time': idx[k], 'r': r, 'reason': reason})
                    i = j
    print("\n--- Familia 4: Alta Precisión EUR/USD: KER + BB + RSI(2) + Stop 2.5 ATR ---")
    for ker_cap in [0.35, 0.40, 0.45]:
        for rsi_th in [5, 8, 10]:
            for stop_atr in [2.0, 2.5, 3.0]:
                for exit_rule in ['sma5', 'bb_mid']:
                    trades = []
                    i = 250
                    n = len(df)
                    while i < n - 1:
                        is_ranging = ker10.iloc[i] < ker_cap
                        long_sig = is_ranging and (df['rsi2'].iloc[i] < rsi_th) and (c.iloc[i] <= bb_lo.iloc[i])
                        short_sig = is_ranging and (df['rsi2'].iloc[i] > (100 - rsi_th)) and (c.iloc[i] >= bb_up.iloc[i])
                        side = 1 if long_sig else (-1 if short_sig else 0)
                        if side == 0 or not math.isfinite(atr.iloc[i]) or atr.iloc[i] <= 0:
                            i += 1
                            continue
                        k = i + 1
                        entry = o.iloc[k] + side * cost_pts
                        stop_dist = stop_atr * atr.iloc[i]
                        stop = entry - side * stop_dist
                        exit_px, reason, j = None, 'TIME', k
                        target_exit = df['sma5'] if exit_rule == 'sma5' else bb_mid
                        for j in range(k, min(n, k + 8)):
                            if (side == 1 and l.iloc[j] <= stop) or (side == -1 and h.iloc[j] >= stop):
                                exit_px = stop - side * cost_pts * 0.5
                                reason = 'STOP'
                                break
                            if side == 1 and c.iloc[j] > target_exit.iloc[j] and j + 1 < n:
                                exit_px = o.iloc[j+1] - cost_pts * 0.5
                                reason = 'RULE'
                                j = j + 1
                                break
                            elif side == -1 and c.iloc[j] < target_exit.iloc[j] and j + 1 < n:
                                exit_px = o.iloc[j+1] + cost_pts * 0.5
                                reason = 'RULE'
                                j = j + 1
                                break
                        if exit_px is None:
                            j = min(n - 1, k + 7)
                            exit_px = c.iloc[j] - side * cost_pts * 0.5
                        pnl = side * (exit_px - entry)
                        r = pnl / stop_dist
                        trades.append({'entry_time': idx[k], 'r': r, 'reason': reason})
                        i = j
                    tdf = pd.DataFrame(trades)
                    if len(tdf) >= 15:
                        m = metrics(tdf['r'].to_numpy())
                        if m['win_rate'] >= 75:
                            print(f"KER<{ker_cap:.2f} | RSI<{rsi_th} | Stop={stop_atr} ATR | Exit={exit_rule} | N={m['n']:<3d} | WR={m['win_rate']}% | PF={m['profit_factor']} | Mean_R={m['mean_r']:+.4f} | MaxDD={m['max_dd_r']} R")



if __name__ == "__main__":
    test_dax()
    test_eurusd()

