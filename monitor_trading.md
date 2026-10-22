# 🤖 Monitor Cuantitativo V3 (Admirals DEMO)

**Última actualización:** `2026-10-22 22:26:40 (Hora España)` | `20:26:40 UTC`

### 💰 Estado de la Cuenta
- **Cuenta:** DEMO #58678879 (AdmiralsGroup-Demo)
- **Balance:** 3008.54 EUR
- **Equity Flotante:** 3008.54 EUR (0.00 EUR)

### 📈 Posiciones Abiertas
*Sin posiciones abiertas en este momento.*

### 🧠 Semáforo del Cerebro Cuantitativo (Decisiones de los Algoritmos)
| Mercado | Estrategia | Estado | Cierre | SMA200 | RSI(2) | IBS | Criterio / Motivo |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| DAX40 | `idx_dax_bollinger_dip` | 🟡 *ESPERA* | 25609.84 | 24887.44 | 81.5 | 0.77 | RSI(2) neutral (81.5 >= 15.0); Precio dentro de bandas Bollinger (25609.84 > 24981.35) |
| SP500 | `idx_rsi2_dip_regime` | 🟡 *ESPERA* | 7759.56 | 7295.33 | 79.2 | 0.80 | RSI(2) neutral (79.2 >= 10.0) |
| EURUSD | `fx_eurusd_ker_exhaustion` | 🟡 *ESPERA* | 1.12 | 1.16 | 60.1 | 0.70 | Precio (1.12) < SMA200 (1.16) [Tendencia bajista]; Mercado en rango / no tendencial (KER10=0.13 < 0.42); Sin extremo de agotamiento en bandas 2.0σ (RSI2=60.1) |

### 🛡️ Transparencia de Costes y Comisiones
- **Broker Demo Actual:** Admirals DEMO `#58678879` (Cuenta Trade.MT5: comisión 0.00 EUR en broker; coste integrado en spread).
- **Modelo Cuantitativo Auditado:** IC Markets Raw ECN (Forex: comisión 3.50 USD/lado = ~6.30 EUR/lote round-trip + 0.1 pip spread crudo; Índices: 1.0 pt DAX / 0.4 pt SP500).
- **Spread y Deslizamiento:** Descontados causalmente al Bid/Ask en cada señal y ejecución.

---
*Actualizado automáticamente desde el motor local en segundo plano.*