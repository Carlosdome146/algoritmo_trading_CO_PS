# 🤖 Monitor Cuantitativo V3 (Admirals DEMO)

**Última actualización:** `2026-10-29 16:20:47 (Hora España)` | `15:20:47 UTC`

### 💰 Estado de la Cuenta
- **Cuenta:** DEMO #58678879 (AdmiralsGroup-Demo)
- **Balance:** 3017.59 EUR
- **Equity Flotante:** 3017.59 EUR (0.00 EUR)

### 📈 Posiciones Abiertas
*Sin posiciones abiertas en este momento.*

### 🧠 Semáforo del Cerebro Cuantitativo (Decisiones de los Algoritmos)
| Mercado | Estrategia | Estado | Cierre | SMA200 | RSI(2) | IBS | Criterio / Motivo |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| DAX40 | `idx_dax_bollinger_dip` | 🟡 *ESPERA* | 25732.98 | 24889.65 | 86.8 | 0.56 | RSI(2) neutral (86.8 >= 15.0); Precio dentro de bandas Bollinger (25732.98 > 24957.16) |
| SP500 | `idx_rsi2_dip_regime` | 🟡 *ESPERA* | 7725.44 | 7315.19 | 78.8 | 0.13 | RSI(2) neutral (78.8 >= 10.0) |
| EURUSD | `fx_eurusd_ker_exhaustion` | 🟡 *ESPERA* | 1.12 | 1.16 | 42.4 | 0.69 | Precio (1.12) < SMA200 (1.16) [Tendencia bajista]; Mercado en rango / no tendencial (KER10=0.02 < 0.42); Sin extremo de agotamiento en bandas 2.0σ (RSI2=42.4) |
| IBEX35 | `idx_ibex_bollinger_dip` | 🟡 *ESPERA* | 18853.64 | 18662.59 | 23.9 | 0.03 | RSI(2) neutral (23.9 >= 10.0); Precio dentro de bandas Bollinger (18853.64 > 18838.68) |

### 🛡️ Transparencia de Costes y Comisiones
- **Broker Demo Actual:** Admirals DEMO `#58678879` (Cuenta Trade.MT5: comisión 0.00 EUR en broker; coste integrado en spread).
- **Modelo Cuantitativo Auditado:** IC Markets Raw ECN (Forex: comisión 3.50 USD/lado = ~6.30 EUR/lote round-trip + 0.1 pip spread crudo; Índices: 1.0 pt DAX / 0.4 pt SP500).
- **Spread y Deslizamiento:** Descontados causalmente al Bid/Ask en cada señal y ejecución.

---
*Actualizado automáticamente desde el motor local en segundo plano.*