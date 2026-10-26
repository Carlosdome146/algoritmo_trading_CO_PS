# 🤖 Monitor Cuantitativo V3 (Admirals DEMO)

**Última actualización:** `2026-10-26 21:07:45 (Hora España)` | `20:07:45 UTC`

### 💰 Estado de la Cuenta
- **Cuenta:** DEMO #58678879 (AdmiralsGroup-Demo)
- **Balance:** 3008.54 EUR
- **Equity Flotante:** 3008.54 EUR (0.00 EUR)

### 📈 Posiciones Abiertas
*Sin posiciones abiertas en este momento.*

### 🧠 Semáforo del Cerebro Cuantitativo (Decisiones de los Algoritmos)
| Mercado | Estrategia | Estado | Cierre | SMA200 | RSI(2) | IBS | Criterio / Motivo |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| DAX40 | `idx_dax_bollinger_dip` | 🟡 *ESPERA* | 25130.87 | 24885.62 | 18.4 | 0.33 | RSI(2) neutral (18.4 >= 15.0); Precio dentro de bandas Bollinger (25130.87 > 24970.21) |
| SP500 | `idx_rsi2_dip_regime` | 🟡 *ESPERA* | 7632.83 | 7302.39 | 13.2 | 0.35 | RSI(2) neutral (13.2 >= 10.0) |
| EURUSD | `fx_eurusd_ker_exhaustion` | 🟡 *ESPERA* | 1.12 | 1.16 | 16.2 | 0.42 | Precio (1.12) < SMA200 (1.16) [Tendencia bajista]; Mercado en rango / no tendencial (KER10=0.00 < 0.42); Sin extremo de agotamiento en bandas 2.0σ (RSI2=16.2) |
| IBEX35 | `idx_ibex_bollinger_dip` | 🟡 *ESPERA* | 18949.37 | 18642.68 | 26.6 | 0.73 | RSI(2) neutral (26.6 >= 10.0); Precio dentro de bandas Bollinger (18949.37 > 18821.67) |

### 🛡️ Transparencia de Costes y Comisiones
- **Broker Demo Actual:** Admirals DEMO `#58678879` (Cuenta Trade.MT5: comisión 0.00 EUR en broker; coste integrado en spread).
- **Modelo Cuantitativo Auditado:** IC Markets Raw ECN (Forex: comisión 3.50 USD/lado = ~6.30 EUR/lote round-trip + 0.1 pip spread crudo; Índices: 1.0 pt DAX / 0.4 pt SP500).
- **Spread y Deslizamiento:** Descontados causalmente al Bid/Ask en cada señal y ejecución.

---
*Actualizado automáticamente desde el motor local en segundo plano.*