# Trading V2 — investigación multi-mercado Admirals (fase offline)

Este script NO importa MetaTrader5 ni conecta al bróker: trabaja con el ZIP
exportado desde la cuenta Admirals DEMO. NO envía órdenes. No está validado
para operativa real ni DEMO automatizada.

## Ejecutar desde la raíz del repositorio

```powershell
python -m pip install -r requirements-v2.txt
python -m unittest discover -s tests -p "test_*.py" -v
python scripts/investigar_admirals_v2.py --zip "admirals_historial_local.zip"
```

El resultado se guarda como `admirals_v2_research_local_result.json` e incluye
las métricas de selección y, solo si hay candidato válido, las del bloque final.

## Método

- Los cinco símbolos de Admirals: GERMANY40, [SP500], [DJI30], GOLD y EURUSD.
- Lee M15/H1 desde el ZIP y comprueba que las velas horarias completas coincidan.
- Usa solo tendencia de H1 **ya cerrada** al decidir con señales M15.
- EMA 20/50, ATR/volatilidad y RSI generan señales LONG/SHORT.
- Modelo logístico entrenado con resultados hipotéticos por operación.
- Examina horizontes de 4, 16, 32 barras M15 y umbrales sin filtro/.35/.45/.55.
- Divide cada símbolo: 60% entrenamiento, 20% selección y 20% holdout;
  embargo 40 velas entre bloques. Para impedir filtrado retrospectivo,
  una señal se admite solo si **todo su horizonte máximo** cabe en su bloque.
- Solo examina holdout si pasa 30 operaciones, PF >=1.10 y expectativa >=0.02R
  en selección. Exige criterios similares en holdout y escenarios de coste.
- Modelo de precios **MT5 OHLC como bid**: compra al ask, venta al bid;
  salida LONG al bid, cierre SHORT al ask, con spread histórico de la vela.
- Escenario adicional de estrés: medio spread de deslizamiento desfavorable
  al entrar y otro medio spread al cerrar. Cuando TP y SL tocan la misma
  vela, el simulador elige SL; gaps al precio ejecutable de apertura.
- Una posición simultánea por **mercado simulado**, sin apalancamiento cruzado.

## Resultados exploratorios: exportación Admirals de 17 oct. 2026

Todos: `NO_TRADE`. Capital normalizado: 3.000 EUR y riesgo nominal de 0,25%
por operación, sin verificar lotes reales, margen ni divisas de beneficio.

| Mercado | Selección en validación | Operaciones holdout con estrés | PF holdout | Retorno teórico holdout |
|---|---|---:|---:|---:|
| DAX40 | 4 barras, ML .45 | 79 | 0.7300 | -2.1953% |
| SP500 | No supera validación | — | — | — |
| DOW30 | 16 barras, ML .35 | 77 | 0.5174 | -6.3969% |
| GOLD | 16 barras, sin filtro ML | 122 | 0.6494 | -6.9461% |
| EURUSD | No supera validación | — | — | — |

El holdout solo se calcula para candidatos que pasan la selección; los
mercados sin candidato no reciben «rentabilidad 0%» ficticia.

## Limitaciones críticas

- **Comisiones y swaps no modelados**; las tarifas reales siguen sin conocerse.
- Supuesto OHLC=bid y spreads por barra pendientes de contrastar con el bróker.
- Valoración en EUR expresada como múltiplos R: no utiliza tamaño de contrato,
  `order_calc_profit`, margen, comisión ni lotaje mínimo. Rentabilidades son
  **normalizadas y no realizables automáticamente**.
- El calendario contiene cierres y gaps; los horizontes son barras,
  no tiempo de reloj fijo.
- Una sola división 60/20/20 purgada NO es walk-forward multi-fold.
- El ML no está calibrado como probabilidad real de ganar.
- Tres horizontes y cuatro umbrales ya son búsqueda de parámetros;
  resultados sobreajustados en validación no prueban ninguna ventaja.
- Comparaciones mercado a mercado, no cartera multiactivo con riesgo
  agregado y correlación.
- Los datos M15 disponibles cubren ~6-7 meses; falta variedad de regímenes.
- Pendiente auditoría de horario del servidor MT5, tick data y eventos.

## Próximos criterios, antes de habilitar siquiera DEMO autónoma

1. Auditoría del origen y modalidad de cotización bid/ask de los históricos.
2. Entidad/condiciones contractuales, comisión, swap y `order_calc_profit`.
3. Walk-forward de múltiples pliegues con embargo y periodos más largos.
4. Control global por cartera y cálculo de lotes real, rechazando el mínimo
   si rompe el riesgo permitido.
5. Pruebas DEMO controladas tras pasar **todas** las revisiones anteriores.

**No ejecutar `live_trader_mt5.py --live` con el bot original.**
