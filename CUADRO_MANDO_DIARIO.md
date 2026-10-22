# 📊 Cuadro de Mando Ejecutivo y Liquidación Diaria (2026-10-22)
**Generado:** `2026-10-22 20:27:17 UTC` | **Cuenta:** DEMO #58678879 (AdmiralsGroup-Demo)

---

## 1. 💰 Resumen Económico de la Jornada

| Métrica | Importe (EUR) | Detalle / Origen |
| :--- | :---: | :--- |
| **Ganancia Bruta** | `+0.00 €` | Suma de operaciones con resultado positivo |
| **Pérdida Bruta** | `-0.00 €` | Suma de operaciones con resultado negativo |
| **Comisiones Bróker** | `-0.00 €` | Coste fijo por lote cobrado por Admirals (0.00 € en Trade.MT5) |
| **Swaps / Financiación** | `+0.00 €` | Coste o abono por mantener posiciones durante la noche |
| **Resultado Neto Cerrado** | **`0.00 €`** 🟢 | **Beneficio/Pérdida neto realizado hoy** |
| **Balance Actual** | **`3008.54 €`** | Capital consolidado en cuenta |
| **Equity Flotante (En vivo)** | **`3008.54 €`** | Capital total incluyendo operaciones abiertas (+0.00 €) |

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
*No hay posiciones abiertas en este momento (100% liquidez protegida).*

---

## 4. 🧠 Diario de Decisiones del Cerebro Cuantitativo
Este apartado detalla de forma pedagógica **por qué el sistema actuó o se abstuvo** en cada activo:

### DAX40 (`GERMANY40`) — 🟡 **ABSTENCIÓN / ESPERA**
- **Estrategia:** `idx_dax_bollinger_dip`
- **Valores Técnicos:** Cierre: `25609.84` | Media 200: `24887.44` | RSI(2): `81.5` | IBS: `0.77` | Régimen ATR: `0.90`
- **Motivo de la Decisión:**
  • RSI(2) neutral (81.5 >= 15.0)<br>• Precio dentro de bandas Bollinger (25609.84 > 24981.35)

### SP500 (`[SP500]`) — 🟡 **ABSTENCIÓN / ESPERA**
- **Estrategia:** `idx_rsi2_dip_regime`
- **Valores Técnicos:** Cierre: `7759.56` | Media 200: `7295.33` | RSI(2): `79.2` | IBS: `0.80` | Régimen ATR: `0.89`
- **Motivo de la Decisión:**
  • RSI(2) neutral (79.2 >= 10.0)

### EURUSD (`EURUSD`) — 🟡 **ABSTENCIÓN / ESPERA**
- **Estrategia:** `fx_eurusd_ker_exhaustion`
- **Valores Técnicos:** Cierre: `1.12` | Media 200: `1.16` | RSI(2): `60.1` | IBS: `0.70` | Régimen ATR: `1.15`
- **Motivo de la Decisión:**
  • Precio (1.12) < SMA200 (1.16) [Tendencia bajista]<br>• Mercado en rango / no tendencial (KER10=0.13 < 0.42)<br>• Sin extremo de agotamiento en bandas 2.0σ (RSI2=60.1)

---

## 5. 🔍 Análisis de Microestructura y Comisiones del Bróker
- **Comisión por orden en Admirals:** **0.00 €** (en cuenta Trade.MT5 el bróker cobra exclusivamente a través del spread).
- **Spread Bid/Ask promedio soportado:** ~0.80 € en DAX40 y ~0.90 $ en Nasdaq 100.
- **Deslizamiento (Slippage):** Las órdenes a mercado entraron en el milisegundo de recepción del precio sin desvío adverso significativo.
- **Gestión del Stop Loss:** El Stop Loss de catástrofe a 2.5x ATR se encuentra activado en el servidor del bróker, protegiendo la cuenta incluso ante caídas de luz o desconexiones.

---
*Informe auditado y firmado automáticamente por el motor cuantitativo V3.*