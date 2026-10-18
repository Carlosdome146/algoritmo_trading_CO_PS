"""Comparativa de carteras: Incorporación de NASDAQ100 a SP500 + DAX40 + DOW30."""
from __future__ import annotations

import pandas as pd
from trading_v2.research.regime_lab_v3 import (
    StrategySpec,
    add_indicators,
    evaluate,
    load_long_history,
    simulate_daily,
)

zip_path = "admirals_historial_largo_local.zip"

sp = simulate_daily(
    add_indicators(load_long_history(zip_path, "SP500", "D1")),
    StrategySpec("idx_rsi2_dip_regime", ("SP500",), "long", {"sma": 200, "rsi_th": 10}, 2.5, 10, regime_cap=1.8),
    "SP500",
)
sp["asset"] = "SP500"

dax = simulate_daily(
    add_indicators(load_long_history(zip_path, "DAX40", "D1")),
    StrategySpec("idx_rsi2_dip_regime", ("DAX40",), "long", {"sma": 200, "rsi_th": 10}, 2.5, 10, regime_cap=1.8),
    "DAX40",
)
dax["asset"] = "DAX40"

dow = simulate_daily(
    add_indicators(load_long_history(zip_path, "DOW30", "D1")),
    StrategySpec("idx_rsi2_dip_regime", ("DOW30",), "long", {"sma": 200, "rsi_th": 10}, 2.5, 10, regime_cap=1.8),
    "DOW30",
)
dow["asset"] = "DOW30"

nas_rsi = simulate_daily(
    add_indicators(load_long_history(zip_path, "NASDAQ100", "D1")),
    StrategySpec("idx_rsi2_dip_regime", ("NASDAQ100",), "long", {"sma": 200, "rsi_th": 10}, 2.5, 10, regime_cap=1.8),
    "NASDAQ100",
)
nas_rsi["asset"] = "NASDAQ100_RSI"

nas_ibs = simulate_daily(
    add_indicators(load_long_history(zip_path, "NASDAQ100", "D1")),
    StrategySpec("idx_ibs_dip", ("NASDAQ100",), "long", {"sma": 200, "ibs_th": 0.2}, 2.5, 5),
    "NASDAQ100",
)
nas_ibs["asset"] = "NASDAQ100_IBS"

# Base: 3 indices
base = pd.concat([sp, dax, dow]).sort_values("entry_time").reset_index(drop=True)
ev_base = evaluate(base)["all"]

# Cartera con NASDAQ100 RSI2
port_rsi = pd.concat([sp, dax, dow, nas_rsi]).sort_values("entry_time").reset_index(drop=True)
ev_rsi = evaluate(port_rsi)["all"]

# Cartera con NASDAQ100 IBS
port_ibs = pd.concat([sp, dax, dow, nas_ibs]).sort_values("entry_time").reset_index(drop=True)
ev_ibs = evaluate(port_ibs)["all"]

print("=" * 90)
print(f"{'CARTERA':<35s} | {'N':<4s} | {'WR%':<6s} | {'PF':<6s} | {'TOT R':<7s} | {'MAX DD':<7s} | {'t-stat'}")
print("=" * 90)
for label, ev, df in [
    ("Base (SP500 + DAX40 + DOW30)", ev_base, base),
    ("+ NASDAQ100 (RSI2 Regime)", ev_rsi, port_rsi),
    ("+ NASDAQ100 (IBS Dip)", ev_ibs, port_ibs),
]:
    tot_r = round(float(df["r"].sum()), 2)
    print(
        f"{label:<35s} | {ev['n']:<4d} | {str(ev['win_rate'])+'%':<6s} | "
        f"{str(ev['profit_factor']):<6s} | {str(tot_r):<7s} | {str(ev['max_dd_r'])+' R':<7s} | {ev['t_stat']}"
    )
print("=" * 90)
