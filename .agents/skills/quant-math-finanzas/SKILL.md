---
name: quant-math-finanzas
description: >-
  Matemática cuantitativa avanzada, estadística financiera (Marcos López de Prado),
  probabilidad de primera pasada (First-Passage Time), calibración de probabilidades
  (Brier Score / Platt / Isotonic), Deflated Sharpe Ratio y criterio de Kelly para
  diseño y auditoría de modelos de trading con alta tasa de acierto (>= 75%).
---

# Skill: Matemática Cuantitativa y Estadística Financiera (`quant-math-finanzas`)

Activa esta skill siempre que diseñes, audites o entrenes estrategias cuantitativas, sistemas de etiquetado (Triple Barrier), filtros de Machine Learning (Meta-Labeling) o dimensionamiento de posiciones.

---

## 1. Ecuación Fundamental de Rentabilidad y Tasa de Acierto ($W$)

Sea:
- $W \in (0, 1)$ la tasa de acierto real (*Win Rate*).
- $R_{\text{win}} > 0$ la ganancia media neta (en múltiplos del riesgo inicial $1R$, descontados spread y deslizamiento).
- $R_{\text{loss}} > 0$ la pérdida media neta en múltiplos de $R$ (normalmente $R_{\text{loss}} \ge 1.0$ por spread y gaps).

### 1.1 Esperanza Matemática Neta por Operación ($E[R]$)
$$E[R] = W \cdot R_{\text{win}} - (1 - W) \cdot R_{\text{loss}}$$

Para que el sistema sea rentable ($E[R] > 0$), la tasa de acierto mínima de equilibrio (*Breakeven Win Rate*, $W_{\min}$) es:
$$W_{\min} = \frac{R_{\text{loss}}}{R_{\text{win}} + R_{\text{loss}}}$$

### 1.2 Profit Factor ($PF$) en función de $W$ y del Ratio Payoff ($\rho = R_{\text{win}} / R_{\text{loss}}$)
$$PF = \frac{W \cdot R_{\text{win}}}{(1 - W) \cdot R_{\text{loss}}} = \frac{W}{1 - W} \cdot \rho$$

### 1.3 Teorema de Primera Pasada (First-Passage Time) en Barreras Simétricas/Asimétricas
En un proceso de difusión intradía con deriva local $\mu \approx 0$ entre la barrera superior $+TP$ y la barrera inferior $-SL$, con coste de spread + slippage total $c > 0$:
- Distancia efectiva al objetivo: $\Delta_{+} = TP + c$
- Distancia efectiva al stop: $\Delta_{-} = SL - c$

La probabilidad base sin ventaja direccional ($P_0$) de tocar primero el $TP$ antes del $SL$ es:
$$P_0(\text{hit } TP) = \frac{\Delta_{-}}{\Delta_{+} + \Delta_{-}} = \frac{SL - c}{TP + SL}$$

> **Corolario Crítico para el Objetivo $W \ge 0.75$ (75% Win Rate):**
> - Si se fija $TP = 1.8 \text{ ATR}$ y $SL = 1.2 \text{ ATR}$, entonces $P_0 < \frac{1.2 - c}{3.0} < 40\%$. Alcanzar $W \ge 75\%$ exigiría un sesgo direccional de $+35\%$ sobre el azar en cada vela, lo cual provoca que los clasificadores filtren el $99\text{–}100\%$ de las señales (`0 trades`).
> - Para lograr $W \ge 0.75$ con $PF \ge 1.30$ y tamaño muestral estadísticamente válido ($N \ge 30$), es **matemáticamente obligatorio** combinar:
>   1. **Geometría de Salida de Alta Probabilidad o Salida en 2 Etapas (Partial TP / Breakeven diferido)**:
>      - Ejemplo A (*High-Probability Target*): $TP = 0.65 \text{ ATR}$, $SL = 1.10 \text{ ATR}$ $\implies P_0 \approx 60\%$. Con filtro direccional + microestructura ($\Delta W \approx +16\%$), se alcanza $W \approx 76\%$, dando $E[R] = 0.76(0.60) - 0.24(1.15) = +0.18R > 0$ y $PF = \frac{0.456}{0.276} = 1.65$.
>      - Ejemplo B (*Two-Stage / Breakeven Lock tras vela cerrada*): Si la vela $j$ cierra con beneficio latente $\ge +0.60 \text{ ATR}$, mover el Stop Loss para las velas posteriores $k > j$ a $\text{Entry} + c_{\text{buffer}}$ (+0.10R). Esto convierte los giros tardíos en salidas ligeramente positivas ($+0.05R$ a $+0.10R$) en lugar de pérdidas de $-1.0R$.
>   2. **Control estricto del coste relativo ($\kappa = \frac{\text{Spread} \cdot \text{Point}}{\text{ATR}}$)**:
>      - Si $\kappa > 0.08$ (el spread consume más del $8\%$ del ATR de M15), la erosión de $P_0$ destruye la esperanza matemática. Toda señal con $\kappa > \kappa_{\max}$ debe vetarse.

---

## 2. Estadística de Machine Learning Financiero (Estándar López de Prado)

### 2.1 Ponderación por Unicidad (Sample Uniqueness) ante Eventos Solapados
Cuando dos señales en M15 ocurren en $t_1$ y $t_2$ con $t_2 < t_1 + h$, sus horizontes $[t_1, t_1+h]$ y $[t_2, t_2+h]$ se solapan (no son i.i.d.).
- Definir la concurrencia en la barra $t$ como $c_t = \sum_{i} \mathbb{I}(t \in [t_{i,\text{start}}, t_{i,\text{exit}}])$.
- La unicidad media del evento $i$ es:
  $$\bar{u}_i = \left( \frac{1}{t_{i,\text{exit}} - t_{i,\text{start}} + 1} \sum_{t=t_{i,\text{start}}}^{t_{i,\text{exit}}} \frac{1}{c_t} \right)$$
- Ponderar cada muestra en `model.fit(X, y, sample_weight=w)` usando:
  $$w_i = \bar{u}_i \cdot |R_i|$$
  para que el clasificador priorice eventos independientes y de mayor impacto económico.

### 2.2 Calibración de Probabilidades y Umbral Adaptativo por Cuantiles
Un clasificador logístico o de árboles con regularización sobre clases desbalanceadas ($P(Y=1) \neq 0.50$) produce scores concentrados alrededor de la tasa base $\bar{y}_{\text{train}}$.
1. **Prohibido usar un umbral fijo arbitrario (como `0.55`) sin calibrar**: Si $\max(\hat{p}) < 0.55$, el modelo produce `0 operaciones` fuera de muestra.
2. **Selección por Cuantil de Entrenamiento o Esperanza Neta**:
   - Calcular en el conjunto de entrenamiento los cuantiles $Q_{q}(\hat{p}_{\text{train}})$ para $q \in \{0.60, 0.70, 0.80, 0.85\}$.
   - O bien calibrar $\hat{p}_{\text{cal}}$ mediante Platt Scaling (`sigmoid`) / Isotonic Regression dentro de un split interno de entrenamiento y exigir:
     $$\hat{E}[R_i \mid X_i] = \hat{p}_{\text{cal}}(X_i) \cdot \hat{R}_{\text{win}} - (1 - \hat{p}_{\text{cal}}(X_i)) \cdot \hat{R}_{\text{loss}} \ge \tau_{R}$$

### 2.3 Significancia Estadística: Probabilistic & Deflated Sharpe Ratio (PSR / DSR)
Dado un conjunto de $N$ operaciones cerradas con retornos $\{r_1, \dots, r_N\}$, media $\hat{\mu}$, desviación típica $\hat{\sigma}$, asimetría (*skewness*) $\hat{\gamma}_3$ y curtosis $\hat{\gamma}_4$:
- El Sharpe Ratio por operación es $\widehat{SR} = \frac{\hat{\mu}}{\hat{\sigma}}$.
- El error estándar del Sharpe Ratio ajustado por no-normalidad (Lo, 2002; López de Prado, 2014) es:
  $$\hat{\sigma}_{SR} = \sqrt{\frac{1 - \hat{\gamma}_3 \widehat{SR} + \frac{\hat{\gamma}_4 - 1}{4} \widehat{SR}^2}{N - 1}}$$
- El **Probabilistic Sharpe Ratio** frente a un umbral de referencia $SR^*$ es:
  $$\text{PSR}(SR^*) = \Phi\left( \frac{\widehat{SR} - SR^*}{\hat{\sigma}_{SR}} \right)$$
  donde $\Phi(\cdot)$ es la CDF de la normal estándar.
- Cuando se prueban $M$ configuraciones en validación, el umbral ajustado por selección múltiple (*Deflated Sharpe Ratio*, Bailey & López de Prado, 2014) exige superar:
  $$SR^* = \sqrt{V[\{\widehat{SR}_m\}]} \left( (1 - \gamma) \Phi^{-1}\left(1 - \frac{1}{M}\right) + \gamma \Phi^{-1}\left(1 - \frac{1}{M \cdot e}\right) \right)$$
  donde $\gamma \approx 0.57721566$ es la constante de Euler-Mascheroni.

### 2.4 Criterio de Kelly Fraccional y Límites de Ruina
Si una estrategia validada tiene tasa de acierto $W$ y ratio ganancia/pérdida $\rho = R_{\text{win}} / R_{\text{loss}}$:
- La fracción óptima de Kelly es:
  $$f^* = W - \frac{1 - W}{\rho}$$
- En trading real con colas pesadas (*fat tails*), usar siempre **Kelly Fraccional conservador** ($f_{\text{used}} = \min(f_{\max}, 0.10 \cdot f^*)$) acotado al presupuesto estricto de riesgo por operación ($0.25\%\text{–}0.50\%$ del equity).
