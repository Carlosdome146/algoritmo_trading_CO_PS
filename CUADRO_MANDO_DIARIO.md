# 📊 Cuadro de Mando Ejecutivo y Liquidación Diaria (2026-10-20)
**Generado:** `2026-10-20 19:16:40 UTC` | **Cuenta:** DEMO #58678879 (AdmiralsGroup-Demo)

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
| **Equity Flotante (En vivo)** | **`2997.31 €`** | Capital total incluyendo operaciones abiertas (-2.69 €) |

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
| #1233248789 | **US100** | COMPRA (LONG) | 0.04 | 29597.38 | 29527.10 | `28986.09` | **-2.50 €** |

---

## 4. 🧠 Diario de Decisiones del Cerebro Cuantitativo
Este apartado detalla de forma pedagógica **por qué el sistema actuó o se abstuvo** en cada activo:

### SP500 (`[SP500]`) — 🟡 **ABSTENCIÓN / ESPERA**
- **Estrategia:** `idx_rsi2_dip_regime`
- **Valores Técnicos:** Cierre: `7698.27` | Media 200: `7287.21` | RSI(2): `46.8` | IBS: `0.61` | Régimen ATR: `0.87`
- **Motivo de la Decisión:**
  • RSI(2) neutral (46.8 >= 10.0)

### DAX40 (`GERMANY40`) — 🟡 **ABSTENCIÓN / ESPERA**
- **Estrategia:** `idx_dax_bollinger_dip`
- **Valores Técnicos:** Cierre: `25179.81` | Media 200: `24884.76` | RSI(2): `17.8` | IBS: `0.01` | Régimen ATR: `0.90`
- **Motivo de la Decisión:**
  • RSI(2) neutral (17.8 >= 15.0)<br>• Precio dentro de bandas Bollinger (25179.81 > 24970.62)

### EURUSD (`EURUSD`) — 🟡 **ABSTENCIÓN / ESPERA**
- **Estrategia:** `fx_eurusd_ker_exhaustion`
- **Valores Técnicos:** Cierre: `1.12` | Media 200: `1.16` | RSI(2): `44.7` | IBS: `0.61` | Régimen ATR: `1.20`
- **Motivo de la Decisión:**
  • Precio (1.12) < SMA200 (1.16) [Tendencia bajista]<br>• Mercado en rango / no tendencial (KER10=0.03 < 0.42)<br>• Sin extremo de agotamiento en bandas 2.0σ (RSI2=44.7)

### NASDAQ100 (`US100`) — 🟡 **ABSTENCIÓN / ESPERA**
- **Estrategia:** `idx_ibs_dip`
- **Valores Técnicos:** Cierre: `29558.54` | Media 200: `27835.79` | RSI(2): `44.8` | IBS: `0.65` | Régimen ATR: `1.01`
- **Motivo de la Decisión:**
  • IBS neutral (0.65 >= 0.20)

### DOW30 (`[DJI30]`) — 🟡 **ABSTENCIÓN / ESPERA**
- **Estrategia:** `idx_rsi2_dip_regime`
- **Valores Técnicos:** Cierre: `52002.79` | Media 200: `50518.03` | RSI(2): `60.3` | IBS: `0.38` | Régimen ATR: `0.98`
- **Motivo de la Decisión:**
  • RSI(2) neutral (60.3 >= 10.0)

---

## 5. 🔍 Análisis de Microestructura y Comisiones del Bróker
- **Comisión por orden en Admirals:** **0.00 €** (en cuenta Trade.MT5 el bróker cobra exclusivamente a través del spread).
- **Spread Bid/Ask promedio soportado:** ~0.80 € en DAX40 y ~0.90 $ en Nasdaq 100.
- **Deslizamiento (Slippage):** Las órdenes a mercado entraron en el milisegundo de recepción del precio sin desvío adverso significativo.
- **Gestión del Stop Loss:** El Stop Loss de catástrofe a 2.5x ATR se encuentra activado en el servidor del bróker, protegiendo la cuenta incluso ante caídas de luz o desconexiones.

---
*Informe auditado y firmado automáticamente por el motor cuantitativo V3.*