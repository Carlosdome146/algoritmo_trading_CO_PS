# Auditoría técnica — Trade Algorithim

**Fecha:** 16 de octubre de 2026  
**Fuente:** `Trade Algorithim.zip`, suministrado por el usuario.  
**Alcance:** lectura de los 10 archivos `.py`, revisión de 19 `.csv`, ejecución local de 5 simuladores originales y reconstrucción retrospectiva aproximada de las reglas de entrada de `live_trader_mt5.py`.  
**Restricción:** sin terminal MetaTrader 5, sin conexión con el bróker y sin logs de producción. No se han enviado órdenes. Los cálculos de señales H1/M15 son una aproximación con históricos exportados, no reproducción tick a tick. 

## Dictamen ejecutivo

**No pasar a una cuenta real.** El motor todavía no acredita una estrategia rentable y tiene riesgos técnicos de ejecución. Primero reparar modelo/datos/backtester, luego validar con periodos futuros de paper trading y límites de capital.

### Causa más probable de cero operaciones

- `live_trader_mt5.py:415-423`: sin el argumento `--live`, `dry_run=True` y **nunca se envían órdenes**.
- `live_trader_mt5.py:254-275,351-356`: además de la confluencia H1/M15 y los filtros horarios, la probabilidad debe superar `0.48`.
- Reconstrucción histórica del clasificador M15 original sobre los CSV suministrados: **ninguna** de 15.573 señales técnicas aproximadas supera simultáneamente el 48% requerido.
- No se puede afirmar cuál de estas causas explica el comportamiento de una sesión concreta sin la línea de comandos empleada y los logs del terminal.

| Mercado | Señales técnicas M15+H1 | Con filtro ML al 48% | Máxima prob. entre señales técnicas |
|---|---:|---:|---:|
| DE40 | 4.176 | 0 | 38,44% |
| US500 | 3.128 | 0 | 34,69% |
| US30 | 2.792 | 0 | 44,68% |
| XAUUSD | 5.477 | 0 | 45,94% |
| **Total** | **15.573** | **0** | — |

> Los clasificadores se ajustaron usando sus CSV completos, por lo que esta prueba no es evaluación fuera de muestra. Para el filtro H1 se asociaron fechas de la serie `*_H1_broker.csv`; puede haber errores de alineación y velas en formación. El resultado constituye evidencia de un filtro excesivamente restrictivo en estos datos, no una garantía de que jamás abrirá operaciones.

## Reproducción de los backtests originales

No se alteró la lógica de los programas.

### `enhanced_strategy.py` (30% final fuera de muestra)

| Mercado | Trades | Acierto puro | PF | DD máximo | Retorno |
|---|---:|---:|---:|---:|---:|
| DAX | 104 | 25,0% | 0,63 | -23,07% | -20,84% |
| S&P 500 | 64 | 18,8% | 0,37 | -24,30% | -23,06% |
| Dow Jones | 65 | 24,6% | 0,61 | -16,62% | -13,90% |
| EUR/USD | 235 | 23,4% | 0,38 | -63,83% | -62,51% |

### `master_quant_bot.py` (30% final fuera de muestra)

| Mercado | Trades | Acierto puro | PF | Retorno |
|---|---:|---:|---:|---:|
| DAX | 9 | 33,3% | 0,71 | -1,79% |
| S&P 500 | 11 | 9,1% | 0,16 | -7,88% |
| Dow Jones | 0 | N/D | 0 asignado por código | 0% |
| EUR/USD | 0 | N/D | 0 asignado por código | 0% |

### `alpha_14years_model.py` (DAX 2022-2026)

| Estrategia | Trades | PF | DD | Retorno | Capital simulado desde 3.000 |
|---|---:|---:|---:|---:|---:|
| Base | 697 | 0,63 | -80,64% | -80,12% | 596,43 |
| ML | 0 | **999 mostrado artificialmente** | 0% | 0% | 3.000 |

**Advertencia:** PF=999 cuando no hay pérdidas/no existen operaciones es un valor centinela de los scripts, no una medida de buen rendimiento.

Otros tests originales: `ml_strategy.py` DAX 37 trades ML, 45,9% acierto y +5,35% de retorno calculado **a partir de etiquetas idealizadas**, pero el resto de mercados tienen resultados negativos o cero operaciones; `backtester.py` tiene recuentos diminutos en ciertas estrategias y no calcula resultados ejecutables de trading CFD real.

Estas cifras son **resultados del simulador original**; sus fallos metodológicos impiden usarlas como estimaciones fidedignas de ganancias o pérdidas futuras.

## Hallazgos críticos con localización

| Severidad | Archivo:línea | Hallazgo | Cambio necesario |
|---|---|---|---|
| CRÍTICA | `live_trader_mt5.py:278-291` | Lotes forzados al mínimo del bróker incluso si el riesgo proyectado supera el presupuesto; retorna `0.1` en error; redondeo fijo a dos decimales sin respetar `volume_step` universalmente. | Volumen calculado con `order_calc_profit` en divisa de la cuenta, redondeo a la **baja**, y rechazo si el lote mínimo supera el límite de riesgo. |
| CRÍTICA | `live_trader_mt5.py:415-429` | `--live` manda órdenes a **la cuenta conectada**, no comprueba `ACCOUNT_TRADE_MODE_DEMO`; el texto 'DEMO' es solo una etiqueta. | Bloquear por defecto toda ejecución en real, comprobar tipo de cuenta y requerir habilitación explícita. |
| CRÍTICA | `live_trader_mt5.py:338-339` | Si `positions_get()` devuelve `None` por error, el bot lo interpreta como cero posiciones. | Detener ejecución ante errores de posiciones u órdenes. |
| ALTA | `live_trader_mt5.py:379-410` | No hace `order_check`, controles explícitos de `trade_stops_level`, redondeo a `digits`/`trade_tick_size`, comprobación amplia de retcodes, ni control de cotización obsoleta. | Validación pretrade, normalización y logs de rechazos. |
| ALTA | `live_trader_mt5.py:308-324` | Para posición BUY comprueba breakeven con `ask`; debería medir ejecutabilidad de cierre con `bid`. Además no verifica resultado de mover SL. | Usar `bid` en compras, `ask` en ventas, y confirmar retcode/SL efectivo. |
| ALTA | `live_trader_mt5.py:201-275` | Promete bidireccionalidad pero solo produce `trigger_long` y envía BUY. | Añadir operativa short *solo tras validación independiente de rentabilidad*, sin forzar ventas. |
| ALTA | `live_trader_mt5.py:50-133,254-275,370-374` | El objetivo de entrenamiento (TP=1,6 ATR, SL=1 ATR, 16 velas) difiere del objetivo real (TP=1,8 ATR, SL=1,2 ATR, sin salida a 16 velas); además cambia el setup y el filtro H1. | Unificar exactamente etiquetado, señal, horizonte y ejecución. |
| ALTA | `live_trader_mt5.py:49-133,174-199` | El modelo se ajusta con CSV local y **no actualiza** el CSV si existe; el reentrenamiento cada medianoche vuelve a leer el mismo archivo. | Ingestión incremental verificada, versionado y cambio de modelo bajo control. |
| ALTA | `live_trader_mt5.py:204,207,216` | Usa horario local del PC y velas `start_pos=0` **todavía en formación**; mezcla zonas horarias y sesga señales respecto al backtest de cierre de vela. | Convertir a UTC y zonas IANA, usar últimas velas cerradas (`start_pos=1`) y ejecutar una vez por cierre de barra. |
| ALTA | `alpha_14years_model.py:108-135`, `ml_strategy.py:101-130`, `live_trader_mt5.py:90-107` | Labels evalúan TP antes que SL **dentro de la misma vela**, cuando se desconoce qué ocurrió primero; los vencimientos se etiquetan como derrota. | Modelo bid/ask de intrabar conservador; etiquetado triple barrier con timeout separado. |
| ALTA | `enhanced_strategy.py:160-189`, `alpha_14years_model.py:237-255` | Breakeven/TP/SL se resuelven en la misma vela siguiendo prioridad del código, sin trayectoria intrabar real. | Evaluación tick o M1 y política conservadora para barras ambiguas. |
| ALTA | `backtester.py:18-30,100-143` | El constructor recibe `spread_pips_or_points` pero no aplica spreads reales en las operaciones. | Spread por símbolo/fecha, comisión, swap, slippage y tamaño de contrato reales. |
| MEDIA | `live_trader_mt5.py:175-191` | El bot declara 50.000 velas, pero no registra fecha/horizonte real ni número de muestras entrenadas. | Informe del universo temporal y cobertura. |
| MEDIA | `live_trader_mt5.py:26-31,418` | `EURUSD` existe en el histórico pero no se ejecuta. | Configuración independiente con reglas calibradas (no simplemente activarlo). |
| MEDIA | `enhanced_strategy.py:193-229`, `alpha_14years_model.py:263-274` | 'Breakeven' estadístico por tolerancia puede coexistir con `won` y sesgar conteos/Profit Factor; ausencia de operaciones se representa como PF=999. | Ganancia/pérdida plana mutuamente excluyentes; PF no definido como N/D. |

## Calidad de los datasets

- CSV: **19**, de ellos **10 archivos de broker** M15/H1 más **1 largo DE40 H1**, y **8 históricos yfinance** (diario/horario de 4 mercados).
- `DE40_H1_14years.csv` tiene 61.393 registros; **2012-2015 contienen barras fechadas solo a las 00:00, una por jornada**, no velas H1. En 2016 pasa a ~5.684 observaciones/hora real. Este cambio de granularidad hace inválido considerar los 14 años como un entrenamiento horario homogéneo.
- Históricos M15 del bróker: 50.000 observaciones por DE40, US500, US30, XAUUSD, EURUSD, con primeras fechas entre mayo y octubre de 2024; no son 14 años en M15.
- Los tres índices desde Yahoo más EURUSD tienen H1 históricamente más corto que el diario. `DAX40_1h.csv` y `EURUSD_1h.csv` tienen **volumen 0 en todas las filas**, que no sirve como confirmación de volumen real.
- `EURUSD_1d.csv`: **29 velas con OHLC internamente inconsistentes** (`High < max(Open,Close)` o `Low > min(Open,Close)`). Han de revisarse/descartarse.
- `EURUSD_M15_broker.csv`: ~39% de spreads almacenados igual a cero; no puede asumirse que el coste de negociación real sea cero.
- Comprobar desplazamientos de hora y DST Europa/EEUU al mezclar CSV Yahoo con históricos MT5 de distinta procedencia.

## Arquitectura recomendada V2

1. **Etapa de datos**: ingesta de histórico por bróker, timestamp UTC, validación OHLC, continuidad, timezone, registro de spread efectivo y contrato/tick value.
2. **Etapa de investigación**: biblioteca de estrategias **separadas** por activo (momentum, ruptura, reversión) y exposición por correlación; código con pruebas unitarias.
3. **Entrenamiento ML**: eventos no solapados o muestras ponderadas, target derivado de PnL realista y misma política SL/TP/time exit que la simulación. Transformadores entrenados solo con pasado. Métricas ROC/PR si proceden, **calibración de probabilidad** y curva de rentabilidad por umbral.
4. **Backtest**: generador de eventos de barra cerrada, entrada en siguiente cotización negociable, bid/ask y spreads, comisiones, stops intrabar conservadores/tick, órdenes rechazadas, margen, swaps, costes del bróker, reglas horarias DST.
5. **Validación**: train/validation/test cronológicos separados, purga por horizonte, walk-forward anidado; test intacto no utilizado para seleccionar estrategias/umbrales; múltiples ventanas, estrés, Monte Carlo por trade/block bootstrap.
6. **Riesgo**: limitar riesgo por operación y por día, exposición total y correlación, volúmenes mínimos no rentables rechazados, kill switch, umbral de drawdown y bloqueo ante datos/cuenta inconsistentes.
7. **Ejecución**: cuenta DEMO verificada, señales por evento de vela cerrada, precheck y retcodes, reconexión, idempotencia, logs estructurados y reconciliación posiciones.
8. **Paper trading prospectivo**: observar un período suficiente, comparar backtest y fills reales de demo y exigir rentabilidad neta **con incertidumbre estadística** antes de cualquier riesgo real.

## Recomendación de acciones inmediatas

1. **Desactivar `--live` si hay riesgo de estar conectado a una cuenta real.** Mantener el proyecto en DEMO y conservar código y CSV originales como baseline inmutable.
2. Ejecutar `diagnostico_gatillos_mt5.py` desde el directorio del bot (lee estados pero nunca envía órdenes) y compartir `diagnostico_gatillos_resultado.json`.
3. En paralelo, ejecutar `diagnostico_mt5_solo_lectura.py` y compartir su JSON (sin credenciales).
4. Registrar durante varias sesiones cada motivo de rechazo y los errores `order_check`/retcodes en un entorno aislado.
5. Implementar backtester y risk engine V2 antes de probar umbrales inferiores u optimización con algoritmos genéticos.

**En ningún caso se garantiza acierto del 79% ni rentabilidad a tres meses.** Una estrategia elegida porque funciona en el histórico puede no reproducir su desempeño cuando el mercado cambia.
