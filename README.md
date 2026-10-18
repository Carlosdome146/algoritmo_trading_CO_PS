# Trading V2 — Sistema de investigación cuantitativa (MT5)

Repositorio colaborativo para analizar datos históricos y prototipar estrategias de trading con Python y MetaTrader 5.

> **Estado: INVESTIGACIÓN / NO OPERATIVO.** Ninguna estrategia V2 está validada para enviar órdenes a una cuenta real ni a una DEMO automática. Los backtests actuales no demuestran rentabilidad fuera de muestra. **No ejecutar el bot antiguo `live_trader_mt5.py` con `--live`**: su control de riesgos sigue pendiente de auditoría.

## Componentes

| Ubicación | Contenido | Estado |
|---|---|---|
| `trading_v2/` | Validación de datos, baseline y selección ML offline | Experimental |
| `scripts/investigar_admirals_v2.py` | Investigación M15/H1 multiactivo desde un ZIP local | Offline |
| `scripts/diagnostico_admirals_mt5.py` | Inspección de especificaciones de una cuenta Admirals DEMO | Solo lectura |
| `scripts/exportar_historial_admirals_mt5.py` | Exporta históricos de Admirals DEMO | Solo lectura |
| `tests/` | Pruebas de causalidad, simulación y seguridad | Automáticas en GitHub |
| `live_trader_mt5.py` y otros scripts originales | Código previo a V2 | **Legacy; no activar órdenes** |

## Primeros pasos

Crear un entorno virtual e instalar dependencias para V2:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-v2.txt
python -m unittest discover -s tests -p 'test_*.py' -v
```

Investigar datos exportados localmente (no se requiere MT5 para este comando):

```powershell
python scripts/investigar_admirals_v2.py --zip 'admirals_historial_local.zip'
```

El ZIP del bróker no está en GitHub. Consulta
[la guía de exportación](ADMIRALS_EXPORT.md) y
[el informe de investigación](ADMIRALS_MULTI_ASSET_RESEARCH.md).

## Datos de referencia y límites

- Cuenta de estudio: Admirals Group AS, servidor `AdmiralsGroup-Demo`, 3.000 **EUR** ficticios, apalancamiento de la DEMO 1:100.
- Instrumentos: `GERMANY40`, `[SP500]`, `[DJI30]`, `GOLD` y `EURUSD`.
- Los costes de comisiones y swaps no están totalmente verificados. Los modelos de riesgo son aproximaciones en múltiplos R; no calculan todavía lotes reales ni margen efectivo.
- **Ninguno de los cinco mercados pasó la evaluación final para activar órdenes.** Ver [informe multiactivo](ADMIRALS_MULTI_ASSET_RESEARCH.md).
- No añadir al repositorio claves, tokens, números de cuenta, credenciales, informes personales del terminal ni datos privados.

## Trabajo en equipo

La rama `main` contiene código integrado; los cambios nuevos se hacen en ramas `feature/*` o `fix/*` y se revisan mediante Pull Requests.

Leer [CONTRIBUTING.md](CONTRIBUTING.md) para el flujo de trabajo, las pruebas y las condiciones necesarias antes de cualquier integración. Los tests se ejecutan en PR dirigidas a `main` y después de cada push a `main`.

## Documentación técnica

- [Motor offline V2](TRADING_V2.md)
- [Filtro ML y selección temporal](TRADING_V2_ML.md)
- [Exportador Admirals](ADMIRALS_EXPORT.md)
- [Investigación multiactivo Admirals](ADMIRALS_MULTI_ASSET_RESEARCH.md)

**Aviso:** el repositorio es código experimental, no asesoramiento financiero.


## Laboratorio ampliado de estrategias (experimental)

Añadidas 3 familias de señales causales: Donchian Breakout, Bollinger/RSI/ADX
y Supertrend con H1; se conserva EMA/RSI como control. El proyecto ahora
puede comparar 4 estrategias x 3 horizontes (4/16/32 M15) x 2 modos
(sin ML / filtro ML), mediante **dos folds temporales de validación y
holdout final protegido**.

Ejecutar **sin conexión a MT5** desde la raíz del repositorio:

    python -m scripts.estrategias_admirals_v2 --zip "admirals_historial_local.zip"

Los cinco mercados Admirals obtuvieron decisión NO_TRADE en la primera
validación doble: ningún modelo justifica operar todavía. El sistema aprende
de trades ganadores/perdedores únicamente durante entrenamiento OFFLINE;
no altera el modelo por pérdidas individuales.

[Metodología, procedencia, resultados y limitaciones](STRATEGY_LAB.md).
