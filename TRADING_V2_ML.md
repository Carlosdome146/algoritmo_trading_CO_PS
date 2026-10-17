# Trading V2 — Fase 2: selección de horizonte y filtro ML (OFFLINE)

**NO CONECTA A METATRADER 5. NO EMITE ÓRDENES NI CONTROLA POSICIONES.**
No usar para trading real ni para habilitar --live.

## Objetivo

Elegir entre horizontes 4, 16 o 32 velas M15 (1, 4 u 8 horas)
y filtrar señales LONG/SHORT con ML sobre el baseline existente.
Si validación o prueba final no pasan, devolver NO_TRADE.

## Instalar y ejecutar (desde la raíz del repositorio)

    python -m pip install -r requirements-v2.txt
    python -m unittest discover -s tests -p "test_*.py" -v
    python -m trading_v2.research.cli --csv data/XAUUSD_M15_broker.csv --timeframe M15 --point 0.01 --out v2_walkforward_local_result.json
    python -m trading_v2.research.cli --csv data/EURUSD_M15_broker.csv --timeframe M15 --point 0.00001 --out v2_eurusd_local_result.json

## Qué hace

1. Lee y valida OHLC M15; rechaza datasets de periodicidad mezclada.
2. Calcula indicadores causales desde el pasado y señales LONG/SHORT.
3. Entrena StandardScaler + LogisticRegression sobre resultados de operaciones
   hipotéticas, con barreras TP/SL y salida máxima al vencer el horizonte.
4. Divide cronológicamente 60% entrenamiento, 20% validación para elección
   de horizonte y umbral, y 20% prueba final no utilizada para elegir.
   Aplica embargo de 40 barras, superior al horizonte máximo de 32 barras.
   **No es todavía walk-forward de múltiples pliegues**: es un split
   cronológico purgado, como primera evaluación experimental.
5. En validación selecciona entre horizontes [4,16,32] y umbrales
   [sin filtro, .25, .35, .45, .55]. Exige al menos 30 operaciones,
   profit factor >= 1.10 y expectativa > 0.02R; la puntuación penaliza
   drawdown. El umbral no se cambia consultando el 20% de prueba.
6. En el test final devuelve NO_TRADE si la expectativa es no positiva,
   profit factor <= 1 o la muestra es insuficiente. Nunca reoptimizar
   sobre ese mismo test.
7. Registra las razones de salida y diagnóstico de pérdidas.

risk_pause.py es un **prototipo aislado y no conectado al bot** de
enfriamiento de 60 minutos tras una pérdida, bloqueo tras tres pérdidas
consecutivas o -1.5% diario. El sistema no rearma una pausa permanente
sin intervención humana. No entrena por una pérdida aislada.

## Limitaciones que impiden operar

- **Comisiones, swaps, financiación, impuestos, lotaje real, márgenes
  y restricciones del bróker NO modelados.**
- Los OHLC exportados por MT5 podrían ser bid (no mid), a diferencia
  de la aproximación del backtester. Verificar con el bróker.
- La zona horaria del histórico y la del servidor no están verificadas.
- Sin datos tick no sabemos el orden real TP/SL intrabar.
- Probabilidad del clasificador NO calibrada como probabilidad real de éxito.
- Elige un horizonte por estrategia en la validación, NO modifica el
  horizonte de cada operación abierta.
- El módulo NO se conecta a ejecución live ni a un proceso de aprendizaje
  incremental. Reentrenar requiere datos posteriores y validación nueva.
- La selección del conjunto de horizontes/umbrales también es una forma
  de ajuste al histórico; el resultado fuera de muestra puede degradarse.
- Pendiente: validación de múltiples pliegues, costes reales, H1/M15
  coherentes, escalado correcto de lotaje, pruebas DEMO prolongadas.

## Pruebas iniciales (CSV histórico octubre 2026)

Hipótesis: 3.000 unidades teóricas de capital, 0.25% de riesgo, point
específico del símbolo, spread contenido en CSV y slippage sintético
de 2 puntos, **sin comisiones ni swaps**.

| Mercado | Horizonte elegido en validación | Umbral ML | Operaciones en test | PF test | Retorno test | Estado |
|---|---|---:|---:|---:|---:|---|
| XAUUSD | 16 barras (4h) | .55 | 3 | 0.7461 | -0.127% | NO_TRADE |
| EURUSD | 4 barras (1h) | .45 | 170 | 0.7897 | -3.426% | NO_TRADE |

No hay evidencia suficiente de rentabilidad. Ni esta rama ni la anterior
deben fusionarse con intención de habilitar operaciones automáticas.
