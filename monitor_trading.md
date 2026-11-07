# 🤖 Monitor Cuantitativo V3 (Admirals DEMO)

**Última actualización:** `2026-11-07 01:12:53 (Hora España)` | `00:12:53 UTC`

### 💰 Estado de la Cuenta DEMO
- **Cuenta:** DEMO #58678879 (AdmiralsGroup-Demo)
- **Balance:** 3058.12 EUR
- **Equity Flotante:** 3058.12 EUR (0.00 EUR)
- **Historial Real:** 13 operaciones cerradas / 10 victorias (**76.9% Win Rate**, +58.21 EUR ganancia neta).

### ⚔️ Batalla de Modelos A/B en Vivo (Cuenta Real DEMO vs Operador Fantasma)

| Métrica / Parámetro | Modelo A (En Vivo DEMO) | Modelo B (Fantasma Híbrido 70/30) | Diferencial (B vs A) |
| :--- | :---: | :---: | :---: |
| **Arquitectura de Salida** | 100% Scalp (M15/M30) | 70% TP rápido + 30% Runner Trailing EMA20 | Runner dinámico de tendencia |
| **Estrategia Forex (EURUSD)** | M15 Scalp | H1 Mean Reversion (+40 pips / -35 pips) | Sin fricción de spread |
| **Riesgo por Operación** | **1.00%** (~30.58 €) | **1.00%** (~30.00 €) | Idéntico |
| **Filtro Macro / Campana A1** | ✅ Activo (DE, ES, EU, US) | ✅ Activo (DE, ES, EU, US) | Idéntico |
| **Balance Acumulado** | **3058.12 €** | **3000.00 €** | **-58.12 €** |
| **Equity Flotante** | **3058.12 €** | **3000.00 €** | **-58.12 €** |
| **Operaciones Cerradas** | 13 | 0 | - |
| **Aciertos / Fallos** | 10W / 3L | 0W / 0L | - |
| **Tasa de Acierto (Win Rate)** | **76.9%** | **0.0%** | **-76.9%** |
| **PnL Neto Acumulado** | **+58.21 €** | **+0.00 €** | **-58.21 €** |
| **Posiciones Abiertas** | 0 | 0 | - |

### 📈 Posiciones Abiertas en Mercado Real (Modelo A)
*Sin posiciones abiertas en este momento.*

### 🧠 Semáforo del Cerebro Cuantitativo (Decisiones de los Algoritmos)
| Mercado | Estrategia | Estado | Cierre | SMA200 | RSI(2) | IBS | Criterio / Motivo |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| DAX40 | `idx_dax_bollinger_dip` | 🟡 *ESPERA* | 26200.64 | 24926.27 | 48.4 | 0.02 | RSI(2) neutral (48.4 >= 15.0); Precio dentro de bandas Bollinger (26200.64 > 24898.29) |
| IBEX35 | `idx_ibex_bollinger_dip` | 🟡 *ESPERA* | 19388.47 | 18706.23 | 72.4 | 0.14 | RSI(2) neutral (72.4 >= 10.0); Precio dentro de bandas Bollinger (19388.47 > 18637.24) |
| EURUSD | `fx_eurusd_ker_exhaustion` | 🟡 *ESPERA* | 1.12 | 1.15 | 67.6 | 0.24 | Precio (1.12) < SMA200 (1.15) [Tendencia bajista]; Mercado en rango / no tendencial (KER10=0.01 < 0.42); Sin extremo de agotamiento en bandas 2.0σ (RSI2=67.6) |
| DOW30 | `idx_rsi2_dip_regime` | 🟡 *ESPERA* | 51237.61 | 50729.42 | 28.4 | 0.00 | RSI(2) neutral (28.4 >= 10.0) |
| ORO | `idx_rsi2_dip_regime` | 🟡 *ESPERA* | 4088.78 | 4468.18 | 87.4 | 0.35 | Precio (4088.78) < SMA200 (4468.18) [Tendencia bajista]; RSI(2) neutral (87.4 >= 10.0) |
| SP500 | `idx_rsi2_dip_regime` | 🟡 *ESPERA* | 7329.53 | 7333.90 | 15.3 | 0.01 | Precio (7329.53) < SMA200 (7333.90) [Tendencia bajista]; RSI(2) neutral (15.3 >= 10.0) |

### ⚡ Configuración y Salvaguardas en Producción
- **Timeframe Principal:** M30 (GERMANY40, US100, [DJI30], [SP500], GOLD) / M15 ([IBEX35]) / H1 (EURUSD en Fantasma).
- **Riesgo por Operación:** **1.00%** (~30.58 EUR sobre balance en cuenta DEMO).
- **Filtro Macro:** Blindaje multi-país (DE, ES, EU, US) contra noticias de alto impacto Tier-1.
- **Filtro de Apertura (Opción A1):** Veto de 5 minutos post-campana Frankfurt (07:00 UTC), Madrid (08:00 UTC) y Wall Street (13:30 UTC).
- **Salvaguarda RiskPause:** Pausa de 60 min tras 2 pérdidas consecutivas; veto diario tras -1.5% sin reinicio.

---
*Actualizado automáticamente desde el motor local en segundo plano.*