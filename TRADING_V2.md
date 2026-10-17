# Trading V2 — Investigación offline (Fase 1)

Esta implementación es independiente de live_trader_mt5.py. **NO conecta a MetaTrader 5, NO abre operaciones y NO afirma haber encontrado una estrategia rentable.**

## Ejecutar (desde la raíz del repositorio)

    python -m pip install -r requirements-v2.txt
    python -m unittest discover -s tests -p "test_v2.py" -v
    python -m trading_v2.cli --csv data/XAUUSD_M15_broker.csv --timeframe M15 --point 0.01 --out v2_research_result.json

El validador debe rechazar la mezcla de granularidades que existe en el archivo DAX de 14 años:

    python -m trading_v2.cli --csv data/DE40_H1_14years.csv --timeframe H1 --point 0.01

## Funciones actuales

- Carga CSV con fecha Time, Datetime o Date y valida duplicados, OHLC inválidos, intervalos menores que la periodicidad y mezcla H1/D1.
- No presupone UTC para los históricos del broker ni inventa barras durante cierres de mercado.
- Estrategia baseline LONG/SHORT EMA20/EMA50 + RSI + ATR, sin ML.
- Señal generada al cierre de la vela i y ejecución simulada al comienzo de i+1.
- Stop adverso cuando SL y TP se tocan en la misma vela; gaps modelados como salidas desfavorables.
- Simulación aproximada de spread bid/ask (OHLC como precio medio) y slippage; una sola posición simultánea.
- Métricas en el 30% final cronológico; riesgo inicial 0,25% del capital por operación.
- Sin operaciones, tasa de acierto y profit factor son null, nunca se inventan resultados.

## LIMITACIONES QUE IMPIDEN USO OPERATIVO

1. USD es **capital teórico normalizado a R**. No se calcula lotaje real ni margen MT5, conversiones de divisa, comisiones, swaps o financiación. No vale para tomar decisiones de inversión.
2. El OHLC exportado por MT5 puede representar bid, no mid; la hipótesis de spread necesita verificarse con el bróker.
3. OHLC no contiene el orden intrabar de máximos/mínimos; se usa SL en caso de simultaneidad.
4. Todavía no hay filtro multi-timeframe H1/M15 ni validación de consistencia temporal entre series.
5. La separación 70/30 no basta para validar un modelo ML. Siguiente fase: purging, walk-forward, calibración, comisiones y comparación de estrategias.
6. Nunca adaptar reglas tras una pérdida aislada; el aprendizaje se valida fuera de muestra antes de activarse.

## Colaboración

Rama feature/v2-data-backtest; revisar mediante PR antes de fusionar en main. No ejecutar live_trader_mt5.py --live mientras existan defectos de seguridad. No subir credenciales ni información sensible.
