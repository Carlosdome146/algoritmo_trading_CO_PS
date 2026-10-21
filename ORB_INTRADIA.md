# Trading V3 — ORB intradia 15/30 minutos (investigación, sin órdenes)

**Estado: prototipo OFFLINE. NO es el ejecutor del bot DEMO, no envía órdenes ni activa el modo live.**

## Por qué se hizo

El lanzador actual \`INICIAR_TRADING_Y_MONITOR_DEMO.bat\` ejecuta
\`--timeframe D1 --strategy idx_rsi2_dip_regime\`: una estrategia de
**velas diarias**, por lo que una sola operación en un día es plausible.
\`institutional_sniper_scalp\` es una lógica M15 basada en barridos de
liquidez y no forma realmente el rango de 15/30m de apertura. ORB requiere
un laboratorio distinto y datos M5 (idealmente ticks/M1 para ejecución).

**ORB 15/30m no implica abrir una operación cada 15/30m.** Los primeros
15 o 30 minutos *definen el rango*. Si el mercado no ofrece ruptura fiable,
el resultado es NO_TRADE. Se pueden buscar hasta dos señales intradía por
sesión y activo con enfriamiento, pero no se fuerza un número de trades.

## Activos y hora de apertura

| Símbolo Admirals | Apertura local (apertura cash/índice de referencia) |
|---|---|
| GERMANY40 | 09:00 Europe/Berlin (Xetra) |
| [SP500] | 09:30 America/New_York |
| US100 | 09:30 America/New_York |
| [DJI30] | 09:30 America/New_York |

Usar siempre horas **locales IANA** con conversión UTC (`zoneinfo`),
no un horario UTC constante; en marzo/octubre hay semanas con cambio
desincronizado de hora entre Europa y EEUU. La cotización CFD Admirals puede
tener sesión distinta de la sesión bursátil de referencia.

## Dos variantes por rango

- `breakout`: ruptura confirmada al cierre de M5 por fuera del máximo/mínimo de ORB, buffer de 0.05 ATR; entra en siguiente apertura M5.
- `retest`: exige ruptura en una vela previa y luego
  retroceso/tacto del extremo del rango y cierre nuevamente fuera en M5.

Comparación predefinida: 15/30 minutos × breakout/retest × TP 1.0/1.5 ATR
= **8 configuraciones por mercado**; SL 1 ATR, salida por tiempo máximo
18 velas M5 (90m), cierre de seguridad antes de 6h tras apertura.
No se pueden tener dos posiciones superpuestas por mercado en el simulador.

Para no sobreajustar: validación temporal sobre sesiones completas:
50-65% y 65-80% como 2 folds; 80-100% como holdout final solo si supera
ambos anteriores (mínimo 10 operaciones por fold, PF >=1.10 y E[R]>=.02).
El 0-50% inicial se reserva como historial anterior/calibración futura:
no se usa en la selección de los 8 candidatos de esta fase.
Esto no constituye aún un entrenamiento ML ni un walk-forward exhaustivo.

## 1. Exportar M5 de Admirals DEMO (solo lectura)

Abrir MT5 Admirals DEMO y, desde la raíz del repositorio, ejecutar:

```powershell
python scripts/exportar_orb_m5_mt5.py --bars 80000
```

Si hay varios terminales:
```powershell
python scripts/exportar_orb_m5_mt5.py --terminal "C:\RUTA\terminal64.exe" --bars 80000
```

Genera `admirals_orb_m5_local.zip` con los CSV:
`ADMIRALS_DAX40_M5.csv`, `ADMIRALS_SP500_M5.csv`,
`ADMIRALS_NASDAQ100_M5.csv`,
`ADMIRALS_DOW30_M5.csv` y `orb_manifest.json`.

El exportador usa exclusivamente funciones de lectura de precios/cuenta y
`symbol_select` (muestra símbolo en Market Watch). Excluye barra en
formación, exige cuenta Admirals DEMO y no envía órdenes.
**No subir a GitHub público el ZIP ni secretos o registros de cuenta.**
Si MT5 no dispone de 80k barras, aumentar barras máximas en sus ajustes
o solicitar menos mediante `--bars`; el laboratorio requiere
al menos 100 sesiones completas por mercado.

## 2. Evaluar los ocho candidatos

```powershell
python -m pip install -r requirements-v2.txt
python -m unittest discover -s tests -p "test_*.py" -v
python -m scripts.investigar_orb_m5 --zip "admirals_orb_m5_local.zip"
```

Resultado `orb_m5_research_local_result.json` por mercado:
número de señales, PF, win-rate, expectancy R y drawdown de los dos pliegues;
holdout final y mejor configuración **solo si pasa ambos pliegues**.

**Sin el ZIP M5 de vuestra cuenta no podemos publicar un resultado real
ni afirmar una tasa de acierto objetivo.**

## Limitaciones que impiden dejarlo operar

- M5 no prueba el orden de ejecución intrabar; si TP y SL se tocan en
  una misma vela se escoge SL adversamente. Se recomiendan ticks/M1.
- Los OHLC de MT5 se asumen BID, y se añade el spread histórico para
  entradas LONG y cierres SHORT; estrés de medio spread extra por
  extremo. Faltan comisión según cuenta, swaps y ejecución real.
- Resultados normalizados en múltiplos R, riesgo teórico 0.25% de
  3.000 EUR, sin lotaje mínimo/márgenes efectivos ni correlaciones.
- Condiciones de cuenta y márgenes de Admirals e IC Markets NO son
  intercambiables. Ejecutar con un único bróker confirmado.
- Las señales pueden existir en días sin operar por festivos o
  falta de barras; el sistema rechaza ORB incompletos.
- Para afirmar robustez se precisan varios años de M5 con regímenes
  variados, datos prospectivos y pruebas de estrés.
- Por ahora no hay ML ORB entrenado ni modelo conectado a
  \`demo_paper_trader.py\`. No alterar su lanzador para ejecutar ORB.

## Próxima fase antes de DEMO automática

1. Auditar divergencias backtest/ejecución, timestamps y spread.
2. Comparar ORB 15 vs 30 en M5 histórico, con filtros de coste
   y frecuencia real de operaciones; no optimizar a posteriori el holdout.
3. Diseñar ML separado de validación, con ventanas temporales purgadas
   y probabilidad calibrada solo si la muestra es suficiente.
4. Reproducir exactamente stops, targets y horario en un runner DEMO
   probado, bloqueando nuevas órdenes ante datos o cálculos ambiguos.
5. Validación prospectiva y aprobación específica antes de usar --live.

No se garantiza rentabilidad ni porcentaje de aciertos.


## Incidencia MT5: Spreads históricos igual a cero

Algunos CSV M5 del terminal registran `Spread=0`. Eso **NO demuestra
que no hubiera coste de negociación**; generalmente significa que el
spread histórico de esa barra no puede reconstruirse con seguridad.

La validación inicial detenía el estudio ante la primera barra cero.
El validador actual conserva `SpreadRaw` y marca `SpreadMissing`;
si existen al menos ocho observaciones positivas en las 288 barras
anteriores, sustituye el cero por el percentil 75 de esos spreads
anteriores. La estimación es causal (sin valores futuros) y el backtest
no envía órdenes. Si no hay historial previo suficiente, la barra no
puede utilizarse para abrir/simular una operación.

El JSON informa de:
- `raw_zero_spread_bars` y `raw_zero_spread_pct`;
- `imputed_from_past_bars` y `spread_unusable_bars`;
- `real_spreads_verified: false`.

**Si más del 20% de barras M5 presenta spread cero,
`NO_TRADE_DATA_QUALITY`**, sin selección automática de la estrategia.
Un porcentaje inferior sigue implicando resultados provisionales:
hay que obtener spreads bid/ask/ticks más fiables antes de automatizar.

Después de actualizar la rama ejecutar el laboratorio sobre el ZIP ya
descargado: no hace falta repetir la exportación salvo que el archivo
sea realmente inválido.
