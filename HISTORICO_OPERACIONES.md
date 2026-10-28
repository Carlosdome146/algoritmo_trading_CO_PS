# 📊 Registro Histórico de Operaciones en Vivo — Algoritmo Quant

> **Última actualización:** `28/10/2026 23:34:21` (Hora Española) | **Cuenta DEMO Admirals:** `#58678879`

Este documento refleja **en tiempo real y con transparencia absoluta** todas las operaciones ejecutadas en la cuenta por el bot. Cada orden se puede verificar directamente en MetaTrader 5 con su número de Ticket.

---

## 📈 Resumen Global de Rendimiento

| Métrica | Valor | Estado |
| :--- | :---: | :---: |
| **Balance Inicial** | `3,000.00 €` | Base de capital |
| **Balance Actual** | **`3,017.59 €`** | `+17.59 €` |
| **Rentabilidad Acumulada** | **`+0.59%`** | 🚀 En verde |
| **Total Operaciones Cerradas** | **`2`** | — |
| **Operaciones Ganadoras** | **`2`** | 🟢 Aciertos |
| **Operaciones Perdedoras** | **`0`** | 🔴 Fallos |
| **Tasa de Acierto (Win Rate)** | **`100.0%`** | ⭐ Objetivo $\ge 80\%$ cumplido |
| **Factor de Beneficio (Profit Factor)** | **`∞ (Sin pérdidas)`** | Excelente |

---

## 📜 Detalle Operación por Operación

| # | Fecha (España) | Activo | Tipo | Lotes | Entrada | Salida | Puntos | Duración | Motivo Cierre | Resultado Neto (€) | Balance |
| :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :--- | :-: | :-: |
| **1** | 22/10/2026 00:53 | **`US100`** | `BUY` | `0.04` | `29,597.38` | `29,847.77` | `+250.39` | `2d 15h 20m` | Regla de Salida | 🟢 **`+8.54 €`** | `3,008.54 €` |
| **2** | 27/10/2026 12:34 | **`[IBEX35]`** | `SELL` | `0.60` | `18,980.26` | `18,965.17` | `+15.09` | `3m 49s` | Take Profit | 🟢 **`+9.05 €`** | `3,017.59 €` |

---

## 🔍 Fichas Técnicas Detalladas de las Últimas Operaciones

### Operación #2 — `[IBEX35]` (🟢 GANADORA)
- **Ticket Posición MT5:** `#1233736948` (Orden Entrada `#1233736948`, Orden Salida `#1233738122`)
- **Estrategia / Gatillo:** `V2_M15_SHORT`
- **Dirección:** `SELL` | **Volumen:** `0.60` lotes
- **Momento Entrada:** `27/10/2026 12:30:55` a precio `18980.26`
- **Momento Salida:** `27/10/2026 12:34:44` a precio `18965.17`
- **Tiempo en Mercado:** `3m 49s`
- **Configuración Inicial:** Stop Loss en `19005.26` | Take Profit en `18965.26`
- **Motivo de Ejecución de Cierre:** `Take Profit` (`[tp 18965.26]`)
- **Desglose Económico:** Beneficio bruto: `+9.05 €` | Swap: `+0.00 €` | Comisión: `+0.00 €`
- **Beneficio Neto:** **`+9.05 €`**

### Operación #1 — `US100` (🟢 GANADORA)
- **Ticket Posición MT5:** `#1233248789` (Orden Entrada `#1233248789`, Orden Salida `#1233520232`)
- **Estrategia / Gatillo:** `V3_D1_LONG`
- **Dirección:** `BUY` | **Volumen:** `0.04` lotes
- **Momento Entrada:** `19/10/2026 09:32:23` a precio `29597.38`
- **Momento Salida:** `22/10/2026 00:53:15` a precio `29847.77`
- **Tiempo en Mercado:** `2d 15h 20m`
- **Configuración Inicial:** Stop Loss en `28986.09` | Take Profit en `0.0`
- **Motivo de Ejecución de Cierre:** `Regla de Salida` (`Close DAILY_RULE_EXIT_SMA5`)
- **Desglose Económico:** Beneficio bruto: `+8.92 €` | Swap: `-0.38 €` | Comisión: `+0.00 €`
- **Beneficio Neto:** **`+8.54 €`**

---

_Registro generado automáticamente por el sistema cuantitativo de trading en MetaTrader 5._