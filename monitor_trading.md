# 🤖 Monitor Cuantitativo V3 (Admirals DEMO)

**Última actualización:** `2026-10-30 10:29:04 (Hora España)` | `09:29:04 UTC`

### 💰 Estado de la Cuenta
- **Cuenta:** DEMO #58678879 (AdmiralsGroup-Demo)
- **Balance:** 3034.75 EUR
- **Equity Flotante:** 3034.75 EUR (0.00 EUR)

### 📈 Posiciones Abiertas
*Sin posiciones abiertas en este momento.*

### 🧠 Semáforo del Cerebro Cuantitativo (Decisiones de los Algoritmos)
| Mercado | Estrategia | Estado | Cierre | SMA200 | RSI(2) | IBS | Criterio / Motivo |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| DAX40 | `idx_dax_bollinger_dip` | 🟡 *ESPERA* | 26087.00 | 24895.26 | 95.6 | 0.88 | RSI(2) neutral (95.6 >= 15.0); Precio dentro de bandas Bollinger (26087.00 > 24932.48) |
| IBEX35 | `idx_ibex_bollinger_dip` | 🟡 *ESPERA* | 18862.08 | 18668.67 | 26.7 | 0.81 | RSI(2) neutral (26.7 >= 10.0); Precio dentro de bandas Bollinger (18862.08 > 18811.63) |
| EURUSD | `fx_eurusd_ker_exhaustion` | 🟡 *ESPERA* | 1.12 | 1.16 | 68.1 | 0.87 | Precio (1.12) < SMA200 (1.16) [Tendencia bajista]; Mercado en rango / no tendencial (KER10=0.20 < 0.42); Sin extremo de agotamiento en bandas 2.0σ (RSI2=68.1) |
| DOW30 | `idx_rsi2_dip_regime` | 🟡 *ESPERA* | 52346.01 | 50654.70 | 31.8 | 0.27 | RSI(2) neutral (31.8 >= 10.0) |
| ORO | `idx_rsi2_dip_regime` | 🟡 *ESPERA* | 4021.35 | 4496.33 | 25.2 | 0.25 | Precio (4021.35) < SMA200 (4496.33) [Tendencia bajista]; RSI(2) neutral (25.2 >= 10.0) |
| SP500 | `idx_rsi2_dip_regime` | 🟡 *ESPERA* | 7678.63 | 7319.06 | 27.0 | 0.03 | RSI(2) neutral (27.0 >= 10.0) |

### 🎯 Cartera Activa y Configuración en Producción (Riesgo 1.0%)
- **Riesgo por Operación:** **1.00%** (~30.18 EUR por trade sobre balance actual).
- **Beneficio Estimado por Acierto:** **+15.00 EUR a +18.00 EUR** netos.
- **Gestión Activa:** Take Profit Asimétrico + Breakeven Causal (eleva Stop Loss a entrada + costes al alcanzar el 40% del recorrido).

| Activo | Símbolo MT5 | Sesión Operativa | Tasa de Acierto (WR) | Profit Factor (ROI) | Salida (TP / SL) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **DAX 40** | `GERMANY40` | Mañana Europa (09:00 - 16:30 CET) | **89.47% (M30)** / **82.35% (M15)** | **2.29** / **1.40** | TP: 12 pts / SL: 35 pts |
| **IBEX 35** | `[IBEX35]` | Mañana Europa (09:00 - 13:00 CET) | **88.24% (M15)** | **2.37** | TP: 15 pts / SL: 25 pts |
| **EUR / USD** | `EURUSD` | Sesión Europea (09:00 - 17:00 CET) | **78.95% (M15)** | **1.38** | TP: 3 pips / SL: 5 pips |
| **Dow Jones 30** | `[DJI30]` | Tarde Wall Street (15:30 - 21:30 CET) | **81.82% (M15)** / **76.92% (M30)** | **2.75** / **2.15** | TP: 55 pts / SL: 110 pts |
| **Oro Spot** | `GOLD` | Solapamiento Londres/NY (14:00 - 20:00 CET) | **84.62% (M15)** / **75.00% (M30)** | **2.04** / **2.28** | TP: 4.0$ / SL: 12.0$ |
| **S&P 500** | `[SP500]` | Tarde Wall Street (15:30 - 21:30 CET) | **84.09% (M15)** | **1.51** | TP: 4.0 pts / SL: 7.5 pts |

### 🛡️ Transparencia de Costes y Comisiones
- **Broker Demo Actual:** Admirals DEMO `#58678879` (Cuenta Trade.MT5: comisión 0.00 EUR en broker; coste integrado en spread).
- **Modelo Cuantitativo Auditado:** IC Markets Raw ECN (Forex: comisión 3.50 USD/lado = ~6.30 EUR/lote round-trip + 0.1 pip spread crudo; Índices: 1.0 pt DAX / 0.4 pt SP500).
- **Spread y Deslizamiento:** Descontados causalmente al Bid/Ask en cada señal y ejecución.

---
*Actualizado automáticamente desde el motor local en segundo plano.*