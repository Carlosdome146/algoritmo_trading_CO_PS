---
name: macro-geopolitica-y-calendario-bursatil
description: >-
  Inteligencia macroeconómica en tiempo real, bancos centrales (Fed, BCE),
  calendario de noticias de alto impacto (CPI, NFP, tipos de interés, PIB),
  geopolítica, correlaciones intermercado (DXY, bonos, oro, índices) y reglas
  de veto operativo (News Blackout) para proteger el operador de bolsa.
---

# Skill: Inteligencia Macroeconómica, Situación Mundial y Correlaciones Intermercado

Activa esta skill cuando necesites contextualizar la situación bursátil y geopolítica actual, analizar correlaciones entre los 5 activos del proyecto (`GERMANY40`, `[SP500]`, `[DJI30]`, `GOLD`, `EURUSD`) o diseñar filtros de protección ante eventos macroeconómicos.

---

## 1.Cómo Obtiene el Agente Conocimiento de la Situación Mundial Actual

A diferencia de un script de Python aislado que solo ve números pasados en un CSV, Antigravity dispone de **dos canales en tiempo real**:
1. **Conexión en directo al mercado vía MetaTrader 5**: Lectura instantánea de cotizaciones, spreads actuales, aperturas con gap y volatilidad intradía en `AdmiralsGroup-Demo`.
2. **Búsqueda Web en vivo (`search_web` / `read_url_content`)**: Capacidad de consultar en cualquier momento qué está pasando hoy en el mundo (decisiones de la Reserva Federal o el BCE, datos de inflación de EE.UU. y Eurozona, resultados empresariales del S&P 500, tensiones geopolíticas en Oriente Medio/Europa que mueven el Oro y el DAX).

---

## 2. Matriz de Correlaciones Intermercado (Cross-Asset Intelligence)

Los 5 activos de nuestra cartera no se mueven en el vacío; forman un sistema interconectado que podemos usar como **features de confirmación (Intermarket Features)** tanto en backtest (cruzando los CSV de los 5 mercados por timestamp UTC) como en vivo:

| Relación Intermercado | Mecanismo Económico | Aplicación Cuantitativa en el Modelo |
| :--- | :--- | :--- |
| **`[SP500]` & `[DJI30]` $\leftrightarrow$ `GERMANY40`** | Liderazgo de Wall Street sobre Europa (especialmente a partir de las `13:30 UTC`). | Si `[SP500]` y `[DJI30]` están en fuerte impulso alcista M15/H1, la probabilidad de éxito de un `LONG` en `GERMANY40` aumenta significativamente; si divergen, vetar rupturas. |
| **`EURUSD` $\leftrightarrow$ `GOLD` (`XAUUSD`)** | Ambos cotizan contra el Dólar Estadounidense (`USD`). Debilidad del dólar suele impulsar tanto al `EURUSD` como al `GOLD`. | Cuando `GOLD` y `EURUSD` se mueven simultáneamente contra el `USD`, confirma flujo institucional de dólar (*Dollar Flow*); cuando `GOLD` sube fuerte pero `EURUSD` cae, indica **flujo de refugio geopolítico (*Risk-Off*)**, lo cual es bajista para `GERMANY40` y `[SP500]`. |
| **Régimen *Risk-On* vs. *Risk-Off*** | En pánicos bursátiles o escaladas geopolíticas, el capital huye de la renta variable (`GERMANY40`, `[SP500]`, `[DJI30]`) y entra en `GOLD` y `USD`. | Usar el diferencial de retorno relativo $\text{Ret}(\text{GOLD}) - \text{Ret}(\text{SP500})$ en las últimas 4 barras M15 como indicador en tiempo real de aversión al riesgo. |

---

## 3. Reglas de Protección ante Eventos Macroeconómicos (*News & Shock Blackout*)

Ningún indicador técnico (EMA, RSI, Bollinger) funciona en el minuto exacto en que se publica un dato de inflación (**CPI**), empleo (**NFP**) o decisión de tipos (**FOMC / BCE**): el spread se multiplica por 5, el libro de órdenes se vacía y los stops sufren deslizamientos masivos.

### 3.1 Ventanas Horarias Críticas de Publicación Macro (UTC)
- **`12:15 - 12:45 UTC` (invierno `13:15 - 13:45 UTC`)**: Decisión de tipos del **BCE** y rueda de prensa + publicación de **CPI / NFP / PIB / Ventas Minoristas de EE.UU.** (`08:30 EST`).
- **`18:00 - 19:00 UTC` (invierno `19:00 - 20:00 UTC`)**: Decisiones de tipos del **FOMC (Reserva Federal)** y conferencia de prensa (`14:00 - 14:30 EST`).

### 3.2 Detector Automático de Choque de Spread y Volatilidad (*Shock Veto*)
Incluso en backtest histórico sin calendario externo de noticias, una noticia macro de alto impacto deja una huella instantánea en la microestructura que el bot debe detectar y bloquear:
1. **Anomalía de Spread**: Si $\text{Spread}_t > 2.0 \times \text{Mediana}_{40}(\text{Spread})_t$, el mercado está ilíquido o en plena noticia $\implies$ **`NO_TRADE`**.
2. **Vela de Choque (*Shock Bar*)**: Si el rango de la última vela M15 cerrada $H_t - L_t > 2.8 \times \text{ATR}_{14, t}$, no entrar en la vela inmediatamente siguiente por riesgo de latigazo (*whipsaw*).
