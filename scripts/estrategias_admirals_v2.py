#!/usr/bin/env python3
"""Ejecuta Strategy Lab V2 contra un ZIP Admirals DEMO SIN conectar a MT5."""
import argparse
import json
from pathlib import Path
from trading_v2.research.strategy_lab import run_archive


def main():
    p=argparse.ArgumentParser(description='Laboratorio de estrategias Trading V2 OFFLINE')
    p.add_argument('--zip',required=True,help='ZIP exportado desde Admirals DEMO')
    p.add_argument('--out',default='v2_strategy_lab_local_result.json')
    args=p.parse_args()
    result=run_archive(args.zip)
    Path(args.out).write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    print('TRADING V2 - ESTUDIO SIN MT5, SIN ÓRDENES')
    for name,m in result['markets'].items():
        winner=m['chosen']
        holdout=m['holdout'] or {}
        stressed=holdout.get('spread_plus_slippage') or {}
        print(name,'->',m['decision'],
              '| estrategia:',winner['strategy'] if winner else 'ninguna',
              '| horizonte:',winner['horizon_bars'] if winner else '-',
              '| PF holdout:',stressed.get('profit_factor'),
              '| winrate holdout:',stressed.get('win_rate'))
    print('Informe guardado:',Path(args.out).resolve())


if __name__=='__main__':
    main()
