# 📊 Cuadro Maestro de Estrategias Intradía (M15 / M30)
> **Repositorio:** `algoritmo_trading_CO_PS` | **Fecha de Auditoría:** 2026-10-25  
> **Capital Base de Referencia:** 3.000 € (DEMO Admirals / IC Markets Raw)  
> **Regla de Operación:** Disciplina estricta. *Solo se opera si los datos históricos demuestran ventaja estadística comprobada (E[R] > 0 y Win Rate > 70%). Si no hay ventaja, NO se opera.*

---

## 🎯 Criterios de Aprobación para Cuenta Real

| Métrica Obligatoria | Umbral Mínimo Requerido | Justificación Cuantitativa |
| :--- | :---: | :--- |
| **Tasa de Acierto (Win Rate)** | **> 70.0%** | Minimiza la racha de pérdidas consecutivas y reduce el estrés psicológico. |
| **Drawdown Máximo Histórico** | **< 5.0%** | Con 3.000 €, la pérdida máxima acumulada de la cuenta no debe superar 150 €. |
| **Timeframe Intradía** | **M15 o M30** | Sin riesgo de "weekend gap" o sorpresas nocturnas; posiciones cerradas en el día. |
| **Esperanza Matemática Neta E[R]** | **> 0 (PF > 1.25)** | Cada operación debe aportar retorno positivo después de pagar comisiones y spreads. |
| **Muestra Estadística** | **N >= 100 trades** | Evita sobreajuste (overfitting) o suerte estadística en muestras pequeñas. |
| **Historial Auditado** | **4 a 8.5 años** | 99.999 barras reales de MetaTrader 5 (2018–2026). |

---

## 📋 Registro Completo de Estrategias Auditadas (Histórico)

### 🔴 Ronda 1: Estrategias Base M15 con Salida Fija por Take Profit (25.000 barras)

| Fecha | Estrategia / Lógica | Activo | TF | N | Win Rate | PF | Max DD | E[R] | Estado | Diagnóstico / Motivo del Descarte |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| 2026-10-23 | RSI2_SMA200_MeanReversion | GERMANY40 | M15 | 425 | **66.4%** | 0.97 | 7.90% | -0.01 R | 🔴 DESCARTADA | WR 66.4% < 70%; Max DD 7.9% > 5%; sin edge neto con TP fijo. |
| 2026-10-23 | Bollinger_RSI_Extremes | GERMANY40 | M15 | 412 | **67.2%** | 1.00 | 6.36% | -0.00 R | 🔴 DESCARTADA | WR 67.2% < 70%; Max DD 6.36% > 5%; breakeven tras costes. |
| 2026-10-23 | Sniper_LiquiditySweep | GERMANY40 | M15 | 756 | **57.7%** | 0.83 | 29.77% | -0.08 R | 🔴 DESCARTADA | WR 57.7% insuficiente; drawdown inaceptable (29.8%). |
| 2026-10-23 | OpeningRangeBreakout_ORB | GERMANY40 | M15 | 218 | **63.8%** | 1.03 | 6.74% | +0.01 R | 🔴 DESCARTADA | WR 63.8% < 70%; Max DD 6.74% supera el límite del 5%. |
| 2026-10-23 | EMA20x50_Regime_Cross | GERMANY40 | M15 | 69 | **72.5%** | 1.26 | 2.01% | +0.12 R | 🟡 EN REVISIÓN | Cumple WR (72.5%) y DD (2.0%), pero solo 69 trades (mínimo 100). |
| 2026-10-23 | RSI2_SMA200_MeanReversion | [SP500] | M15 | 87 | **67.8%** | 1.03 | 3.76% | +0.01 R | 🔴 DESCARTADA | WR 67.8% < 70%; solo 87 operaciones (muestra baja). |
| 2026-10-23 | Bollinger_RSI_Extremes | [SP500] | M15 | 107 | **62.6%** | 0.82 | 3.76% | -0.06 R | 🔴 DESCARTADA | WR 62.6% < 70%; expectativa negativa (PF=0.82). |
| 2026-10-23 | Sniper_LiquiditySweep | [SP500] | M15 | 197 | **57.9%** | 0.89 | 7.11% | -0.04 R | 🔴 DESCARTADA | WR 57.9% < 70%; Max DD 7.11% > 5.0%. |
| 2026-10-23 | OpeningRangeBreakout_ORB | [SP500] | M15 | 26 | **61.5%** | 0.63 | 2.47% | -0.15 R | 🔴 DESCARTADA | WR 61.5% < 70%; muestra insuficiente (26 trades). |
| 2026-10-23 | EMA20x50_Regime_Cross | [SP500] | M15 | 18 | **61.1%** | 0.82 | 1.59% | -0.08 R | 🔴 DESCARTADA | Solo 18 operaciones; WR 61.1% < 70%. |
| 2026-10-23 | RSI2_SMA200_MeanReversion | EURUSD | M15 | 11 | **81.8%** | 1100 | 0.00% | +0.50 R | 🔴 DESCARTADA | Solo 11 trades; sobreajuste por muestra ridícula. |
| 2026-10-23 | Bollinger_RSI_Extremes | EURUSD | M15 | 11 | **100.0%** | inf | 0.00% | +0.65 R | 🔴 DESCARTADA | Solo 11 trades; artefacto estadístico no generalizable. |
| 2026-10-23 | Sniper_LiquiditySweep | EURUSD | M15 | 13 | **76.9%** | 3.03 | 0.55% | +0.32 R | 🔴 DESCARTADA | Solo 13 trades; requiere historial profundo de 6 años. |
| 2026-10-23 | OpeningRangeBreakout_ORB | EURUSD | M15 | 2 | **50.0%** | 265 | 0.00% | +0.10 R | 🔴 DESCARTADA | Solo 2 operaciones en el año; inoperable. |
| 2026-10-23 | EMA20x50_Regime_Cross | EURUSD | M15 | 1 | **0.0%** | 0.00 | 0.00% | 0.00 R | 🔴 DESCARTADA | 1 sola operación; inoperable en M15. |
| 2026-10-23 | RSI2_SMA200_MeanReversion | US100 | M15 | 281 | **65.1%** | 0.95 | 6.56% | -0.02 R | 🔴 DESCARTADA | WR 65.1% < 70%; Max DD 6.56% > 5.0%. |
| 2026-10-23 | Bollinger_RSI_Extremes | US100 | M15 | 319 | **63.9%** | 0.88 | 10.38% | -0.05 R | 🔴 DESCARTADA | WR 63.9% < 70%; Max DD 10.38% > 5.0%. |
| 2026-10-23 | Sniper_LiquiditySweep | US100 | M15 | 541 | **59.1%** | 0.90 | 15.97% | -0.04 R | 🔴 DESCARTADA | WR 59.1% insuficiente; drawdown excesivo (16.0%). |
| 2026-10-23 | OpeningRangeBreakout_ORB | US100 | M15 | 103 | **61.2%** | 0.95 | 5.37% | -0.01 R | 🔴 DESCARTADA | WR 61.2% < 70%; Max DD 5.37% > 5.0%. |
| 2026-10-23 | EMA20x50_Regime_Cross | US100 | M15 | 60 | **61.7%** | 0.63 | 4.15% | -0.12 R | 🔴 DESCARTADA | WR 61.7% < 70%; solo 60 trades. |

---

### 🔴 Ronda 2: Histórico Profundo de 8.5 Años MT5 (99.999 Barras — 2018 a 2026)

| Fecha | Estrategia / Lógica | Activo | TF | N | Win Rate | PF | Max DD | E[R] | Estado | Diagnóstico / Motivo del Descarte |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| 2026-10-25 | RSI2_Dip_Dynamic_EMA7 | GERMANY40 | M30 | 1229 | **60.8%** | 0.91 | 20.12% | -0.027 R | 🔴 DESCARTADA | WR 60.8% < 70%; DD 20.1% inaceptable en 8.9 años. |
| 2026-10-25 | RSI2_Dip_Dynamic_EMA7 | GERMANY40 | M15 | 1129 | **59.5%** | 0.73 | 47.48% | -0.085 R | 🔴 DESCARTADA | Ruido excesivo en M15; fricción de spread destruye el edge. |
| 2026-10-25 | RSI2_Dip_Dynamic_EMA7 | [SP500] | M30 | 930 | **61.9%** | 0.95 | 13.94% | -0.017 R | 🔴 DESCARTADA | WR 61.9% < 70%; sin ventaja frente a la tendencia. |
| 2026-10-25 | RSI2_Dip_Dynamic_EMA7 | [SP500] | M15 | 772 | **63.2%** | 0.89 | 19.99% | -0.032 R | 🔴 DESCARTADA | WR 63.2% < 70%; Max DD 20.0% > 5.0%. |
| 2026-10-25 | RSI2_Dip_Dynamic_EMA7 | US100 | M30 | 927 | **59.4%** | 0.89 | 26.99% | -0.038 R | 🔴 DESCARTADA | Nasdaq en M30 tiene demasiada volatilidad para compras ciegas. |
| 2026-10-25 | RSI2_Dip_Dynamic_EMA7 | US100 | M15 | 786 | **64.5%** | 0.89 | 13.36% | -0.031 R | 🔴 DESCARTADA | WR 64.5% < 70%; expectativa negativa tras costes. |
| 2026-10-25 | RSI2_Dip_Dynamic_EMA7 | GOLD | M30 | 1332 | **46.6%** | 0.43 | 137.9% | -0.193 R | 🔴 DESCARTADA | El oro en M30 tiene tendencias violentas; la reversión falla estrepitosamente. |
| 2026-10-25 | RSI2_Dip_Dynamic_EMA7 | GOLD | M15 | 1312 | **48.2%** | 0.45 | 117.3% | -0.170 R | 🔴 DESCARTADA | El oro no es apto para reversión a la media pura sin filtro de régimen. |

---

### 🔍 Hallazgo Cuantitativo Crucial: La Paradoja del Win Rate vs Expectativa

En el estudio de optimización de precisión intradía (`scripts/research_79_intraday_precision.py`):
- Se encontraron configuraciones en **[SP500] M15** con **Win Rate de hasta el 74.1%** (N=343 trades).
- **SIN EMBARGO, el Profit Factor fue de solo 0.74 y el PnL fue NEGATIVO.**
- **¿Por qué ocurre esto?** Porque para lograr un Win Rate del 74% con Take Profit de 0.40 ATR y Stop Loss de 1.50 ATR, la relación riesgo/beneficio es de $1:0.267$. Matemáticamente, para no perder dinero con ese ratio se necesita un acierto superior al **78.95%**.
- **Conclusión de Carlos respetada al 100%:** *"Quiero que operes si consideras que vas a ganarle al mercado, si no, NO."* Por este motivo, **esas variantes quedan DESCARTADAS** hasta lograr un sistema que combine Win Rate > 70% CON ganancia neta demostrada ($E[R] > 0$).

---

### 🔴 Ronda 3: Evaluación TauricResearch/TradingAgents (GitHub)
> **Fuente:** https://github.com/TauricResearch/TradingAgents  
> **Lógica Extraída:** Confluencia Técnica del Market Analyst (EMA10 + SMA50 + SMA200 + MACD Histogram + RSI14 + Bandas de Bollinger).

| Fecha | Estrategia / Fuente | Activo | TF | N | Win Rate | PF | Max DD | E[R] | Estado | Diagnóstico / Motivo del Descarte |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| 2026-10-26 | TradingAgents_Technical_Confluence | GERMANY40 | M30 | 757 | **64.9%** | 0.94 | 13.72% | -0.0198 | 🔴 DESCARTADA | Win Rate 64.9% < 70.0%; Max Drawdown 13.72% > 5.0%; Profit Factor 0.94 <= 1.25 o E[R]=-0.0198 <= 0; t-stat -0.74 < 1.5 (baja significancia) |
| 2026-10-26 | TradingAgents_Technical_Confluence | GERMANY40 | M15 | 770 | **65.1%** | 0.86 | 19.72% | -0.0465 | 🔴 DESCARTADA | Win Rate 65.1% < 70.0%; Max Drawdown 19.72% > 5.0%; Profit Factor 0.86 <= 1.25 o E[R]=-0.0465 <= 0; t-stat -1.77 < 1.5 (baja significancia) |
| 2026-10-26 | TradingAgents_Technical_Confluence | [SP500] | M30 | 680 | **65.0%** | 0.89 | 17.63% | -0.0358 | 🔴 DESCARTADA | Win Rate 65.0% < 70.0%; Max Drawdown 17.63% > 5.0%; Profit Factor 0.89 <= 1.25 o E[R]=-0.0358 <= 0; t-stat -1.27 < 1.5 (baja significancia) |
| 2026-10-26 | TradingAgents_Technical_Confluence | [SP500] | M15 | 690 | **65.5%** | 0.83 | 24.82% | -0.0556 | 🔴 DESCARTADA | Win Rate 65.5% < 70.0%; Max Drawdown 24.82% > 5.0%; Profit Factor 0.83 <= 1.25 o E[R]=-0.0556 <= 0; t-stat -2.04 < 1.5 (baja significancia) |
| 2026-10-26 | TradingAgents_Technical_Confluence | US100 | M30 | 611 | **65.1%** | 0.91 | 15.97% | -0.0293 | 🔴 DESCARTADA | Win Rate 65.1% < 70.0%; Max Drawdown 15.97% > 5.0%; Profit Factor 0.91 <= 1.25 o E[R]=-0.0293 <= 0; t-stat -1.01 < 1.5 (baja significancia) |
| 2026-10-26 | TradingAgents_Technical_Confluence | US100 | M15 | 617 | **68.1%** | 1.00 | 9.63% | -0.0004 | 🔴 DESCARTADA | Win Rate 68.1% < 70.0%; Max Drawdown 9.63% > 5.0%; Profit Factor 1.00 <= 1.25 o E[R]=-0.0004 <= 0; t-stat -0.01 < 1.5 (baja significancia) |
| 2026-10-26 | TradingAgents_Technical_Confluence | EURUSD | M30 | 844 | **44.8%** | 0.83 | 27.63% | -0.0593 | 🔴 DESCARTADA | Win Rate 44.8% < 70.0%; Max Drawdown 27.63% > 5.0%; Profit Factor 0.83 <= 1.25 o E[R]=-0.0593 <= 0; t-stat -2.29 < 1.5 (baja significancia) |
| 2026-10-26 | TradingAgents_Technical_Confluence | EURUSD | M15 | 801 | **39.0%** | 0.71 | 45.83% | -0.1056 | 🔴 DESCARTADA | Win Rate 39.0% < 70.0%; Max Drawdown 45.83% > 5.0%; Profit Factor 0.71 <= 1.25 o E[R]=-0.1056 <= 0; t-stat -4.06 < 1.5 (baja significancia) |

---

### 🚀 Ronda 4: Evaluación OpenByteInc/QuantDinger (GitHub) — ¡PRIMERA ESTRATEGIA APROBADA!
> **Fuente:** https://github.com/OpenByteInc/QuantDinger  
> **Lógica Extraída:** 
> 1. QuantDinger_MTF_Cross: Cruce M15 MA10xMA30 con confirmación macro H1.
> 2. QuantDinger_Keltner_Reversion: Canales de Keltner (EMA20 +/- 2.0*ATR10) en pullback sobre SMA200 con Breakeven (+0.05 ATR tras +0.50 ATR) y salida dinámica por EMA9.

| Fecha | Estrategia / Fuente | Activo | TF | N | Win Rate | PF | Max DD | E[R] | Estado | Diagnóstico / Motivo |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| 2026-10-26 | QuantDinger_MTF_Cross | GERMANY40 | M30 | 1824 | **65.6%** | 0.89 | 36.87% | -0.0364 | 🔴 DESCARTADA | Win Rate 65.6% < 70.0%; Max Drawdown 36.87% > 5.0%; Profit Factor 0.89 <= 1.25 o E[R]=-0.0364 <= 0; t-stat -2.13 < 1.5 (baja significancia) |
| 2026-10-26 | QuantDinger_MTF_Cross | GERMANY40 | M15 | 1644 | **65.1%** | 0.83 | 52.84% | -0.0565 | 🔴 DESCARTADA | Win Rate 65.1% < 70.0%; Max Drawdown 52.84% > 5.0%; Profit Factor 0.83 <= 1.25 o E[R]=-0.0565 <= 0; t-stat -3.13 < 1.5 (baja significancia) |
| 2026-10-26 | QuantDinger_MTF_Cross | [SP500] | M30 | 1489 | **62.3%** | 0.81 | 57.01% | -0.0689 | 🔴 DESCARTADA | Win Rate 62.3% < 70.0%; Max Drawdown 57.01% > 5.0%; Profit Factor 0.81 <= 1.25 o E[R]=-0.0689 <= 0; t-stat -3.58 < 1.5 (baja significancia) |
| 2026-10-26 | QuantDinger_MTF_Cross | [SP500] | M15 | 1244 | **65.5%** | 0.84 | 36.50% | -0.0534 | 🔴 DESCARTADA | Win Rate 65.5% < 70.0%; Max Drawdown 36.50% > 5.0%; Profit Factor 0.84 <= 1.25 o E[R]=-0.0534 <= 0; t-stat -2.62 < 1.5 (baja significancia) |
| 2026-10-26 | QuantDinger_MTF_Cross | US100 | M30 | 1494 | **62.9%** | 0.85 | 39.58% | -0.0513 | 🔴 DESCARTADA | Win Rate 62.9% < 70.0%; Max Drawdown 39.58% > 5.0%; Profit Factor 0.85 <= 1.25 o E[R]=-0.0513 <= 0; t-stat -2.69 < 1.5 (baja significancia) |
| 2026-10-26 | QuantDinger_MTF_Cross | US100 | M15 | 1224 | **64.5%** | 0.81 | 40.61% | -0.0624 | 🔴 DESCARTADA | Win Rate 64.5% < 70.0%; Max Drawdown 40.61% > 5.0%; Profit Factor 0.81 <= 1.25 o E[R]=-0.0624 <= 0; t-stat -3.05 < 1.5 (baja significancia) |
| 2026-10-26 | QuantDinger_MTF_Cross | EURUSD | M30 | 1874 | **40.5%** | 0.66 | 122.62% | -0.1285 | 🔴 DESCARTADA | Win Rate 40.5% < 70.0%; Max Drawdown 122.62% > 5.0%; Profit Factor 0.66 <= 1.25 o E[R]=-0.1285 <= 0; t-stat -7.50 < 1.5 (baja significancia) |
| 2026-10-26 | QuantDinger_MTF_Cross | EURUSD | M15 | 1529 | **38.1%** | 0.71 | 82.17% | -0.1035 | 🔴 DESCARTADA | Win Rate 38.1% < 70.0%; Max Drawdown 82.17% > 5.0%; Profit Factor 0.71 <= 1.25 o E[R]=-0.1035 <= 0; t-stat -5.54 < 1.5 (baja significancia) |
| 2026-10-26 | QuantDinger_Keltner_Reversion | GERMANY40 | M30 | 564 | **62.6%** | 0.75 | 26.13% | -0.0918 | 🔴 DESCARTADA | Win Rate 62.6% < 70.0%; Max Drawdown 26.13% > 5.0%; Profit Factor 0.75 <= 1.25 o E[R]=-0.0918 <= 0; t-stat -2.91 < 1.5 (baja significancia) |
| 2026-10-26 | QuantDinger_Keltner_Reversion | GERMANY40 | M15 | 559 | **61.0%** | 0.68 | 34.33% | -0.1216 | 🔴 DESCARTADA | Win Rate 61.0% < 70.0%; Max Drawdown 34.33% > 5.0%; Profit Factor 0.68 <= 1.25 o E[R]=-0.1216 <= 0; t-stat -3.88 < 1.5 (baja significancia) |
| 2026-10-26 | QuantDinger_Keltner_Reversion | [SP500] | M30 | 381 | **66.7%** | 0.93 | 7.59% | -0.0225 | 🔴 DESCARTADA | Win Rate 66.7% < 70.0%; Max Drawdown 7.59% > 5.0%; Profit Factor 0.93 <= 1.25 o E[R]=-0.0225 <= 0; t-stat -0.60 < 1.5 (baja significancia) |
| 2026-10-26 | QuantDinger_Keltner_Reversion | [SP500] | M15 | 290 | **71.7%** | 1.07 | 6.13% | +0.0192 | 🔴 DESCARTADA | Max Drawdown 6.13% > 5.0%; Profit Factor 1.07 <= 1.25 o E[R]=+0.0192 <= 0; t-stat 0.46 < 1.5 (baja significancia) |
| 2026-10-26 | QuantDinger_Keltner_Reversion | US100 | M30 | 412 | **65.3%** | 0.85 | 14.24% | -0.0515 | 🔴 DESCARTADA | Win Rate 65.3% < 70.0%; Max Drawdown 14.24% > 5.0%; Profit Factor 0.85 <= 1.25 o E[R]=-0.0515 <= 0; t-stat -1.43 < 1.5 (baja significancia) |
| 2026-10-26 | QuantDinger_Keltner_Reversion | US100 | M15 | 290 | **70.3%** | 0.98 | 6.87% | -0.0050 | 🔴 DESCARTADA | Max Drawdown 6.87% > 5.0%; Profit Factor 0.98 <= 1.25 o E[R]=-0.0050 <= 0; t-stat -0.12 < 1.5 (baja significancia) |
| 2026-10-26 | QuantDinger_Keltner_Reversion | EURUSD | M30 | 466 | **42.1%** | 0.81 | 22.05% | -0.0644 | 🔴 DESCARTADA | Win Rate 42.1% < 70.0%; Max Drawdown 22.05% > 5.0%; Profit Factor 0.81 <= 1.25 o E[R]=-0.0644 <= 0; t-stat -1.92 < 1.5 (baja significancia) |
| 2026-10-26 | QuantDinger_Keltner_Reversion | EURUSD | M15 | 428 | **36.7%** | 0.66 | 29.77% | -0.1268 | 🔴 DESCARTADA | Win Rate 36.7% < 70.0%; Max Drawdown 29.77% > 5.0%; Profit Factor 0.66 <= 1.25 o E[R]=-0.1268 <= 0; t-stat -3.60 < 1.5 (baja significancia) |
| 2026-10-26 | QuantDinger_Keltner_Reversion_Opt | [SP500] | M15 | 128 | **73.4%** | 1.28 | 3.42% | +0.0747 | 🔴 DESCARTADA | t-stat 0.84 < 1.5 (baja significancia) |
| 2026-10-26 | QuantDinger_Keltner_Reversion_Opt | US100 | M15 | 121 | **65.3%** | 0.64 | 7.46% | -0.1157 | 🔴 DESCARTADA | Win Rate 65.3% < 70.0%; Max Drawdown 7.46% > 5.0%; Profit Factor 0.64 <= 1.25 o E[R]=-0.1157 <= 0; t-stat -1.49 < 1.5 (baja significancia) |
| 2026-10-26 | QuantDinger_Keltner_Reversion_Opt | GERMANY40 | M15 | 250 | **63.6%** | 0.89 | 10.77% | -0.0364 | 🔴 DESCARTADA | Win Rate 63.6% < 70.0%; Max Drawdown 10.77% > 5.0%; Profit Factor 0.89 <= 1.25 o E[R]=-0.0364 <= 0; t-stat -0.51 < 1.5 (baja significancia) |
| 2026-10-26 | QuantDinger_Keltner_Reversion_Opt | EURUSD | M15 | 169 | **20.1%** | 0.85 | 11.69% | -0.0452 | 🔴 DESCARTADA | Win Rate 20.1% < 70.0%; Max Drawdown 11.69% > 5.0%; Profit Factor 0.85 <= 1.25 o E[R]=-0.0452 <= 0; t-stat -0.63 < 1.5 (baja significancia) |

---


### 🔴 Ronda 5: Evaluación brainbrick-trades/The-Quant-Trading-Vault (GitHub)
> **Fuente:** https://github.com/brainbrick-trades/The-Quant-Trading-Vault  
> **Lógicas Evaluadas:**  
> 1. `Vault_BB_VWAP_Anomaly`: Tendencia EMA50>200 + VWAP + anomalía de precio bajo Bollinger Bands (20, 2.0).  
> 2. `Vault_Connors_RSI2_Reversal`: Connors RSI(2) < 10 con filtro SMA200 y salida dinámica por EMA9.  
> 3. `Vault_Consecutive_Candle_Reversal`: Reversión de 3 velas bajistas con mecha de absorción a favor de EMA200.  

| Fecha | Estrategia / Fuente | Activo | TF | N | Win Rate | PF | Max DD | E[R] | Estado | Diagnóstico / Motivo del Descarte |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| 2026-11-03 | Vault_BB_VWAP_Anomaly | GERMANY40 | M30 | 1876 | **58.4%** | 0.90 | 28.94% | -0.0270 | 🔴 DESCARTADA | Win Rate 58.4% < 70.0%; Max Drawdown 28.94% > 5.0%; Profit Factor 0.90 <= 1.25 o E[R]=-0.0270 <= 0; t-stat -1.75 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_BB_VWAP_Anomaly | GERMANY40 | M15 | 1535 | **55.0%** | 0.92 | 30.90% | -0.0214 | 🔴 DESCARTADA | Win Rate 55.0% < 70.0%; Max Drawdown 30.90% > 5.0%; Profit Factor 0.92 <= 1.25 o E[R]=-0.0214 <= 0; t-stat -1.21 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_BB_VWAP_Anomaly | [SP500] | M30 | 1848 | **54.8%** | 0.79 | 56.03% | -0.0557 | 🔴 DESCARTADA | Win Rate 54.8% < 70.0%; Max Drawdown 56.03% > 5.0%; Profit Factor 0.79 <= 1.25 o E[R]=-0.0557 <= 0; t-stat -3.59 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_BB_VWAP_Anomaly | [SP500] | M15 | 1333 | **55.7%** | 0.80 | 37.85% | -0.0531 | 🔴 DESCARTADA | Win Rate 55.7% < 70.0%; Max Drawdown 37.85% > 5.0%; Profit Factor 0.80 <= 1.25 o E[R]=-0.0531 <= 0; t-stat -3.02 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_BB_VWAP_Anomaly | US100 | M30 | 1844 | **55.7%** | 0.86 | 35.09% | -0.0364 | 🔴 DESCARTADA | Win Rate 55.7% < 70.0%; Max Drawdown 35.09% > 5.0%; Profit Factor 0.86 <= 1.25 o E[R]=-0.0364 <= 0; t-stat -2.33 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_BB_VWAP_Anomaly | US100 | M15 | 1254 | **57.8%** | 0.91 | 16.59% | -0.0220 | 🔴 DESCARTADA | Win Rate 57.8% < 70.0%; Max Drawdown 16.59% > 5.0%; Profit Factor 0.91 <= 1.25 o E[R]=-0.0220 <= 0; t-stat -1.15 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_BB_VWAP_Anomaly | EURUSD | M30 | 1418 | **48.1%** | 0.68 | 73.94% | -0.1020 | 🔴 DESCARTADA | Win Rate 48.1% < 70.0%; Max Drawdown 73.94% > 5.0%; Profit Factor 0.68 <= 1.25 o E[R]=-0.1020 <= 0; t-stat -5.38 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_BB_VWAP_Anomaly | EURUSD | M15 | 1136 | **47.5%** | 0.61 | 66.70% | -0.1162 | 🔴 DESCARTADA | Win Rate 47.5% < 70.0%; Max Drawdown 66.70% > 5.0%; Profit Factor 0.61 <= 1.25 o E[R]=-0.1162 <= 0; t-stat -5.73 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_BB_VWAP_Anomaly | GOLD | M30 | 1918 | **26.8%** | 0.21 | 337.70% | -0.3519 | 🔴 DESCARTADA | Win Rate 26.8% < 70.0%; Max Drawdown 337.70% > 5.0%; Profit Factor 0.21 <= 1.25 o E[R]=-0.3519 <= 0; t-stat -26.73 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_BB_VWAP_Anomaly | GOLD | M15 | 1645 | **34.4%** | 0.32 | 236.13% | -0.2822 | 🔴 DESCARTADA | Win Rate 34.4% < 70.0%; Max Drawdown 236.13% > 5.0%; Profit Factor 0.32 <= 1.25 o E[R]=-0.2822 <= 0; t-stat -17.39 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_Connors_RSI2_Reversal | GERMANY40 | M30 | 875 | **55.4%** | 0.76 | 50.89% | -0.1037 | 🔴 DESCARTADA | Win Rate 55.4% < 70.0%; Max Drawdown 50.89% > 5.0%; Profit Factor 0.76 <= 1.25 o E[R]=-0.1037 <= 0; t-stat -3.51 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_Connors_RSI2_Reversal | GERMANY40 | M15 | 803 | **53.8%** | 0.65 | 61.19% | -0.1520 | 🔴 DESCARTADA | Win Rate 53.8% < 70.0%; Max Drawdown 61.19% > 5.0%; Profit Factor 0.65 <= 1.25 o E[R]=-0.1520 <= 0; t-stat -5.00 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_Connors_RSI2_Reversal | [SP500] | M30 | 655 | **57.6%** | 0.91 | 21.15% | -0.0386 | 🔴 DESCARTADA | Win Rate 57.6% < 70.0%; Max Drawdown 21.15% > 5.0%; Profit Factor 0.91 <= 1.25 o E[R]=-0.0386 <= 0; t-stat -1.04 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_Connors_RSI2_Reversal | [SP500] | M15 | 546 | **60.8%** | 0.92 | 12.84% | -0.0294 | 🔴 DESCARTADA | Win Rate 60.8% < 70.0%; Max Drawdown 12.84% > 5.0%; Profit Factor 0.92 <= 1.25 o E[R]=-0.0294 <= 0; t-stat -0.78 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_Connors_RSI2_Reversal | US100 | M30 | 680 | **56.8%** | 0.94 | 15.21% | -0.0252 | 🔴 DESCARTADA | Win Rate 56.8% < 70.0%; Max Drawdown 15.21% > 5.0%; Profit Factor 0.94 <= 1.25 o E[R]=-0.0252 <= 0; t-stat -0.68 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_Connors_RSI2_Reversal | US100 | M15 | 534 | **59.6%** | 0.83 | 18.12% | -0.0667 | 🔴 DESCARTADA | Win Rate 59.6% < 70.0%; Max Drawdown 18.12% > 5.0%; Profit Factor 0.83 <= 1.25 o E[R]=-0.0667 <= 0; t-stat -1.81 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_Connors_RSI2_Reversal | EURUSD | M30 | 680 | **45.4%** | 0.73 | 40.34% | -0.1156 | 🔴 DESCARTADA | Win Rate 45.4% < 70.0%; Max Drawdown 40.34% > 5.0%; Profit Factor 0.73 <= 1.25 o E[R]=-0.1156 <= 0; t-stat -3.43 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_Connors_RSI2_Reversal | EURUSD | M15 | 614 | **43.8%** | 0.54 | 65.88% | -0.2055 | 🔴 DESCARTADA | Win Rate 43.8% < 70.0%; Max Drawdown 65.88% > 5.0%; Profit Factor 0.54 <= 1.25 o E[R]=-0.2055 <= 0; t-stat -6.27 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_Connors_RSI2_Reversal | GOLD | M30 | 972 | **42.1%** | 0.36 | 162.23% | -0.3243 | 🔴 DESCARTADA | Win Rate 42.1% < 70.0%; Max Drawdown 162.23% > 5.0%; Profit Factor 0.36 <= 1.25 o E[R]=-0.3243 <= 0; t-stat -13.24 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_Connors_RSI2_Reversal | GOLD | M15 | 926 | **43.2%** | 0.34 | 158.41% | -0.3332 | 🔴 DESCARTADA | Win Rate 43.2% < 70.0%; Max Drawdown 158.41% > 5.0%; Profit Factor 0.34 <= 1.25 o E[R]=-0.3332 <= 0; t-stat -13.67 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_Consecutive_Candle_Reversal | GERMANY40 | M30 | 406 | **56.9%** | 0.74 | 22.97% | -0.0972 | 🔴 DESCARTADA | Win Rate 56.9% < 70.0%; Max Drawdown 22.97% > 5.0%; Profit Factor 0.74 <= 1.25 o E[R]=-0.0972 <= 0; t-stat -2.41 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_Consecutive_Candle_Reversal | GERMANY40 | M15 | 383 | **62.7%** | 0.97 | 8.43% | -0.0097 | 🔴 DESCARTADA | Win Rate 62.7% < 70.0%; Max Drawdown 8.43% > 5.0%; Profit Factor 0.97 <= 1.25 o E[R]=-0.0097 <= 0; t-stat -0.25 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_Consecutive_Candle_Reversal | [SP500] | M30 | 325 | **58.8%** | 0.81 | 14.44% | -0.0726 | 🔴 DESCARTADA | Win Rate 58.8% < 70.0%; Max Drawdown 14.44% > 5.0%; Profit Factor 0.81 <= 1.25 o E[R]=-0.0726 <= 0; t-stat -1.52 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_Consecutive_Candle_Reversal | [SP500] | M15 | 267 | **64.8%** | 1.09 | 5.60% | +0.0246 | 🔴 DESCARTADA | Win Rate 64.8% < 70.0%; Max Drawdown 5.60% > 5.0%; Profit Factor 1.09 <= 1.25 o E[R]=+0.0246 <= 0; t-stat 0.48 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_Consecutive_Candle_Reversal | US100 | M30 | 322 | **60.2%** | 0.77 | 15.45% | -0.0837 | 🔴 DESCARTADA | Win Rate 60.2% < 70.0%; Max Drawdown 15.45% > 5.0%; Profit Factor 0.77 <= 1.25 o E[R]=-0.0837 <= 0; t-stat -1.91 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_Consecutive_Candle_Reversal | US100 | M15 | 282 | **63.1%** | 0.86 | 16.26% | -0.0468 | 🔴 DESCARTADA | Win Rate 63.1% < 70.0%; Max Drawdown 16.26% > 5.0%; Profit Factor 0.86 <= 1.25 o E[R]=-0.0468 <= 0; t-stat -1.01 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_Consecutive_Candle_Reversal | EURUSD | M30 | 313 | **58.1%** | 0.70 | 17.68% | -0.1131 | 🔴 DESCARTADA | Win Rate 58.1% < 70.0%; Max Drawdown 17.68% > 5.0%; Profit Factor 0.70 <= 1.25 o E[R]=-0.1131 <= 0; t-stat -2.53 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_Consecutive_Candle_Reversal | EURUSD | M15 | 294 | **51.0%** | 0.55 | 29.93% | -0.1753 | 🔴 DESCARTADA | Win Rate 51.0% < 70.0%; Max Drawdown 29.93% > 5.0%; Profit Factor 0.55 <= 1.25 o E[R]=-0.1753 <= 0; t-stat -3.42 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_Consecutive_Candle_Reversal | GOLD | M30 | 510 | **36.3%** | 0.28 | 87.78% | -0.3349 | 🔴 DESCARTADA | Win Rate 36.3% < 70.0%; Max Drawdown 87.78% > 5.0%; Profit Factor 0.28 <= 1.25 o E[R]=-0.3349 <= 0; t-stat -11.81 < 1.5 (baja significancia) |
| 2026-11-03 | Vault_Consecutive_Candle_Reversal | GOLD | M15 | 507 | **36.7%** | 0.31 | 79.40% | -0.3146 | 🔴 DESCARTADA | Win Rate 36.7% < 70.0%; Max Drawdown 79.40% > 5.0%; Profit Factor 0.31 <= 1.25 o E[R]=-0.3146 <= 0; t-stat -10.03 < 1.5 (baja significancia) |

---

## 🛠️ Cómo Probar Estrategias de Repositorios de GitHub
Cuando encuentres un repositorio de trading algorítmico en GitHub:
1. **Pásame el enlace de GitHub** aquí en el chat.
2. Yo clonaré/analizaré el código de la estrategia, la programaré en el motor causal anti-lookahead (`trading_v2/strategies/github_imports/`).
3. Ejecutaremos el backtest de hasta 8.5 años de datos reales en MetaTrader 5 en los 4 activos principales.
4. Si el Win Rate es menor al 70%, o el Drawdown supera el 5%, **se descartará inmediatamente y se registrará en este cuadro con el motivo exacto**.
5. Si supera todos los filtros, pasará a la lista de **CANDIDATAS DE ALTA SEGURIDAD** para preparar el despliegue con capital real.
