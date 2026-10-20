"""Auditoría de Estrategias Cuantitativas de Alta Tasa de Acierto (Ismael Benchmark vs Swing/Intraday)."""
from __future__ import annotations
import pandas as pd
from trading_v2.research.regime_lab_v3 import load_long_history, add_indicators, simulate_daily, StrategySpec, metrics

def test_daily_portfolio():
    zip_path = "admirals_historial_largo_local.zip"
    print("=" * 80)
    print("PORTAFOLIO SWING V3 (D1) - RENDIMIENTO AUDITADO CON COSTES REALES ADMIRALS/IC MARKETS")
    print("=" * 80)
    
    # 1. EURUSD KER Exhaustion (D1)
    d_eur = add_indicators(load_long_history(zip_path, "EURUSD", "D1"))
    s_eur = StrategySpec("fx_eurusd_ker_exhaustion", ("EURUSD",), "both", {"ker_cap": 0.42, "rsi_th": 8, "sigma": 2.0}, stop_atr=2.5, max_bars=10)
    tdf_eur = simulate_daily(d_eur, s_eur, "EURUSD")
    m_eur = metrics(tdf_eur["r"].to_numpy())
    print(f"EURUSD D1 KER:      N={m_eur['n']:3d} | WR={m_eur['win_rate']:5.1f}% | PF={m_eur.get('profit_factor',0):5.2f} | R_mean={m_eur['mean_r']:+6.4f} | MaxDD={m_eur['max_dd_r']:5.2f}R")

    # 2. DAX40 Bollinger Dip (D1)
    d_dax = add_indicators(load_long_history(zip_path, "DAX40", "D1"))
    s_dax = StrategySpec("idx_dax_bollinger_dip", ("DAX40",), "long", {"rsi_th": 15, "sigma": 1.8}, stop_atr=2.5, max_bars=10)
    tdf_dax = simulate_daily(d_dax, s_dax, "DAX40")
    m_dax = metrics(tdf_dax["r"].to_numpy())
    print(f"DAX40 D1 Bollinger: N={m_dax['n']:3d} | WR={m_dax['win_rate']:5.1f}% | PF={m_dax.get('profit_factor',0):5.2f} | R_mean={m_dax['mean_r']:+6.4f} | MaxDD={m_dax['max_dd_r']:5.2f}R")

    # 3. SP500 RSI2 Dip (D1)
    d_sp = add_indicators(load_long_history(zip_path, "SP500", "D1"))
    s_sp = StrategySpec("idx_rsi2_dip_regime", ("SP500",), "long", {"sma": 200, "rsi_th": 10}, stop_atr=2.5, max_bars=10)
    tdf_sp = simulate_daily(d_sp, s_sp, "SP500")
    m_sp = metrics(tdf_sp["r"].to_numpy())
    print(f"SP500 D1 RSI2 Dip:  N={m_sp['n']:3d} | WR={m_sp['win_rate']:5.1f}% | PF={m_sp.get('profit_factor',0):5.2f} | R_mean={m_sp['mean_r']:+6.4f} | MaxDD={m_sp['max_dd_r']:5.2f}R")

    # 4. US100 (NASDAQ100) RSI2 Dip (D1)
    d_ndx = add_indicators(load_long_history(zip_path, "NASDAQ100", "D1"))
    s_ndx = StrategySpec("idx_rsi2_dip_regime", ("NASDAQ100",), "long", {"sma": 200, "rsi_th": 10}, stop_atr=2.5, max_bars=10)
    tdf_ndx = simulate_daily(d_ndx, s_ndx, "NASDAQ100")
    m_ndx = metrics(tdf_ndx["r"].to_numpy())
    print(f"NASDAQ D1 RSI2 Dip: N={m_ndx['n']:3d} | WR={m_ndx['win_rate']:5.1f}% | PF={m_ndx.get('profit_factor',0):5.2f} | R_mean={m_ndx['mean_r']:+6.4f} | MaxDD={m_ndx['max_dd_r']:5.2f}R")

if __name__ == "__main__":
    test_daily_portfolio()
