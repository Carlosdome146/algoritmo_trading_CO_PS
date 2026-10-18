"""Estudio de optimización de ejecución: Órdenes Límite vs Market Open (Opción 3).

Compara científicamente en el histórico de 12 años (2015-2026):
1. Market on Open (MoP): Ejecución inmediata en la apertura de t+1.
2. Limit at Prior Close (Limit = Close[t]): Compra si el precio retrocede al cierre anterior o mejor.
3. Limit Discount 0.10 ATR (Limit = Open[t+1] - 0.10 * ATR): Descuento leve intradía.
4. Limit Discount 0.20 ATR (Limit = Open[t+1] - 0.20 * ATR): Descuento medio intradía.
5. Limit Discount 0.30 ATR (Limit = Open[t+1] - 0.30 * ATR): Descuento profundo intradía.

Métricas evaluadas:
- Tasa de ejecución (Fill Rate %): % de señales que logran entrar.
- Tasa de acierto (Win Rate %): % de operaciones ganadoras sobre las ejecutadas.
- Profit Factor (PF): Calidad de la relación ganancia/pérdida.
- Expectativa matemática por señal (Mean R / Signal): R neto promedio considerando órdenes no ejecutadas (R=0).
- Total R acumulado en 12 años: Ganancia total absoluta del sistema.
"""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd

from trading_v2.research.regime_lab_v3 import (
    MARKET_SYMBOL,
    StrategySpec,
    add_indicators,
    evaluate,
    load_long_history,
    simulate_daily,
)


def run_execution_study(zip_path: str = "admirals_historial_largo_local.zip") -> dict:
    cases = [
        ("SP500", StrategySpec("idx_rsi2_dip_regime", ("SP500",), "long", {"sma": 200, "rsi_th": 10}, 2.5, 10, regime_cap=1.8)),
        ("NASDAQ100", StrategySpec("idx_ibs_dip", ("NASDAQ100",), "long", {"sma": 200, "ibs_th": 0.2}, 2.5, 5)),
        ("NASDAQ100", StrategySpec("idx_rsi2_dip_regime", ("NASDAQ100",), "long", {"sma": 200, "rsi_th": 10}, 2.5, 10, regime_cap=1.8)),
        ("DAX40", StrategySpec("idx_rsi2_dip_regime", ("DAX40",), "long", {"sma": 200, "rsi_th": 10}, 2.5, 10, regime_cap=1.8)),
        ("DOW30", StrategySpec("idx_rsi2_dip_regime", ("DOW30",), "long", {"sma": 200, "rsi_th": 10}, 2.5, 10, regime_cap=1.8)),
    ]

    modes = [
        ("Market on Open", "market", 0.0),
        ("Limit at Prior Close", "limit_close", 0.0),
        ("Limit Discount 0.10 ATR", "limit_discount", 0.10),
        ("Limit Discount 0.20 ATR", "limit_discount", 0.20),
        ("Limit Discount 0.30 ATR", "limit_discount", 0.30),
    ]

    results = {}

    for market, strat in cases:
        key = f"{market}_{strat.name}"
        results[key] = {"market": market, "strategy": strat.name, "modes": {}}
        df = add_indicators(load_long_history(zip_path, market, "D1"))
        
        # Obtenemos el número base de señales de entrada teóricas
        base_trades = simulate_daily(df, strat, market, entry_mode="market")
        base_n = len(base_trades)
        
        for mode_label, mode_id, offset in modes:
            t = simulate_daily(df, strat, market, entry_mode=mode_id, limit_offset_atr=offset)
            n_filled = len(t)
            fill_rate = round(100.0 * n_filled / base_n, 1) if base_n > 0 else 0.0
            
            if not t.empty:
                r = t["r"].to_numpy()
                wins = int((r > 0).sum())
                wr = round(100.0 * wins / n_filled, 1)
                gw = float(r[r > 0].sum())
                gl = float(-r[r < 0].sum())
                pf = round(gw / gl, 3) if gl > 0 else 999.0
                mean_r_trade = round(float(r.mean()), 4)
                total_r = round(float(r.sum()), 2)
                # Expectativa por señal teórica generada: total_r / base_n
                mean_r_per_signal = round(total_r / base_n, 4) if base_n > 0 else 0.0
                max_dd = round(float(evaluate(t)["all"]["max_dd_r"]), 2)
            else:
                wr, pf, mean_r_trade, total_r, mean_r_per_signal, max_dd = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

            results[key]["modes"][mode_label] = {
                "filled": n_filled,
                "fill_rate": fill_rate,
                "win_rate": wr,
                "profit_factor": pf,
                "mean_r_trade": mean_r_trade,
                "mean_r_per_signal": mean_r_per_signal,
                "total_r": total_r,
                "max_dd_r": max_dd,
            }

    return results


def main():
    res = run_execution_study()
    print("=" * 115)
    print(f"{'CASO':<28s} | {'MODALIDAD':<24s} | {'FILL%':<6s} | {'N':<4s} | {'WR%':<6s} | {'PF':<6s} | {'TOT R':<7s} | {'E[R]/SIG':<8s} | {'MAX DD'}")
    print("=" * 115)
    for case_key, data in res.items():
        for mode_label, m in data["modes"].items():
            print(
                f"{case_key:<28s} | {mode_label:<24s} | "
                f"{str(m['fill_rate'])+'%':<6s} | {m['filled']:<4d} | "
                f"{str(m['win_rate'])+'%':<6s} | {str(m['profit_factor']):<6s} | "
                f"{str(m['total_r']):<7s} | {str(m['mean_r_per_signal']):<8s} | "
                f"{str(m['max_dd_r'])+' R'}"
            )
        print("-" * 115)
    
    Path("execution_study_results.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    print("Estudio guardado en execution_study_results.json")


if __name__ == "__main__":
    main()
