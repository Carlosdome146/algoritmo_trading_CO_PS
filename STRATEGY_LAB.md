# Trading V2 — laboratorio de estrategias (solo investigación)

**No conecta a MetaTrader 5. Sin órdenes. No autoriza operativa DEMO ni real.**

## Motivación y procedencia

Referencias conceptuales revisadas:

- Freqtrade Strategies: https://github.com/freqtrade/freqtrade-strategies
  Ejemplos de Supertrend y Bollinger. GPL-3.0. **No se ha copiado código GPL**.
- QuantConnect LEAN: https://github.com/QuantConnect/Lean
  Separación señales/backtesting/riesgo. Apache-2.0.
- VeighNa/vn.py: https://github.com/vnpy/vnpy
  Diseño por componentes y aprendizaje cuantitativo. MIT.
- bukosabino/ta: https://github.com/bukosabino/ta
  Formulaciones de indicadores técnicos. MIT.

Las implementaciones en trading_v2/strategies/candidates.py son originales, con NumPy y pandas.

## Estrategias

1. ema_rsi_baseline: referencia existente, sin alterar señales.
2. donchian_breakout: ruptura máximo/mínimo de 20 velas anteriores, filtro H1 y ATR.
3. bollinger_reversion: cierre extremo Bollinger(20,2), RSI extremo, ADX suavizado bajo.
4. supertrend_follow: Supertrend(10,3) causal, cambios direccionales confirmados por H1.

Las tres estrategias nuevas rechazan una señal si el spread/ATR es >=15%.
Son hipótesis iniciales: **no son parámetros óptimos demostrados**.

## Ejecutar

Desde PowerShell en la raíz del repositorio:

    python -m pip install -r requirements-v2.txt
    python -m unittest discover -s tests -p "test_*.py" -v
    python -m scripts.estrategias_admirals_v2 --zip "admirals_historial_local.zip"

Indicar el nombre exacto del ZIP si incluye sufijo (1).
El resultado se guarda en v2_strategy_lab_local_result.json, excluido de Git.
No publicar los históricos bróker personales en GitHub.

## Selección y validación temporal

- Señales M15 con tendencia H1 de velas ya CERRADAS.
- Simulación desde la apertura de la vela M15 siguiente.
- Horizontes de 4, 16, 32 barras (1/4/8 horas de velas, no necesariamente horas de reloj).
- Por estrategia/horizonte: sin filtro ML, o clasificador logístico con umbral 0.55.
- ML se entrena con ejemplos de ganancias Y PÉRDIDAS históricas y StandardScaler
  ajustado solo al training. No se reentrena después de una pérdida aislada.
- Fold 1: entrenamiento 0-45%, validación 45-58%; fold 2: entrenamiento
  0-58%, validación 58-78%; embargo de 40 barras entre train/validación.
- Holdout reservado del 78 al 100%, tras embargo: no se utiliza para elegir
  estrategia, horizonte ni umbral.
- Se exigen 12 operaciones, PF >= 1.10 y expectativa >=0.02R en CADA fold,
  ya con escenario de spread + deslizamiento adverso.
- Solo si supera ambos folds se permite UNA evaluación del holdout, que exige
  30 operaciones y resultados suficientes en dos escenarios de costes.
- Si nadie supera validación: NO_TRADE. No se vuelve a ajustar el holdout.
- El scoring favorece la expectativa en R y penaliza drawdown. La tasa de
  acierto se reporta pero nunca es el único objetivo.
- Los resultados negativos pueden desglosarse por lado, causa de cierre,
  RSI, spread relativo y probabilidad histórica. Es diagnóstico offline;
  NO provoca modificaciones automáticas del modelo.

## Resultado del 17/10/2026 sobre ZIP Admirals validado

Cada mercado contiene 12.000 velas M15 y 3.500 H1. Las 24 configuraciones
por mercado no lograron superar AMBOS pliegues temporales, por lo que no se
utilizó el holdout para seleccionar modelos.

| Mercado | Configuraciones elegibles | Decisión |
|---|---:|---|
| DAX 40 | 0 | NO_TRADE |
| S&P 500 | 0 | NO_TRADE |
| Dow Jones | 0 | NO_TRADE |
| Oro | 0 | NO_TRADE |
| EUR/USD | 0 | NO_TRADE |

Estos hallazgos NO prueban que las estrategias nunca puedan funcionar.
Tampoco prueban rentabilidad ni autorizan despliegue.

## Limitaciones críticas

- Históricos de unos 6-7 meses, insuficientes para todos los regímenes.
- OHLC asumido BID, spread histórico y escenario de +0.5 spread desfavorable
  por extremo (entrada/salida): requiere confirmar convenciones del bróker.
- Comisiones, swaps, conversión de divisa, lotaje, margen, sesiones,
  correlaciones entre activos y pérdidas por gaps extremos incompletos.
- Capital normalizado 3.000 EUR; riesgo nominal 0.25% multiplicado por R,
  no es un importe verificable en MT5 sin order_calc_profit/order_calc_margin.
- ML no produce probabilidades calibradas ni realiza auto-despliegue.
- 24 variantes por mercado implican riesgo de minería/sobreajuste.
- Los indicadores simplificados no son clones exactos de bibliotecas ajenas.

Siguientes pasos: históricos multianuales, coste completo y sesiones,
walk-forward extendido, calibración ML fuera de muestra, sizing real MT5
solo lectura, simulación de cartera y auditoría antes de cualquier DEMO automática.

**Prohibido ejecutar el bot antiguo con --live mientras los riesgos
de la versión original no estén corregidos.**
