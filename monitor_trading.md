# 🤖 Monitor Cuantitativo V3 (Admirals DEMO)

**Última actualización:** `2026-11-02 23:30:55 (Hora España)` | `22:30:55 UTC`

### 💰 Estado de la Cuenta
- **Cuenta:** DEMO #58678879 (AdmiralsGroup-Demo)
- **Balance:** 3049.82 EUR
- **Equity Flotante:** 3049.82 EUR (0.00 EUR)
- **Historial Real:** 4 operaciones cerradas / 4 victorias (**100% Win Rate**, +49.82 EUR ganancia neta).

### 📈 Posiciones Abiertas
*Sin posiciones abiertas en este momento.*

### 🧠 Semáforo del Cerebro Cuantitativo (Decisiones de los Algoritmos)
| Mercado | Estrategia | Estado | Cierre | SMA200 | RSI(2) | IBS | Criterio / Motivo |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| DAX40 | `idx_dax_bollinger_dip` | 🟡 *ESPERA* | 25780.02 | 24901.23 | 44.4 | 0.27 | RSI(2) neutral (44.4 >= 15.0); Precio dentro de bandas Bollinger (25780.02 > 24931.91) |
| IBEX35 | `idx_ibex_bollinger_dip` | 🟡 *ESPERA* | 18548.99 | 18674.74 | 7.0 | 0.08 | Precio (18548.99) < SMA200 (18674.74) [Tendencia bajista]; RSI(2) en sobreventa (7.0 < 10.0); Precio en agotamiento inferior Bollinger 2.0σ (18548.99 <= 18694.90) |
| EURUSD | `fx_eurusd_ker_exhaustion` | 🟡 *ESPERA* | 1.12 | 1.16 | 74.9 | 0.46 | Precio (1.12) < SMA200 (1.16) [Tendencia bajista]; Mercado en rango / no tendencial (KER10=0.11 < 0.42); Sin extremo de agotamiento en bandas 2.0σ (RSI2=74.9) |
| DOW30 | `idx_rsi2_dip_regime` | 🟢 **COMPRA** | 51762.09 | 50668.47 | 8.4 | 0.23 | RSI(2) en sobreventa extrema (8.4 < 10.0) |
| ORO | `idx_rsi2_dip_regime` | 🟡 *ESPERA* | 3875.28 | 4491.02 | 4.8 | 0.03 | Precio (3875.28) < SMA200 (4491.02) [Tendencia bajista]; RSI(2) en sobreventa extrema (4.8 < 10.0) |
| SP500 | `idx_rsi2_dip_regime` | 🟢 **COMPRA** | 7580.52 | 7322.45 | 7.2 | 0.35 | RSI(2) en sobreventa extrema (7.2 < 10.0) |

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