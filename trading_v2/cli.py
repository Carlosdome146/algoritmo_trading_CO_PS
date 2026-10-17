"""CLI offline de validación y baseline. NO abre operaciones."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .data.loader import load_csv
from .data.validator import DataQualityError
from .strategies.trend_following import add_indicators
from .backtesting.engine import Config, run_backtest

def main():
    p = argparse.ArgumentParser(description="Investigación V2 offline; nunca conecta a MT5")
    p.add_argument("--csv", required=True)
    p.add_argument("--timeframe", choices=("M15","H1","D1"), required=True)
    p.add_argument("--point", type=float, required=True)
    p.add_argument("--spread-fijo-puntos", type=float, default=None)
    p.add_argument("--slippage-puntos", type=float, default=2.0)
    p.add_argument("--capital", type=float, default=3000.)
    p.add_argument("--riesgo", type=float, default=.0025)
    p.add_argument("--out", default="v2_research_result.json")
    args = p.parse_args()
    try:
        df, report = load_csv(args.csv, args.timeframe)
        signal_bars = add_indicators(df)
        cut = int(len(signal_bars)*.70)
        opts = Config(initial_equity=args.capital, risk_fraction=args.riesgo, point=args.point,
                      fixed_spread_points=args.spread_fijo_puntos, slippage_points=args.slippage_puntos)
        metrics, trades = run_backtest(signal_bars.iloc[cut:].copy(), opts)
    except (DataQualityError, ValueError) as exc:
        p.exit(2, f"[RECHAZADO] {exc}\n")
    output = {
        "tipo": "INVESTIGACIÓN OFFLINE / NO OPERATIVO", "input": str(Path(args.csv)),
        "validacion": report.as_dict(),
        "evaluacion": "30% final cronológico; baseline sin ML ni optimización",
        "limitaciones": [
            "No simula lotaje real ni margen MT5", "Sin comisiones ni swaps hasta recibir tarifas",
            "Spread histórico aproximado sobre precio medio",
            "Zona horaria no inferida", "No representa rentabilidad esperable"
        ],
        "parametros": vars(args), "metricas": metrics, "trades": trades
    }
    Path(args.out).write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print("RESEARCH ONLY |", metrics)
    print(f"Resultado guardado en {args.out}")
    for w in report.warnings:
        print("ADVERTENCIA:", w)

if __name__ == "__main__":
    main()
