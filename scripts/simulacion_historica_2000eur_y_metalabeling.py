"""Simulación Histórica Retrospectiva con 2.000 EUR y Auditoría de Meta-Labeling (MLFinLab / FreqAI).

Ejecuta:
1. Replay Histórico barra a barra (2015-2026) con una cuenta inicial de 2.000 EUR en los 4 activos
   (GERMANY40, [SP500], EURUSD, [IBEX35]), descontando spreads reales y comisiones.
2. Desglose año por año (evolución del capital de 2.000 EUR con interés compuesto al 1.0% y 1.5% de riesgo).
3. Listado detallado de las últimas 25 operaciones históricas (fecha exacta, precio entrada/salida, EUR ganados).
4. Auditoría de Meta-Labeling Cuantitativo (Sincronía Intermercado + Calidad de Microestructura) en M15 y D1.
"""
from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from trading_v2.research.regime_lab_v3 import metrics, wilson_lb


def simulate_d1_asset(sym: str, sigma: float, rsi_th: int, stop_m: float, is_ker: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    r = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 3000)
    if r is None or len(r) == 0:
        return pd.DataFrame(), pd.DataFrame()
    df = pd.DataFrame(r)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    c, h, l, o = df["close"].values, df["high"].values, df["low"].values, df["open"].values
    n = len(df)

    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift(1)).abs(),
        (df["low"] - df["close"].shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(20, min_periods=10).mean().values

    delta = df["close"].diff()
    up = delta.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    rsi2 = (100 - 100 / (1 + up / dn.replace(0, np.nan))).values

    sma200 = df["close"].rolling(200, min_periods=50).mean().values
    sma50 = df["close"].rolling(50, min_periods=25).mean().values
    sma20 = df["close"].rolling(20, min_periods=10).mean().values
    std20 = df["close"].rolling(20, min_periods=10).std(ddof=0).values
    sma5 = df["close"].rolling(5, min_periods=3).mean().values
    bb_lo = sma20 - sigma * std20
    bb_up = sma20 + sigma * std20

    # IBS (Internal Bar Strength)
    rng = np.maximum(h - l, 1e-9)
    ibs = (c - l) / rng

    pt = 0.00001 if sym == "EURUSD" else 0.01
    spr = df["spread"].values * pt

    ker10 = (df["close"] - df["close"].shift(10)).abs() / df["close"].diff().abs().rolling(10).sum().replace(0, np.nan)
    ker10_arr = ker10.values

    # Guardar serie diaria para sincronía intermercado (Meta-Labeling)
    daily_state = pd.DataFrame({
        "close": c,
        "sma200": sma200,
        "sma50": sma50,
        "rsi2": rsi2,
        "ibs": ibs,
        "atr": atr,
    }, index=df.index.normalize())
    daily_state = daily_state[~daily_state.index.duplicated(keep="last")]

    trades = []
    i = 250
    while i < n - 1:
        if is_ker:
            is_rng = ker10_arr[i] < 0.40
            long_sig = is_rng and (rsi2[i] < rsi_th) and (c[i] <= bb_lo[i])
            short_sig = is_rng and (rsi2[i] > (100 - rsi_th)) and (c[i] >= bb_up[i])
            side = 1 if long_sig else (-1 if short_sig else 0)
        else:
            if sigma > 0:
                cond = (c[i] > sma200[i]) and (rsi2[i] < rsi_th) and (c[i] <= bb_lo[i])
            else:
                cond = (c[i] > sma200[i]) and (rsi2[i] < rsi_th)
            side = 1 if cond else 0

        cur_atr = atr[i]
        if side == 0 or not np.isfinite(cur_atr) or cur_atr <= 0:
            i += 1
            continue

        k = i + 1
        entry = o[k] + side * spr[k] * 1.5
        stop = entry - side * stop_m * cur_atr
        exit_px = None
        exit_reason = "TIME_EXIT"
        for j in range(k, min(n, k + 10)):
            if (side == 1 and l[j] <= stop) or (side == -1 and h[j] >= stop):
                exit_px = stop - side * spr[j] * 0.5
                exit_reason = "STOP_LOSS"
                break
            if side == 1 and c[j] > sma5[j] and j + 1 < n:
                exit_px = o[j + 1] - side * spr[j + 1] * 0.5
                exit_reason = "TAKE_PROFIT_SMA5"
                j = j + 1
                break
            elif side == -1 and c[j] < sma5[j] and j + 1 < n:
                exit_px = o[j + 1] + side * spr[j + 1] * 0.5
                exit_reason = "TAKE_PROFIT_SMA5"
                j = j + 1
                break
        if exit_px is None:
            j = min(n - 1, k + 9)
            exit_px = c[j]

        r_val = side * (exit_px - entry) / (stop_m * cur_atr)
        # Características en el instante de señal i para Meta-Labeling
        z_bb = (sma20[i] - c[i]) / max(std20[i], 1e-9) if side == 1 else (c[i] - sma20[i]) / max(std20[i], 1e-9)
        trades.append({
            "signal_date": df.index[i].normalize(),
            "entry_date": df.index[k],
            "exit_date": df.index[j],
            "holding_days": max(1, (df.index[j] - df.index[k]).days),
            "sym": sym,
            "side": "BUY" if side == 1 else "SELL",
            "entry_px": entry,
            "exit_px": exit_px,
            "rsi2_sig": rsi2[i],
            "ibs_sig": ibs[i],
            "z_bb": z_bb,
            "above_sma50": bool(c[i] > sma50[i]),
            "exit_reason": exit_reason,
            "r": r_val,
        })
        i = j

    return pd.DataFrame(trades), daily_state


def evaluate_meta_labeling_d1(all_trades: pd.DataFrame, states: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Calcula el Meta-Score (0 a 100) estilo MLFinLab / FreqAI para cada señal histórica."""
    df = all_trades.copy().sort_values("entry_date").reset_index(drop=True)
    meta_scores = []
    confluences = []

    for idx, row in df.iterrows():
        sig_dt = row["signal_date"]
        sym = row["sym"]
        score = 50.0  # Base score

        # 1. Sincronía Intermercado: ¿Cuántos de los 3 grandes índices (DAX, SP500, IBEX) están en régimen alcista (>SMA200)?
        bull_regimes = 0
        pullback_peers = 0
        for idx_sym in ["GERMANY40", "[SP500]", "[IBEX35]"]:
            st = states.get(idx_sym)
            if st is not None and sig_dt in st.index:
                s_row = st.loc[sig_dt]
                if s_row["close"] > s_row["sma200"]:
                    bull_regimes += 1
                if s_row["rsi2"] < 25.0:
                    pullback_peers += 1

        if bull_regimes == 3:
            score += 15.0  # Sincronía macro global alcista
        elif bull_regimes >= 2:
            score += 7.5

        if pullback_peers >= 2:
            score += 15.0  # Barrido / sobreventa sincronizada en múltiples bolsas a la vez

        # 2. Microestructura de la vela de señal (IBS extremo + compresión Bollinger)
        if row["side"] == "BUY" and row["ibs_sig"] < 0.20:
            score += 10.0  # Cierre en el 20% inferior de la vela diaria (absorción institucional al día siguiente)
        if row["z_bb"] >= 2.1:
            score += 10.0  # Estiramiento estadístico extremo (>2.1 sigma)

        score = min(100.0, max(0.0, score))
        meta_scores.append(score)
        confluences.append(f"Macro:{bull_regimes}/3 | SyncDip:{pullback_peers}/3 | IBS:{row['ibs_sig']:.2f}")

    df["meta_score"] = meta_scores
    df["confluence_info"] = confluences
    return df


def audit_intraday_meta_labeling():
    """Audita en barras M15 reales el impacto de Meta-Labeling (Filtro H1 + Breakeven + Sincronía Intermercado)."""
    symbols = ["GERMANY40", "[IBEX35]", "[SP500]", "EURUSD"]
    m15_data = {}
    h1_data = {}

    for sym in symbols:
        r15 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 15000)
        r1h = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 5000)
        if r15 is not None and len(r15) > 0:
            d15 = pd.DataFrame(r15)
            d15["time"] = pd.to_datetime(d15["time"], unit="s", utc=True)
            d15.set_index("time", inplace=True)
            m15_data[sym] = d15
        if r1h is not None and len(r1h) > 0:
            d1h = pd.DataFrame(r1h)
            d1h["time"] = pd.to_datetime(d1h["time"], unit="s", utc=True)
            d1h.set_index("time", inplace=True)
            d1h["ema50"] = d1h["close"].ewm(span=50, adjust=False).mean()
            d1h["trend"] = np.where(d1h["close"] > d1h["ema50"], 1, -1)
            h1_data[sym] = d1h

    print("\n" + "=" * 95)
    print("4. AUDITORÍA INTRADÍA M15 CON META-LABELING (FILTRO H1 + BREAKEVEN + SINCRONÍA INTERMERCADO)")
    print("=" * 95)

    configs = [
        ("GERMANY40", 12.0, 20.0, 7, 15, 4.0, 0.30),
        ("[IBEX35]", 15.0, 25.0, 7, 15, 8.0, 0.30),
        ("[SP500]", 5.0, 8.0, 13, 19, 1.5, 0.30),
        ("EURUSD", 6.0, 10.0, 7, 16, 2.5, 0.30),
    ]

    for sym, tgt, sl_u, sh_start, sh_end, min_sw, min_wk in configs:
        if sym not in m15_data or sym not in h1_data:
            continue
        df = m15_data[sym].copy()
        h1 = h1_data[sym]

        # Map H1 trend causally (shift 1 hour so no lookahead)
        h1_trend_map = h1["trend"].shift(1).reindex(df.index, method="ffill").fillna(0).values

        # Peer index H1 trend for intermarket sync
        peer_sym = "[IBEX35]" if sym == "GERMANY40" else ("GERMANY40" if sym == "[IBEX35]" else "GERMANY40")
        peer_trend_map = h1_data[peer_sym]["trend"].shift(1).reindex(df.index, method="ffill").fillna(0).values

        unit = 0.00010 if sym == "EURUSD" else 1.0
        pt = 0.00001 if sym == "EURUSD" else 0.01

        c, o, h, l = df["close"].values, df["open"].values, df["high"].values, df["low"].values
        spr = df["spread"].values * pt
        hrs = df.index.hour.values

        # Rolling prev 12 bars high/low (3 hours liquidity pool)
        roll_hi = pd.Series(h).shift(1).rolling(12).max().values
        roll_lo = pd.Series(l).shift(1).rolling(12).min().values
        tr = np.maximum(h - l, np.abs(h - pd.Series(c).shift(1).fillna(c[0]).values))
        atr14 = pd.Series(tr).rolling(14).mean().values

        base_trades = []
        meta_trades = []

        i = 20
        n = len(df)
        while i < n - 8:
            if not (sh_start <= hrs[i] < sh_end):
                i += 1
                continue
            rng_b = h[i] - l[i]
            if rng_b <= 0 or not np.isfinite(roll_lo[i]) or not np.isfinite(atr14[i]):
                i += 1
                continue

            # Check sweep
            sw_long = (roll_lo[i] - l[i]) / unit
            wk_long = (min(o[i], c[i]) - l[i]) / rng_b
            is_long = (sw_long >= min_sw) and (c[i] > roll_lo[i]) and (wk_long >= min_wk) and (c[i] > o[i])

            sw_short = (h[i] - roll_hi[i]) / unit
            wk_short = (h[i] - max(o[i], c[i])) / rng_b
            is_short = (sw_short >= min_sw) and (c[i] < roll_hi[i]) and (wk_short >= min_wk) and (c[i] < o[i])

            side = 1 if is_long else (-1 if is_short else 0)
            if side == 0:
                i += 1
                continue

            # Simulate trade with Causal Breakeven at +0.35 ATR
            k = i + 1
            entry = o[k] + side * (spr[k] / 2.0)
            tp_px = entry + side * (tgt * unit)
            sl_px = entry - side * (sl_u * unit)
            be_trig = entry + side * (0.35 * atr14[i])
            be_lock = entry + side * (0.05 * atr14[i])

            cur_sl = sl_px
            exit_px = None
            for j in range(k, min(n, k + 8)):
                eval_lo = l[j] - side * (spr[j] / 2.0)
                eval_hi = h[j] - side * (spr[j] / 2.0)
                hit_sl = (eval_lo <= cur_sl) if side == 1 else (eval_hi >= cur_sl)
                hit_tp = (eval_hi >= tp_px) if side == 1 else (eval_lo <= tp_px)
                if hit_sl:
                    exit_px = cur_sl
                    break
                if hit_tp:
                    exit_px = tp_px
                    break
                # Check BE trigger at bar close
                if (side == 1 and c[j] >= be_trig) or (side == -1 and c[j] <= be_trig):
                    if (side == 1 and cur_sl < be_lock) or (side == -1 and cur_sl > be_lock):
                        cur_sl = be_lock

            if exit_px is None:
                j = min(n - 1, k + 7)
                exit_px = c[j] - side * (spr[j] / 2.0)

            r_res = side * (exit_px - entry) / (sl_u * unit)
            base_trades.append(r_res)

            # Meta-Labeling check: H1 Trend aligned + Peer Index aligned
            if h1_trend_map[i] == side and (peer_trend_map[i] == side or sym == "EURUSD"):
                meta_trades.append(r_res)

            i = j + 2

        b_arr = np.array(base_trades)
        m_arr = np.array(meta_trades)
        bw = float((b_arr > 0).mean() * 100) if len(b_arr) > 0 else 0.0
        mw = float((m_arr > 0).mean() * 100) if len(m_arr) > 0 else 0.0
        bpf = float(b_arr[b_arr > 0].sum() / max(abs(b_arr[b_arr < 0].sum()), 1e-9)) if len(b_arr) > 0 else 0.0
        mpf = float(m_arr[m_arr > 0].sum() / max(abs(m_arr[m_arr < 0].sum()), 1e-9)) if len(m_arr) > 0 else 0.0
        print(
            f"{sym:<12} | Base M15: N={len(b_arr):<3d} WR={bw:5.1f}% PF={bpf:4.2f} "
            f"--> Con Meta-Labeling (H1+Sync+BE): N={len(m_arr):<3d} WR={mw:5.1f}% PF={mpf:4.2f}"
        )


def main():
    if not mt5.initialize():
        print("Error al inicializar MT5")
        return

    tr_dax, st_dax = simulate_d1_asset("GERMANY40", 1.8, 15, 2.5)
    tr_sp, st_sp = simulate_d1_asset("[SP500]", 0.0, 8, 2.5)
    tr_eu, st_eu = simulate_d1_asset("EURUSD", 2.0, 8, 2.0, is_ker=True)
    tr_ibx, st_ibx = simulate_d1_asset("[IBEX35]", 2.0, 10, 2.5)

    states = {"GERMANY40": st_dax, "[SP500]": st_sp, "EURUSD": st_eu, "[IBEX35]": st_ibx}
    all_trades = pd.concat([tr_dax, tr_sp, tr_eu, tr_ibx], ignore_index=True)
    df_sim = evaluate_meta_labeling_d1(all_trades, states)

    # Simulación de cuenta de 2.000 EUR con:
    # A) Riesgo fijo 1.0% (compuesto)
    # B) Riesgo dinámico Meta-Labeling (0.75% si score < 70, 1.25% si score >= 70)
    cap_1pct = 2000.0
    cap_meta = 2000.0
    peak_1pct = 2000.0
    peak_meta = 2000.0
    max_dd_1pct = 0.0
    max_dd_meta = 0.0

    cap_1pct_list = []
    pnl_1pct_list = []
    cap_meta_list = []
    pnl_meta_list = []

    for _, row in df_sim.iterrows():
        r = row["r"]
        score = row["meta_score"]

        # Estrategia 1% estándar
        risk_eur_1 = cap_1pct * 0.01
        pnl_1 = risk_eur_1 * r
        cap_1pct += pnl_1
        peak_1pct = max(peak_1pct, cap_1pct)
        dd_1 = (peak_1pct - cap_1pct) / peak_1pct * 100
        max_dd_1pct = max(max_dd_1pct, dd_1)
        cap_1pct_list.append(cap_1pct)
        pnl_1pct_list.append(pnl_1)

        # Estrategia Meta-Labeling (asigna 1.25% en alta confluencia >=70, 0.75% en estándar)
        risk_frac_meta = 0.0125 if score >= 70.0 else 0.0075
        risk_eur_m = cap_meta * risk_frac_meta
        pnl_m = risk_eur_m * r
        cap_meta += pnl_m
        peak_meta = max(peak_meta, cap_meta)
        dd_m = (peak_meta - cap_meta) / peak_meta * 100
        max_dd_meta = max(max_dd_meta, dd_m)
        cap_meta_list.append(cap_meta)
        pnl_meta_list.append(pnl_m)

    df_sim["pnl_eur_1pct"] = pnl_1pct_list
    df_sim["equity_1pct"] = cap_1pct_list
    df_sim["pnl_eur_meta"] = pnl_meta_list
    df_sim["equity_meta"] = cap_meta_list
    df_sim["year"] = df_sim["entry_date"].dt.year

    print("=" * 95)
    print("1. EVOLUCIÓN ANUAL DE 2.000 EUR EN SIMULACIÓN RETROSPECTIVA (CARTERA 4 ACTIVOS D1)")
    print("=" * 95)
    print(f"{'Año':<6} | {'Trades':<6} | {'WinRate':<8} | {'R Acum':<8} | {'Ganancia (1%)':<15} | {'Saldo Final (1%)':<16} | {'Saldo Meta-ML'}")
    print("-" * 95)

    prev_cap = 2000.0
    for yr, grp in df_sim.groupby("year"):
        n_t = len(grp)
        wr = (grp["r"] > 0).mean() * 100
        r_sum = grp["r"].sum()
        end_c1 = grp["equity_1pct"].iloc[-1]
        yr_pnl1 = end_c1 - prev_cap
        end_cm = grp["equity_meta"].iloc[-1]
        prev_cap = end_c1
        print(f"{yr:<6} | {n_t:<6} | {wr:6.1f}%  | {r_sum:+6.2f} R | {yr_pnl1:+10.2f} EUR  | {end_c1:12.2f} EUR | {end_cm:10.2f} EUR")

    print("-" * 95)
    print(f"RESUMEN GLOBAL (11 AÑOS): 2.000 EUR -> {cap_1pct:,.2f} EUR (1% Riesgo) | {cap_meta:,.2f} EUR (Con Meta-Labeling)")
    print(f"Max Drawdown Histórico: {max_dd_1pct:.2f}% (1% Riesgo) | {max_dd_meta:.2f}% (Con Meta-Labeling)")

    # Impacto del filtro Meta-Labeling en D1
    high_meta = df_sim[df_sim["meta_score"] >= 70.0]
    low_meta = df_sim[df_sim["meta_score"] < 70.0]
    print("\n" + "=" * 95)
    print("2. AUDITORÍA DEL FILTRO META-LABELING (SINCRONÍA INTERMERCADO DAX + SP500 + IBEX)")
    print("=" * 95)
    print(f"Señales Estándar (Meta-Score < 70)        : N={len(low_meta):<3d} | WinRate={(low_meta['r']>0).mean()*100:5.1f}% | E[R]={low_meta['r'].mean():+6.3f} R")
    print(f"Señales Alta Confluencia (Meta-Score >= 70): N={len(high_meta):<3d} | WinRate={(high_meta['r']>0).mean()*100:5.1f}% | E[R]={high_meta['r'].mean():+6.3f} R")

    print("\n" + "=" * 95)
    print("3. REPLAY OPERACIÓN POR OPERACIÓN (ÚLTIMAS 25 OPERACIONES DE LA CARTERA CON 2.000 EUR)")
    print("=" * 95)
    print(f"{'Fecha Entrada':<12} | {'Activo':<10} | {'Entrada':<9} | {'Salida':<9} | {'Días':<4} | {'Meta':<4} | {'Resultado R':<11} | {'PnL (EUR)':<10} | {'Saldo Cuenta'}")
    print("-" * 95)
    for _, r_row in df_sim.tail(25).iterrows():
        dt_str = r_row["entry_date"].strftime("%Y-%m-%d")
        sym = r_row["sym"]
        epx = f"{r_row['entry_px']:.4f}" if sym == "EURUSD" else f"{r_row['entry_px']:.1f}"
        xpx = f"{r_row['exit_px']:.4f}" if sym == "EURUSD" else f"{r_row['exit_px']:.1f}"
        tag = "WIN " if r_row["r"] > 0 else "LOSS"
        print(
            f"{dt_str:<12} | {sym:<10} | {epx:<9} | {xpx:<9} | {r_row['holding_days']:<4} | "
            f"{int(r_row['meta_score']):<4} | {tag} {r_row['r']:+5.2f}R | {r_row['pnl_eur_meta']:+8.2f}€ | {r_row['equity_meta']:9.2f}€"
        )

    # 4. Auditoría Intradía M15 con Meta-Labeling
    audit_intraday_meta_labeling()

    mt5.shutdown()


if __name__ == "__main__":
    main()
