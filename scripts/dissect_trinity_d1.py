"""Dissección estadística rigurosa de la Trinidad de Activos en D1."""
from __future__ import annotations

import numpy as np
import pandas as pd
from trading_v2.research.regime_lab_v3 import load_long_history, add_indicators, metrics


def main():
    print("=" * 85)
    print("DISSECCIÓN DE LA TRINIDAD DE ACTIVOS EN D1 (ALTA TASA + ALTO PROFIT FACTOR)")
    print("=" * 85)

    # 1. DAX 40
    df = load_long_history('admirals_historial_largo_local.zip', 'DAX40', 'D1')
    df = add_indicators(df)
    c, h, l, o = df['Close'].values, df['High'].values, df['Low'].values, df['Open'].values
    atr = df['atr20'].values
    sma200 = df['sma200']
    rsi2 = df['rsi2']
    bb_mid = df['Close'].rolling(20).mean().values
    bb_lo = bb_mid - 1.8 * df['Close'].rolling(20).std(ddof=0).values
    sma5 = df['sma5'].values
    spr = df['Spread'].values * 0.01

    trades_dax = []
    i = 250
    n = len(df)
    while i < n - 1:
        if (c[i] > sma200.iloc[i]) and (rsi2.iloc[i] < 15) and (c[i] <= bb_lo[i]) and atr[i] > 0:
            k = i + 1
            entry = o[k] + spr[k] * 1.5
            stop = entry - 2.5 * atr[i]
            exit_px, reason, j = None, 'TIME', k
            for j in range(k, min(n, k + 10)):
                if l[j] <= stop:
                    exit_px = stop - 0.5 * spr[j]
                    reason = 'STOP'
                    break
                if c[j] > sma5[j] and j + 1 < n:
                    exit_px = o[j+1] - 0.5 * spr[j+1]
                    reason = 'RULE'
                    j = j + 1
                    break
            if exit_px is None:
                j = min(n - 1, k + 9)
                exit_px = c[j]
            r = (exit_px - entry) / (2.5 * atr[i])
            trades_dax.append({'r': r, 'won': r > 0, 'reason': reason, 'bars': j - k})
            i = j
        else:
            i += 1

    tdax = pd.DataFrame(trades_dax)
    m_dax = metrics(tdax['r'].to_numpy())
    r_win = tdax[tdax['r'] > 0]['r'].mean()
    r_loss = tdax[tdax['r'] <= 0]['r'].mean()
    print(f"DAX 40 (D1 Dip):   N={m_dax['n']:<3d} | WR={m_dax['win_rate']:5.1f}% | PF={m_dax['profit_factor']:5.2f} | E[R]={m_dax['mean_r']:+.4f} | R_win={r_win:+.4f} | R_loss={r_loss:+.4f}")

    # 2. SP500
    df_sp = load_long_history('admirals_historial_largo_local.zip', 'SP500', 'D1')
    df_sp = add_indicators(df_sp)
    c, h, l, o = df_sp['Close'].values, df_sp['High'].values, df_sp['Low'].values, df_sp['Open'].values
    atr = df_sp['atr20'].values
    sma200 = df_sp['sma200']
    rsi2 = df_sp['rsi2']
    sma5 = df_sp['sma5'].values
    spr = df_sp['Spread'].values * 0.01

    trades_sp = []
    i = 250
    n = len(df_sp)
    while i < n - 1:
        if (c[i] > sma200.iloc[i]) and (rsi2.iloc[i] < 8) and atr[i] > 0:
            k = i + 1
            entry = o[k] + spr[k] * 1.5
            stop = entry - 2.5 * atr[i]
            exit_px, reason, j = None, 'TIME', k
            for j in range(k, min(n, k + 10)):
                if l[j] <= stop:
                    exit_px = stop - 0.5 * spr[j]
                    reason = 'STOP'
                    break
                if c[j] > sma5[j] and j + 1 < n:
                    exit_px = o[j+1] - 0.5 * spr[j+1]
                    reason = 'RULE'
                    j = j + 1
                    break
            if exit_px is None:
                j = min(n - 1, k + 9)
                exit_px = c[j]
            r = (exit_px - entry) / (2.5 * atr[i])
            trades_sp.append({'r': r, 'won': r > 0, 'reason': reason, 'bars': j - k})
            i = j
        else:
            i += 1

    tsp = pd.DataFrame(trades_sp)
    m_sp = metrics(tsp['r'].to_numpy())
    r_win = tsp[tsp['r'] > 0]['r'].mean()
    r_loss = tsp[tsp['r'] <= 0]['r'].mean()
    print(f"S&P 500 (D1 Dip):  N={m_sp['n']:<3d} | WR={m_sp['win_rate']:5.1f}% | PF={m_sp['profit_factor']:5.2f} | E[R]={m_sp['mean_r']:+.4f} | R_win={r_win:+.4f} | R_loss={r_loss:+.4f}")

    # 3. EURUSD
    df_eu = load_long_history('admirals_historial_largo_local.zip', 'EURUSD', 'D1')
    df_eu = add_indicators(df_eu)
    c_s = df_eu['Close']
    change_10 = (c_s - c_s.shift(10)).abs()
    sum_diffs_10 = c_s.diff().abs().rolling(10).sum()
    ker10 = change_10 / sum_diffs_10.replace(0, np.nan)
    c, h, l, o = df_eu['Close'].values, df_eu['High'].values, df_eu['Low'].values, df_eu['Open'].values
    atr = df_eu['atr20'].values
    rsi2 = df_eu['rsi2']
    sma5 = df_eu['sma5'].values
    sma20 = df_eu['Close'].rolling(20).mean().values
    std20 = df_eu['Close'].rolling(20).std(ddof=0).values
    bb_lo = sma20 - 2.0 * std20
    bb_up = sma20 + 2.0 * std20
    cost_pts = 8.0 * 0.00001

    trades_eu = []
    i = 250
    n = len(df_eu)
    while i < n - 1:
        is_ranging = ker10.iloc[i] < 0.40
        long_sig = is_ranging and (rsi2.iloc[i] < 8) and (c[i] <= bb_lo[i])
        short_sig = is_ranging and (rsi2.iloc[i] > 92) and (c[i] >= bb_up[i])
        side = 1 if long_sig else (-1 if short_sig else 0)
        if side != 0 and atr[i] > 0:
            k = i + 1
            entry = o[k] + side * cost_pts
            stop = entry - side * (2.0 * atr[i])
            exit_px, reason, j = None, 'TIME', k
            for j in range(k, min(n, k + 8)):
                if (side == 1 and l[j] <= stop) or (side == -1 and h[j] >= stop):
                    exit_px = stop - side * cost_pts * 0.5
                    reason = 'STOP'
                    break
                if side == 1 and c[j] > sma5[j] and j + 1 < n:
                    exit_px = o[j+1] - cost_pts * 0.5
                    reason = 'RULE'
                    j = j + 1
                    break
                elif side == -1 and c[j] < sma5[j] and j + 1 < n:
                    exit_px = o[j+1] + cost_pts * 0.5
                    reason = 'RULE'
                    j = j + 1
                    break
            if exit_px is None:
                j = min(n - 1, k + 7)
                exit_px = c[j] - side * cost_pts * 0.5
            r = side * (exit_px - entry) / (2.0 * atr[i])
            trades_eu.append({'r': r, 'won': r > 0, 'reason': reason, 'bars': j - k})
            i = j
        else:
            i += 1

    teu = pd.DataFrame(trades_eu)
    m_eu = metrics(teu['r'].to_numpy())
    r_win = teu[teu['r'] > 0]['r'].mean()
    r_loss = teu[teu['r'] <= 0]['r'].mean()
    print(f"EUR/USD (D1 KER):  N={m_eu['n']:<3d} | WR={m_eu['win_rate']:5.1f}% | PF={m_eu['profit_factor']:5.2f} | E[R]={m_eu['mean_r']:+.4f} | R_win={r_win:+.4f} | R_loss={r_loss:+.4f}")
    print("=" * 85)


if __name__ == "__main__":
    main()
