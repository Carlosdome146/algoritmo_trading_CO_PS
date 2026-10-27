# 🤖 Monitor Cuantitativo V3 (Admirals DEMO)

**Última actualización:** `2026-10-27 09:31:09 (Hora España)` | `08:31:09 UTC`

### 💰 Estado de la Cuenta
- **Cuenta:** DEMO #58678879 (AdmiralsGroup-Demo)
- **Balance:** 3008.54 EUR
- **Equity Flotante:** 3004.61 EUR (-3.93 EUR)

### 📈 Posiciones Abiertas
| Ticket | Símbolo | Tipo | Lotes | Entrada | Precio Actual | Stop Loss | PnL (EUR) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| #1233736948 | [IBEX35] | VENTA | 0.60 | 18980.26 | 18986.81 | 19005.26 | -3.93 € |

### 🧠 Semáforo del Cerebro Cuantitativo (Decisiones de los Algoritmos)
| Mercado | Estrategia | Estado | Cierre | SMA200 | RSI(2) | IBS | Criterio / Motivo |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| DAX40 | `idx_dax_bollinger_dip` | 🟡 *ESPERA* | 25375.45 | 24885.88 | 60.4 | 0.63 | RSI(2) neutral (60.4 >= 15.0); Precio dentro de bandas Bollinger (25375.45 > 24975.81) |
| SP500 | `idx_rsi2_dip_regime` | 🟡 *ESPERA* | 7678.07 | 7306.38 | 55.5 | 0.71 | RSI(2) neutral (55.5 >= 10.0) |
| EURUSD | `fx_eurusd_ker_exhaustion` | 🟡 *ESPERA* | 1.12 | 1.16 | 5.7 | 0.02 | Precio (1.12) < SMA200 (1.16) [Tendencia bajista]; Mercado en rango / no tendencial (KER10=0.07 < 0.42); Sin extremo de agotamiento en bandas 2.0σ (RSI2=5.7) |
| IBEX35 | `idx_ibex_bollinger_dip` | 🟡 *ESPERA* | 18987.85 | 18649.13 | 43.4 | 0.74 | RSI(2) neutral (43.4 >= 10.0); Precio dentro de bandas Bollinger (18987.85 > 18852.13) |

### 🛡️ Transparencia de Costes y Comisiones
- **Broker Demo Actual:** Admirals DEMO `#58678879` (Cuenta Trade.MT5: comisión 0.00 EUR en broker; coste integrado en spread).
- **Modelo Cuantitativo Auditado:** IC Markets Raw ECN (Forex: comisión 3.50 USD/lado = ~6.30 EUR/lote round-trip + 0.1 pip spread crudo; Índices: 1.0 pt DAX / 0.4 pt SP500).
- **Spread y Deslizamiento:** Descontados causalmente al Bid/Ask en cada señal y ejecución.

---
*Actualizado automáticamente desde el motor local en segundo plano.*