---
name: quant-trading-mt5
description: >-
  Arquitectura cuantitativa, reglas de validación Walk-Forward purgada,
  modelado de costes Bid/Ask en MetaTrader 5 (Admirals / brokers australianos)
  y diseño de estrategias de alta tasa de acierto para el proyecto algoritmo_trading_CO_PS.
---

# Skill: Ingeniería Cuantitativa & Trading Algorítmico MT5 (`algoritmo_trading_CO_PS`)

Esta skill centraliza el contexto técnico, las auditorías (V1 y V2) y los estándares de desarrollo del repositorio `Carlosdome146/algoritmo_trading_CO_PS`.

## 1. Contexto del Proyecto y Activos Objetivo
- **Universo de activos (5 mercados principales)**:
  - **DAX 40** (`DE40` / `GERMANY40`)
  - **S&P 500** (`US500` / `[SP500]`)
  - **Dow Jones 30** (`US30` / `[DJI30]`)
  - **Oro Spot** (`XAUUSD` / `GOLD`)
  - **Euro / Dólar** (`EURUSD`)
- **Arquitectura Multi-Temporalidad**:
  - **Filtro Macro (H1)**: Determina dirección estructural solo con **velas H1 completamente cerradas** (`close_time = open_time + 1h <= signal_close_time`). Prohibido usar la vela H1 en formación (`start_pos=0`).
  - **Gatillo Operativo (M15)**: Evalúa al cierre de la vela `i` (`start_pos=1` en vivo) y ejecuta en la apertura de `i+1`.

## 2. Reglas Inquebrantables de Simulación y ML (Estándar V2)
1. **Cero Lookahead Bias**:
   - Ningún indicador, normalizador (`StandardScaler`) ni umbral se ajusta usando datos de validación/test.
   - Al alinear H1 con M15 (`pd.merge_asof(..., direction="backward")`), comparar siempre el instante de **cierre** de la vela M15 con el instante de **cierre** de la vela H1.
2. **Validación Purgada con Embargo**:
   - División cronológica estricta (60% Train / 20% Validation / 20% Holdout Test, o Walk-Forward multi-pliegue).
   - Aplicar embargo (`embargo_bars > max(horizons)`) entre particiones y exigir que el horizonte completo de cada evento quepa dentro de su partición (`i + horizon < split_end`).
3. **Modelado Realista de Precios y Costes (MT5 Bid OHLC)**:
   - MT5 exporta precios **BID** en las barras OHLC.
   - **LONG**: entra en `ASK = Open_bid + Spread + Slippage`; sale en `BID - Slippage`.
   - **SHORT**: entra en `BID = Open_bid - Slippage`; sale en `ASK = Close_bid + Spread + Slippage`.
   - Si una misma vela toca `SL` y `TP` simultáneamente, asumir siempre **Stop Loss primero** (`BOTH_ASSUME_STOP` / `SL_TP_SAME_BAR`).
   - Los gaps de apertura que superan el SL se ejecutan al precio de apertura desfavorable (`GAP_STOP`), nunca al precio teórico del SL.
4. **Seguridad Operativa en MetaTrader 5**:
   - Bloquear por código cualquier envío de órdenes si `account_info().trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO` durante la fase de simulación.
   - Calcular el lotaje exclusivamente mediante `mt5.order_calc_profit()`, redondeando a la **baja** según `volume_step`. Si `volume_min` supera el presupuesto de riesgo, **rechazar la operación** (nunca forzar `volume_min` ni devolver `0.1` por defecto).
   - En posiciones `BUY`, verificar el nivel de Breakeven y cierre contra `tick.bid` (no `tick.ask`); en `SELL`, verificar contra `tick.ask`.
   - Integrar `RiskPause` (enfriamiento tras pérdida, parada tras 3 pérdidas seguidas o -1.5% diario sin rearme automático).

## 3. Estrategias para Alcanzar Alta Tasa de Acierto (Objetivo >= 75% Win Rate)
Un Win Rate del 75%+ es matemáticamente incompatible con ratios TP/SL lejanos (ej. TP = 1.8 ATR vs SL = 1.2 ATR sin gestión activa, donde el acierto natural ronda el 35-45%). Para elevar la tasa de acierto de forma genuina y con Esperanza Matemática ($E[R] > 0$) positiva después de costes:
1. **Asimetría de Salida / Take Profit Escalonado (Partial TP + Breakeven Protegido)**:
   - Capturar beneficios rápidos en zonas de alta probabilidad (ej. TP1 en $0.6 \times \text{ATR}$ a $0.8 \times \text{ATR}$ tras pullback a media institucional o banda de liquidez) cubriendo spread + comisión.
2. **Filtro de Régimen de Mercado y Sesión Líquida**:
   - Operar únicamente en ventanas de máxima liquidez y menor spread relativo (Apertura Europea 08:00-11:30 CET para `GERMANY40`, Solapamiento Londres/NY 14:30-17:30 CET para `US500`/`US30`/`XAUUSD`).
   - Rechazar entradas cuando el ratio `Spread / ATR_M15` supere un umbral crítico (ej. $> 8\%$).
3. **Calibración de Probabilidades (Isotonic / Platt Scaling) y Meta-Labeling**:
   - Combinar clasificadores de gradiente / regresión logística regularizada con calibración de probabilidades en validación, operando solo el decil superior de convicción (`NO_TRADE` por defecto cuando el régimen es ruidoso).

## 4. Comandos de Verificación Rápida
- Ejecutar suite de tests unitarios V2:
  ```powershell
  python -m unittest discover -s tests -p "test_*.py" -v
  ```
- Diagnóstico seguro MT5 (solo lectura):
  ```powershell
  python scripts/diagnostico_admirals_mt5.py
  ```
- Exportar historial cerrado desde MT5 DEMO:
  ```powershell
  python scripts/exportar_historial_admirals_mt5.py
  ```
- Investigación multi-activo offline:
  ```powershell
  python scripts/investigar_admirals_v2.py --zip "admirals_historial_local.zip"
  ```
