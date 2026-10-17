"""Ejecutar estudio ML offline y guardar resultado JSON."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from trading_v2.data.loader import load_csv
from trading_v2.backtesting.engine import Config
from .walkforward import ResearchConfig, research


def main():
    p=argparse.ArgumentParser(description="ML + horizonte automático; investigación offline SIN órdenes")
    p.add_argument('--csv',required=True)
    p.add_argument('--timeframe',choices=('M15',),default='M15')
    p.add_argument('--point',required=True,type=float,help='Tamaño point MT5, NO pip genérico')
    p.add_argument('--spread-fijo-puntos',type=float,default=None)
    p.add_argument('--slippage-puntos',type=float,default=2.)
    p.add_argument('--out',default='v2_walkforward_local_result.json')
    args=p.parse_args()
    data,quality=load_csv(args.csv,args.timeframe)
    cfg=Config(point=args.point,fixed_spread_points=args.spread_fijo_puntos,
               slippage_points=args.slippage_puntos)
    results=research(data,cfg,ResearchConfig())
    out={'tipo':'ESTUDIO ML 100% OFFLINE','archivo':args.csv,'quality':quality.as_dict(),
         'assumptions':{'commission':'DESCONOCIDA, NO MODELADA','swap':'DESCONOCIDO, NO MODELADO',
                        'point':args.point,'spread':'CSV' if args.spread_fijo_puntos is None else args.spread_fijo_puntos,
                        'slippage_points':args.slippage_puntos,
                        'multitimeframe':'NO IMPLEMENTADO (M15 únicamente)',
                        'readiness':'NO APTO PARA OPERATIVA REAL NI AUTOOPERACIÓN DEMO',
                        'horizon_selection':'Automática a nivel de modelo por validación, NO cambia en cada operación'},
         'results':results}
    Path(args.out).write_text(json.dumps(out,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    print(f"Decisión: {results['decision']}")
    if results['chosen']:
        print('Elección (validación):',results['chosen']['horizon_bars'], 'velas M15; umbral:',results['chosen']['ml_threshold'])
        print('Prueba final:',results['test']['metrics'])
    else:
        print('Ninguna configuración superó los mínimos de validación. NO OPERAR.')
    print('Guardado:',args.out)

if __name__=='__main__':
    main()
