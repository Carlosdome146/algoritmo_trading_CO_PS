# Trading V3 — Intradía continuo M15/M30 (NO ORB)

**Objetivo decidido:** analizar cada vela M15/M30 cerrada durante toda la sesión,
buscar operaciones LONG/SHORT con expectativa neta favorable y cerrarlas antes
del fin de la sesión. No se limita a los primeros 15/30 minutos de apertura.

**Estado: investigación OFFLINE únicamente.** No tiene integración con
`DemoPaperTrader` ni envía órdenes. El lanzador
`INICIAR_TRADING_Y_MONITOR_DEMO.bat` sigue usando D1: **no ejecutarlo
para probar este laboratorio.**

## Qué reutilizamos del repositorio

- Estrategias existentes: `ema_rsi_baseline`, `donchian_breakout`,
  `bollinger_reversion`, `supertrend_follow`.
- M15/M30 reconstruidas desde cada 3/6 barras M5, con H1 también reconstruida
  desde 12 M5. Nunca usar velas incompletas.
- Señal calculada al **cierre** de la vela; entrada únicamente en la **siguiente
  apertura**. Filtro H1 basado solo en horas cerradas.
- Todo el horario bursátil cash: DAX 09:00–17:30 Europe/Berlin;
  SP500, Nasdaq100 y Dow30 09:30–16:00 America/New_York. Las conversiones
  incluyen horario de verano. El CFD puede ofrecer cotizaciones más horas,
  pero esta primera investigación solo utiliza sesión cash.
- Direcciones LONG/SHORT, sin posiciones simultáneas por activo y salida
  intradía como máximo 60/120 minutos después o al cierre cash.
- Stop 1.2 ATR y objetivo 1.8 ATR para la primera comparación; se mantienen
  constantes por ahora para limitar la búsqueda de parámetros.
- 2 modos: con reglas sin ML o con filtro ML logístico de probabilidad
  0.55 entrenado **solo con trades anteriores**. El modelo no se adapta tras
  una pérdida aislada, ni usa el futuro. Se requieren >=80 eventos de
  entrenamiento y ambas clases.

## Comparación y seguridad estadística

4 estrategias × 2 temporalidades × 2 horizontes de salida × 2 modos ML =
**32 candidatos por activo**.

Dos pliegues de validación cronológica expansiva, con embargo de 12 barras
del marco evaluado: train hasta 45%, validación 45%+embargo–58%;
train hasta 58%, validación 58%+embargo–78%. El holdout final (desde el 78%+
embargo) solo se consulta para el candidato que supere ambos bloques.

Para superar cada validación se necesitan al menos 12 operaciones, PF >=1.10
y esperanza >= +0.02R después del spread simulado y un deslizamiento adverso
de medio spread por lado. El holdout exige al menos 30 trades y la misma
expectativa/PF. **Incluso un resultado favorable no autoriza DEMO con órdenes
ni trading real.** Probar 32 variantes por activo aumenta el riesgo de
sobreajuste; harán falta periodos prospectivos verdaderamente nuevos.

El simulador interpreta OHLC MT5 como BID, usa ASK para comprar/cerrar short,
prioriza SL si toca SL y TP en la misma vela, y no mantiene posiciones
overnight. **Faltan comisiones específicas del contrato, swaps efectivos,
lotes mínimos, margen y ticks**, por lo que los retornos son teóricos.

Datos M5 que tengan spread cero se identifican como desconocidos;
su estimación usa exclusivamente el percentil 75 de spreads positivos
en las 288 barras previas. Mercados con más del 20% de spreads históricos
cero se bloquean. Revisar el reporte de calidad; no atribuir costo cero.

## Ejecutar directamente con el ZIP M5 ya exportado

En PowerShell, desde la raíz de la rama
`feature/v3-continuous-intraday-m15-m30`:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-v2.txt
python -m unittest discover -s tests -p "test_*.py" -v
python -m scripts.investigar_intradia_m15_m30 --zip "admirals_orb_m5_local.zip"
```

Se crea `intradia_m15_m30_local_result.json`; el ZIP sigue privado
(no subirlo a GitHub público). Puede tardar varios minutos con
80.000 M5 por mercado.

**Importante al cambiar de rama:** si el ZIP se encuentra en el directorio
de trabajo no rastreado, se conserva al cambiar de rama.

## Siguiente fase

1. Analizar el informe: frecuencia de señales, trades de validación,
   tasa de acierto, expectativa R, PF, pérdidas y resultados por activo.
2. Diagnosticar mercados que filtran demasiadas señales y comparar
   el coste relativo spread/ATR.
3. Conservar el holdout; diseñar validación *walk-forward* real más extensa
   y pruebas con ticks/M1 cuando dispongamos de datos verificables.
4. Solo entonces preparar un motor de ejecución M15/M30 desacoplado,
   con **bloqueo DEMO obligatorio**, gestión de riesgo y rechazo ante
   API/posiciones/margen incoherentes. Su activación requiere revisión
   separada y aprobación de la estrategia.

No hay garantía de alta tasa de acierto ni de rentabilidad.
