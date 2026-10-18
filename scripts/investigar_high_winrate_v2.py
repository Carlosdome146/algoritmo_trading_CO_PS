#!/usr/bin/env python3
"""Ejecuta el Laboratorio de Alta Precisión (>= 79% Win Rate) V2 OFFLINE."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_v2.research.high_winrate_lab import run_high_winrate_archive


def main():
    parser = argparse.ArgumentParser(
        description="Laboratorio de Alta Tasa de Acierto (>= 79% Benchmark) Trading V2 OFFLINE"
    )
    parser.add_argument("--zip", required=True, help="ZIP exportado desde Admirals DEMO")
    parser.add_argument("--out", default="v2_high_winrate_local_result.json")
    args = parser.parse_args()

    result = run_high_winrate_archive(args.zip)
    Path(args.out).write_text(
        json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )

    print("TRADING V2 HIGH-WINRATE PRECISION LAB - ESTUDIO OFFLINE SIN ORDENES REALES")
    print("-" * 105)
    for name, m in result["markets"].items():
        winner = m["chosen"]
        if not winner:
            print(f"{name:7s} -> {m['decision']:22s} | Sin candidato que supere ambos pliegues con >=75% WR y PF>=1.10")
            continue
        f1, f2 = winner["validation_folds"]
        holdout = m["holdout"] or {}
        base_h = holdout.get("spread_only") or {}
        stress_h = holdout.get("spread_plus_slippage") or {}
        print(
            f"{name:7s} -> {m['decision']:22s} | {winner['strategy']} ({winner['exit_profile']}, h={winner['horizon_bars']}, q={winner['ml_quantile']})\n"
            f"          Fold 1 (Estrés):  N={f1['trades']:2d} | WR={f1['win_rate']:5.1f}% (Wilson90>={f1['wilson_lower_90_pct']:5.1f}%) | PF={f1['profit_factor']:.2f} | E[R]={f1['mean_r']:+.3f}\n"
            f"          Fold 2 (Estrés):  N={f2['trades']:2d} | WR={f2['win_rate']:5.1f}% (Wilson90>={f2['wilson_lower_90_pct']:5.1f}%) | PF={f2['profit_factor']:.2f} | E[R]={f2['mean_r']:+.3f}\n"
            f"          Holdout (Spread): N={base_h.get('trades', 0):2d} | WR={str(base_h.get('win_rate')):>5s}% | PF={str(base_h.get('profit_factor')):>5s} | E[R]={str(base_h.get('mean_r')):>6s}\n"
            f"          Holdout (Estrés): N={stress_h.get('trades', 0):2d} | WR={str(stress_h.get('win_rate')):>5s}% | PF={str(stress_h.get('profit_factor')):>5s} | E[R]={str(stress_h.get('mean_r')):>6s}"
        )
    print("-" * 105)
    print("Informe guardado en:", Path(args.out).resolve())


if __name__ == "__main__":
    main()
