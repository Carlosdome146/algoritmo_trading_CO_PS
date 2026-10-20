# 🤖 Monitor Cuantitativo V3 (Admirals DEMO)

**Última actualización:** `2026-10-20 23:27:45 (Hora España)` | `21:27:45 UTC`

### 💰 Estado de la Cuenta
- **Cuenta:** DEMO #58678879 (AdmiralsGroup-Demo)
- **Balance:** 3000.00 EUR
- **Equity Flotante:** 3003.42 EUR (+3.42 EUR)

### 📈 Posiciones Abiertas
| Ticket | Símbolo | Tipo | Lotes | Entrada | Precio Actual | Stop Loss | PnL (EUR) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| #1233248789 | US100 | COMPRA | 0.04 | 29597.38 | 29704.10 | 28986.09 | +3.80 € |

### 🧠 Semáforo del Cerebro Cuantitativo (Decisiones de los Algoritmos)
| Mercado | Estrategia | Estado | Cierre | SMA200 | RSI(2) | IBS | Criterio / Motivo |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| DAX40 | `idx_dax_bollinger_dip` | 🟡 *ESPERA* | 25179.81 | 24884.76 | 17.8 | 0.01 | RSI(2) neutral (17.8 >= 15.0); Precio dentro de bandas Bollinger (25179.81 > 24970.62) |
| SP500 | `idx_rsi2_dip_regime` | 🟡 *ESPERA* | 7698.27 | 7287.21 | 46.8 | 0.61 | RSI(2) neutral (46.8 >= 10.0) |
| EURUSD | `fx_eurusd_ker_exhaustion` | 🟡 *ESPERA* | 1.12 | 1.16 | 69.6 | 0.58 | Precio (1.12) < SMA200 (1.16) [Tendencia bajista]; Mercado en rango / no tendencial (KER10=0.06 < 0.42); Sin extremo de agotamiento en bandas 2.0σ (RSI2=69.6) |

### 🛡️ Transparencia de Costes y Comisiones
- **Broker Demo Actual:** Admirals DEMO `#58678879` (Cuenta Trade.MT5: comisión 0.00 EUR en broker; coste integrado en spread).
- **Modelo Cuantitativo Auditado:** IC Markets Raw ECN (Forex: comisión 3.50 USD/lado = ~6.30 EUR/lote round-trip + 0.1 pip spread crudo; Índices: 1.0 pt DAX / 0.4 pt SP500).
- **Spread y Deslizamiento:** Descontados causalmente al Bid/Ask en cada señal y ejecución.

---
*Actualizado automáticamente desde el motor local en segundo plano.*