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

## 🛠️ Cómo Probar Estrategias de Repositorios de GitHub
Cuando encuentres un repositorio de trading algorítmico en GitHub:
1. **Pásame el enlace de GitHub** aquí en el chat.
2. Yo clonaré/analizaré el código de la estrategia, la programaré en el motor causal anti-lookahead (`trading_v2/strategies/github_imports/`).
3. Ejecutaremos el backtest de hasta 8.5 años de datos reales en MetaTrader 5 en los 4 activos principales.
4. Si el Win Rate es menor al 70%, o el Drawdown supera el 5%, **se descartará inmediatamente y se registrará en este cuadro con el motivo exacto**.
5. Si supera todos los filtros, pasará a la lista de **CANDIDATAS DE ALTA SEGURIDAD** para preparar el despliegue con capital real.
