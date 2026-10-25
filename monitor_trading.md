# 🤖 Monitor Cuantitativo V3 (Admirals DEMO)

**Última actualización:** `2026-10-25 16:44:21 (Hora España)` | `15:44:21 UTC`

### 💰 Estado de la Cuenta
- **Cuenta:** DEMO #58678879 (AdmiralsGroup-Demo)
- **Balance:** 3008.54 EUR
- **Equity Flotante:** 3008.54 EUR (0.00 EUR)

### 📈 Posiciones Abiertas
*Sin posiciones abiertas en este momento.*

### 🧠 Semáforo del Cerebro Cuantitativo (Decisiones de los Algoritmos)
| Mercado | Estrategia | Estado | Cierre | SMA200 | RSI(2) | IBS | Criterio / Motivo |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| DAX40 | `idx_dax_bollinger_dip` | 🟡 *ESPERA* | 25365.85 | 24887.00 | 37.5 | 0.20 | RSI(2) neutral (37.5 >= 15.0); Precio dentro de bandas Bollinger (25365.85 > 24981.07) |
| SP500 | `idx_rsi2_dip_regime` | 🟡 *ESPERA* | 7664.92 | 7298.92 | 19.9 | 0.22 | RSI(2) neutral (19.9 >= 10.0) |
| EURUSD | `fx_eurusd_ker_exhaustion` | 🟡 *ESPERA* | 1.12 | 1.16 | 30.2 | 0.41 | Precio (1.12) < SMA200 (1.16) [Tendencia bajista]; Mercado en rango / no tendencial (KER10=0.02 < 0.42); Sin extremo de agotamiento en bandas 2.0σ (RSI2=30.2) |
| IBEX35 | `idx_ibex_bollinger_dip` | 🟡 *ESPERA* | 18945.95 | 18636.48 | 25.6 | 0.22 | RSI(2) neutral (25.6 >= 10.0); Precio dentro de bandas Bollinger (18945.95 > 18805.53) |

### 🛡️ Transparencia de Costes y Comisiones
- **Broker Demo Actual:** Admirals DEMO `#58678879` (Cuenta Trade.MT5: comisión 0.00 EUR en broker; coste integrado en spread).
- **Modelo Cuantitativo Auditado:** IC Markets Raw ECN (Forex: comisión 3.50 USD/lado = ~6.30 EUR/lote round-trip + 0.1 pip spread crudo; Índices: 1.0 pt DAX / 0.4 pt SP500).
- **Spread y Deslizamiento:** Descontados causalmente al Bid/Ask en cada señal y ejecución.

---
*Actualizado automáticamente desde el motor local en segundo plano.*