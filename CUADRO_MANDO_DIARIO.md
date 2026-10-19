# 📊 Cuadro de Mando Ejecutivo y Liquidación Diaria (2026-10-19)
**Generado:** `2026-10-19 15:30:23 UTC` | **Cuenta:** DEMO #58678879 (AdmiralsGroup-Demo)

---

## 1. 💰 Resumen Económico de la Jornada

| Métrica | Importe (EUR) | Detalle / Origen |
| :--- | :---: | :--- |
| **Ganancia Bruta** | `+0.00 €` | Suma de operaciones con resultado positivo |
| **Pérdida Bruta** | `-0.00 €` | Suma de operaciones con resultado negativo |
| **Comisiones Bróker** | `-0.00 €` | Coste fijo por lote cobrado por Admirals (0.00 € en Trade.MT5) |
| **Swaps / Financiación** | `+0.00 €` | Coste o abono por mantener posiciones durante la noche |
| **Resultado Neto Cerrado** | **`0.00 €`** 🟢 | **Beneficio/Pérdida neto realizado hoy** |
| **Balance Actual** | **`3000.00 €`** | Capital consolidado en cuenta |
| **Equity Flotante (En vivo)** | **`3005.98 €`** | Capital total incluyendo operaciones abiertas (+5.98 €) |

---

## 2. 🏛️ Módulo de Tributación Estimada (IRPF España - Base del Ahorro)
> *Cálculo orientativo según los tramos vigentes del IRPF para ganancias patrimoniales de derivados/CFDs.*

| Concepto Fiscal | Valor | Explicación |
| :--- | :---: | :--- |
| **Base Imponible Generada Hoy** | **`0.00 €`** | Ganancias netas compensadas con pérdidas |
| **Tipo de Retención / Tramo** | **`0.0%`** | Tramo aplicable (19% hasta 6.000 € de beneficio anual) |
| **Importe a Declarar / Reservar** | **`0.00 €`** | Estimación para liquidar con la Agencia Tributaria |
| **Beneficio Limpio (En el Bolsillo)** | **`0.00 €`** 💶 | **Rendimiento neto real tras impuestos** |

> **Nota legal:** Pérdida patrimonial compensable con ganancias de los próximos 4 años o hasta el 25% de rendimientos del capital mobiliario.

---

## 3. 📈 Posiciones Abiertas y en Seguimiento
| Ticket | Activo | Tipo | Lotes | Precio Entrada | Precio Actual | Stop Loss | P&L Flotante (EUR) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| #1233248789 | **US100** | COMPRA (LONG) | 0.04 | 29597.38 | 29765.17 | `28986.09` | **+5.98 €** |

---

## 4. 🧠 Diario de Decisiones del Cerebro Cuantitativo
Este apartado detalla de forma pedagógica **por qué el sistema actuó o se abstuvo** en cada activo:

### SP500 (`[SP500]`) — 🟡 **ABSTENCIÓN / ESPERA**
- **Estrategia:** `idx_rsi2_dip_regime`
- **Valores Técnicos:** Cierre: `7657.87` | Media 200: `7283.58` | RSI(2): `10.6` | IBS: `0.20` | Régimen ATR: `0.90`
- **Motivo de la Decisión:**
  • RSI(2) neutral (10.6 >= 10.0)

### DAX40 (`GERMANY40`) — 🟡 **ABSTENCIÓN / ESPERA**
- **Estrategia:** `idx_dax_bollinger_dip`
- **Valores Técnicos:** Cierre: `25473.23` | Media 200: `24884.45` | RSI(2): `83.3` | IBS: `0.22` | Régimen ATR: `0.89`
- **Motivo de la Decisión:**
  • RSI(2) neutral (83.3 >= 15.0)<br>• Precio dentro de bandas Bollinger (25473.23 > 24974.16)

### EURUSD (`EURUSD`) — 🟡 **ABSTENCIÓN / ESPERA**
- **Estrategia:** `fx_eurusd_ker_exhaustion`
- **Valores Técnicos:** Cierre: `1.12` | Media 200: `1.16` | RSI(2): `79.6` | IBS: `0.50` | Régimen ATR: `1.18`
- **Motivo de la Decisión:**
  • Precio (1.12) < SMA200 (1.16) [Tendencia bajista]<br>• Mercado en rango / no tendencial (KER10=0.04 < 0.42)<br>• Sin extremo de agotamiento en bandas 2.0σ (RSI2=79.6)

### NASDAQ100 (`US100`) — 🟢 **OPERACIÓN ACTIVA**
- **Estrategia:** `idx_ibs_dip`
- **Valores Técnicos:** Cierre: `29191.19` | Media 200: `27816.83` | RSI(2): `0.6` | IBS: `0.12` | Régimen ATR: `1.04`
- **Motivo de la Decisión:**
  • IBS en cierre de rango inferior (0.12 < 0.20)

### DOW30 (`[DJI30]`) — 🟡 **ABSTENCIÓN / ESPERA**
- **Estrategia:** `idx_rsi2_dip_regime`
- **Valores Técnicos:** Cierre: `51957.88` | Media 200: `50505.70` | RSI(2): `54.4` | IBS: `0.17` | Régimen ATR: `0.98`
- **Motivo de la Decisión:**
  • RSI(2) neutral (54.4 >= 10.0)

---

## 5. 🔍 Análisis de Microestructura y Comisiones del Bróker
- **Comisión por orden en Admirals:** **0.00 €** (en cuenta Trade.MT5 el bróker cobra exclusivamente a través del spread).
- **Spread Bid/Ask promedio soportado:** ~0.80 € en DAX40 y ~0.90 $ en Nasdaq 100.
- **Deslizamiento (Slippage):** Las órdenes a mercado entraron en el milisegundo de recepción del precio sin desvío adverso significativo.
- **Gestión del Stop Loss:** El Stop Loss de catástrofe a 2.5x ATR se encuentra activado en el servidor del bróker, protegiendo la cuenta incluso ante caídas de luz o desconexiones.

---
*Informe auditado y firmado automáticamente por el motor cuantitativo V3.*