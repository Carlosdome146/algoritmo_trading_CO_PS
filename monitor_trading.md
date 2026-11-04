# 🤖 Monitor Cuantitativo V3 (Admirals DEMO)

**Última actualización:** `2026-11-04 17:53:34 (Hora España)` | `16:53:34 UTC`

### 💰 Estado de la Cuenta
- **Cuenta:** DEMO #58678879 (AdmiralsGroup-Demo)
- **Balance:** 3076.80 EUR
- **Equity Flotante:** 3076.80 EUR (0.00 EUR)
- **Historial Real:** 11 operaciones cerradas / 9 victorias (**81.8% Win Rate**, +76.89 EUR ganancia neta).

### 📈 Posiciones Abiertas
*Sin posiciones abiertas en este momento.*

### 🧠 Semáforo del Cerebro Cuantitativo (Decisiones de los Algoritmos)
| Mercado | Estrategia | Estado | Cierre | SMA200 | RSI(2) | IBS | Criterio / Motivo |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| DAX40 | `idx_dax_bollinger_dip` | 🟡 *ESPERA* | 25816.61 | 24911.31 | 43.9 | 0.42 | RSI(2) neutral (43.9 >= 15.0); Precio dentro de bandas Bollinger (25816.61 > 24925.97) |
| IBEX35 | `idx_ibex_bollinger_dip` | 🟡 *ESPERA* | 18802.39 | 18688.20 | 46.4 | 0.31 | RSI(2) neutral (46.4 >= 10.0); Precio dentro de bandas Bollinger (18802.39 > 18676.57) |
| EURUSD | `fx_eurusd_ker_exhaustion` | 🟡 *ESPERA* | 1.12 | 1.16 | 78.2 | 0.52 | Precio (1.12) < SMA200 (1.16) [Tendencia bajista]; Mercado en rango / no tendencial (KER10=0.22 < 0.42); Sin extremo de agotamiento en bandas 2.0σ (RSI2=78.2) |
| DOW30 | `idx_rsi2_dip_regime` | 🟡 *ESPERA* | 51663.00 | 50695.73 | 20.8 | 0.30 | RSI(2) neutral (20.8 >= 10.0) |
| ORO | `idx_rsi2_dip_regime` | 🟡 *ESPERA* | 3929.99 | 4480.43 | 38.9 | 0.46 | Precio (3929.99) < SMA200 (4480.43) [Tendencia bajista]; RSI(2) neutral (38.9 >= 10.0) |
| SP500 | `idx_rsi2_dip_regime` | 🟡 *ESPERA* | 7578.44 | 7328.49 | 36.1 | 0.79 | RSI(2) neutral (36.1 >= 10.0) |

### ⚡ Estrategia Universal en Producción: `institutional_sniper_scalp` (Micro-Sweep Reclaim)
- **Timeframe:** M15 (EURUSD, [IBEX35]) / M30 (GERMANY40, US100, [DJI30], [SP500], GOLD).
- **Riesgo por Operación:** **1.50%** (~45.75 EUR de presupuesto de riesgo por operación sobre balance).
- **Beneficio Estimado por Acierto:** **+25.00 EUR a +35.00 EUR** netos.
- **Límites de operaciones:** **SIN LÍMITE ARTIFICIAL** (`max_trades_per_day = None`). Cada oportunidad de calidad se ejecuta.
- **Cooldown:** 2 velas (EURUSD) / 3 velas (Índices y Materias Primas).

### 📊 Desglose de Extrapolación de Cartera (Backtesting Octubre 2026 en MT5 Real)
*Rendimiento conjunto de los 7 activos con spread real de broker y Breakeven Causal:*

| Activo | Símbolo MT5 | TF | Dirección | Trades Oct-26 | Win Rate | Profit Factor | PnL Neto Octubre (1.5% Riesgo) | Retorno R | Salida (TP / SL) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **EUR / USD** | `EURUSD` | M15 | **Bidireccional** | 41 | **80.5%** | 1.72 | **+299.70 EUR** | +6.20 R | TP: 3.5 pips / SL: 5.5 pips |
| **Dow Jones 30** | `[DJI30]` | M30 | Long Only | 8 | **100.0%** | INF | **+213.58 EUR** | +3.85 R | TP: 40.0 pts / SL: 80.0 pts |
| **DAX 40** | `GERMANY40` | M30 | **Bidireccional** | 15 | **80.0%** | 1.83 | **+124.66 EUR** | +2.53 R | TP: 22.0 pts / SL: 35.0 pts |
| **IBEX 35** | `[IBEX35]` | M15 | Long Only | 15 | **86.7%** | 2.10 | **+114.05 EUR** | +2.32 R | TP: 20.0 pts / SL: 45.0 pts |
| **Nasdaq 100** | `US100` | M30 | **Bidireccional** | 21 | **85.7%** | 1.62 | **+99.36 EUR** | +1.87 R | TP: 25.0 pts / SL: 70.0 pts |
| **S&P 500** | `[SP500]` | M30 | Long Only | 13 | **92.3%** | 2.56 | **+88.84 EUR** | +1.60 R | TP: 4.0 pts / SL: 12.0 pts |
| **Oro Spot** | `GOLD` | M30 | Long Only | 13 | **92.3%** | 2.34 | **+75.19 EUR** | +1.35 R | TP: 4.0 $ / SL: 15.0 $ |
| **TOTAL CARTERA** | **7 ACTIVOS** | - | - | **126** | **85.71%** | **2.05** | **+1,015.37 EUR (+33.85%)** | **+19.72 R** | **DD Máx: 8.90%** |

### 🛡️ Salvaguardas y Control de Riesgo
- **Broker Conectado:** Admirals DEMO `#58678879` (Cuenta Trade.MT5).
- **RiskPause:** Pausa de 60 min tras 2 pérdidas consecutivas; veto diario tras -1.5% sin reinicio automático.
- **Gestión Dinámica:** Breakeven Causal se activa al 35-45% del TP para proteger el capital.

---
*Actualizado automáticamente desde el motor local en segundo plano.*