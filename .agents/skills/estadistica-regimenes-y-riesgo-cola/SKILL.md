---
name: estadistica-regimenes-y-riesgo-cola
description: >-
  Estadística avanzada de series temporales financieras, detección de regímenes
  de mercado (Ratio de Eficiencia de Kaufman, Exponente de Hurst, compresión de
  volatilidad), intervalos de confianza binomiales de Wilson para tasas de
  acierto (>= 79%) y control de riesgo de cola (Expected Shortfall / CVaR).
---

# Skill: Estadística de Series Temporales, Regímenes de Mercado y Riesgo de Cola

Activa esta skill para clasificar matemáticamente el estado del mercado (Tendencia vs. Reversión vs. Ruido) y auditar con rigor estadístico si una tasa de acierto observada ($\ge 79\%$) es estadísticamente significativa.

---

## 1. Detección Estadística de Regímenes de Mercado (Causal)

Un mismo activo alterna entre fases de **persistencia (tendencia)**, **antipersistencia (reversión a la media)** y **ruido browniano puro**. Operar una estrategia tendencial en un régimen de reversión (o viceversa) hunde la tasa de acierto.

### 1.1 Ratio de Eficiencia de Kaufman ($ER_n$, *Efficiency Ratio*)
Mide la relación entre el desplazamiento neto y la suma de movimientos absolutos en una ventana de $n$ barras cerradas (típicamente $n = 20$):
$$ER_t(n) = \frac{|C_t - C_{t-n}|}{\sum_{k=t-n+1}^{t} |C_k - C_{k-1}|} \in [0, 1]$$
- **$ER_t \ge 0.35$**: Movimiento direccional limpio (alta relación señal/ruido). Ideal para **Pullbacks de Continuación y Breakouts**.
- **$ER_t \le 0.18$**: Mercado lateral / picadora de carne (*chop*). Ideal para **Reversión a la Media** en extremos de banda o **abstención (`NO_TRADE`)** en estrategias tendenciales.

### 1.2 Estimador Rápido de Persistencia / Varianza Relativa (*Variance Ratio* $VR(q)$)
Para distinguir tendencia de reversión sin el coste computacional de R/S Hurst:
$$VR_t(q) = \frac{\text{Var}(r_t^{(q)})}{q \cdot \text{Var}(r_t^{(1)})}$$
donde $r_t^{(1)} = \ln(C_t / C_{t-1})$ y $r_t^{(q)} = \ln(C_t / C_{t-q})$ (ej. $q = 4$ u $8$ barras).
- **$VR(q) > 1.05$**: Autocorrelación positiva (persistencia / momento).
- **$VR(q) < 0.95$**: Autocorrelación negativa (reversión a la media).
- **$VR(q) \approx 1.00$**: Paseo aleatorio puro $\implies$ exigir máxima selectividad ML.

### 1.3 Compresión de Volatilidad (*Squeeze Regime*)
Razón entre la desviación típica de 20 periodos y el ATR de 20 periodos:
$$\text{Squeeze\_Ratio}_t = \frac{2 \cdot \sigma_{20}(C)_t}{1.5 \cdot \text{ATR}_{20, t}}$$
- Cuando $\text{Squeeze\_Ratio}_t < 1.0$, las Bandas de Bollinger están dentro de los Canales de Keltner (compresión institucional previa a expansión).

---

## 2. Auditoría Estadística de una Tasa de Acierto ($\ge 79\%$)

Obtener un $80\%$ de acierto en $N = 10$ operaciones no demuestra nada (puede ocurrir por azar). Para validar científicamente que un modelo tiene una tasa de acierto real $W$, aplicamos:

### 2.1 Intervalo de Confianza Binomial de Wilson (Wilson Score Interval)
Dado un número de operaciones $N$ y una proporción observada de aciertos $\hat{p} = \frac{k}{N}$, el límite inferior del intervalo de confianza al nivel $1 - \alpha$ (ej. $90\%$ o $95\%$, con $z = 1.645$ o $1.96$) es:
$$W_{\text{lower}} = \frac{\hat{p} + \frac{z^2}{2N} - z \sqrt{\frac{\hat{p}(1 - \hat{p})}{N} + \frac{z^2}{4N^2}}}{1 + \frac{z^2}{N}}$$
- *Regla de calidad*: Al comparar dos candidatos con alta tasa de acierto ($\hat{p} \ge 0.79$), priorizar siempre el que tenga **mayor límite inferior de Wilson ($W_{\text{lower}}$)** y mayor tamaño muestral $N$.

### 2.2 Control de Riesgo de Cola (Left-Tail Risk / CVaR en Sistemas de Alto Win Rate)
El único punto débil de las estrategias con Win Rate $\ge 79\%$ es la **asimetría negativa (*negative skewness*)**: ganar muchas veces $+0.55R$ pero sufrir pérdidas aisladas de $-1.5R$ o $-2.0R$ por deslizamiento o gaps.
Para blindar el modelo:
1. **Ratio de Cola (*Tail Ratio*) y Pérdida Máxima Acotada**:
   - Verificar que la pérdida media real $\bar{R}_{\text{loss}}$ nunca supere $1.25 \times R_{\text{teórico}}$ en el escenario de estrés.
2. **Expected Shortfall / CVaR al 5% ($ES_{0.05}$)**:
   - Calcular la media del $5\%$ de peores operaciones cerradas:
     $$ES_{0.05} = \mathbb{E}[R \mid R \le Q_{0.05}(R)]$$
   - Rechazar cualquier configuración cuyo $ES_{0.05} < -1.60R$.
3. **Probabilidad de Racha Perdedora ($k$ pérdidas seguidas)**:
   - Con $W = 0.80$ ($q = 1 - W = 0.20$), la probabilidad de sufrir $3$ pérdidas seguidas en una ventana de $N$ operaciones es baja ($q^3 = 0.008 = 0.8\%$ en un bloque de 3 trades), por lo que si en vivo ocurren **3 pérdidas consecutivas**, es señal estadística de **cambio de régimen o rotura de modelo** ($p < 0.01$) y debe activarse inmediatamente [`RiskPause`](file:///C:/Users/julix/.gemini/antigravity/scratch/algoritmo_trading_CO_PS/trading_v2/research/risk_pause.py) (`CONSECUTIVE_LOSS_HALT`).
