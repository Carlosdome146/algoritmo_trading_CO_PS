---
name: microestructura-orderflow-intradia
description: >-
  Microestructura del mercado bursátil, dinámicas institucionales de apertura
  (Opening Range, Initial Balance, Liquidity Sweeps), VWAP intradía, consumo de
  ADR (Average Daily Range) y diseño de gatillos de precisión tipo francotirador
  con tasa de acierto objetivo >= 80% para DAX40, SP500, DOW30, GOLD y EURUSD.
---

# Skill: Microestructura Bursátil y Gatillos Institucionales de Alta Precisión (`>= 80%` Win Rate)

Esta skill define las reglas de microestructura intradía y comportamiento específico por activo para maximizar la tasa de acierto (objetivo $\ge 79\text{–}82\%$) en MetaTrader 5.

---

## 1. Anatomía Específica de los 5 Activos del Proyecto

No todos los activos se mueven igual. Tratar el `EURUSD` con las mismas reglas que el `GOLD` o el `DAX40` destruye la tasa de acierto.

| Activo | Símbolo Admirals | Personalidad Estadística | Ventana Óptima (UTC) | Trampa Principal a Evitar |
| :--- | :--- | :--- | :--- | :--- |
| **DAX 40** | `GERMANY40` | Fuerte impulso en apertura de Frankfurt (`07:00-09:30 UTC`) seguido de barridos de liquidez y continuación en apertura de EE.UU. | `07:00 - 15:30 UTC` | Operar entre `11:00 y 13:00 UTC` (mediodía europeo sin volumen) o en sesión nocturna con spread de 150+ pts. |
| **S&P 500** | `[SP500]` | Tendencial institucional en sesión NY; fuertes reversiones al `VWAP` intradía tras excesos iniciales. | `13:30 - 19:30 UTC` | Entrar en los primeros 15 min de apertura (`13:30-13:45 UTC`) cuando hay barridos violentos en ambas direcciones. |
| **Dow Jones 30** | `[DJI30]` | Más defensivo/industrial que el S&P 500, pero con spread relativo mayor en puntos (`300 pts`). Requiere ATR amplio. | `13:45 - 19:30 UTC` | Operar cuando el ratio `Spread / ATR_M15 > 0.07` (el spread devora el beneficio de objetivos cortos). |
| **Oro Spot** | `GOLD` | Activo refugio y de momento puro; respeta niveles redondos, máximos/mínimos de sesión asiática/londinense y explosiones de volatilidad. | `07:00 - 18:00 UTC` | Operar en contra de una expansión de volatilidad H1 o justo en la publicación de datos de EE.UU. (`12:30 / 13:30 UTC`). |
| **Euro / Dólar** | `EURUSD` | Alta reversión a la media (Hurst $H < 0.48$ la mayor parte del tiempo); falsas rupturas frecuentes salvo en sesiones con catalizador macro. | `07:00 - 16:00 UTC` | Comprar rupturas tardías (*breakouts*) tras 3 velas consecutivas: en `EURUSD` suelen revertir de inmediato. |

---

## 2. Variables de Microestructura Causales (100% Sin Sesgo de Futuro)

Para alcanzar tasas de acierto $\ge 79\%$, las señales técnicas deben incorporar estas variables calculadas estrictamente con barras cerradas hasta el instante $i$:

1. **VWAP Intradía Causal y Bandas de Desviación ($\sigma_{\text{VWAP}}$)**:
   - Reiniciado al inicio de cada sesión diaria UTC:
     $$\text{VWAP}_i = \frac{\sum_{k=t_0}^{i} P_{\text{typ}, k} \cdot V_k}{\sum_{k=t_0}^{i} V_k}, \quad P_{\text{typ}, k} = \frac{H_k + L_k + C_k}{3}$$
   - Distancia normalizada al VWAP:
     $$z_{\text{VWAP}, i} = \frac{C_i - \text{VWAP}_i}{\text{ATR}_i}$$
   - *Regla institucional*: En tendencias alcistas (`H1 == 1`), las compras de mayor tasa de acierto ocurren en *pullbacks* hacia la zona $\text{VWAP}_i \pm 0.5 \text{ ATR}_i$, nunca cuando $z_{\text{VWAP}, i} > +2.0$ (sobreextensión).

2. **Consumo de Rango Diario (ADR% Exhaustion Filter)**:
   - Sea $\text{ADR}_{14}$ la media móvil de los últimos 14 rangos diarios completos ($\text{High}_{\text{day}} - \text{Low}_{\text{day}}$).
   - El rango consumido hoy hasta la vela $i$ es:
     $$\text{ADR\_Used}_i = \frac{\max_{k \in \text{hoy}}(H_k) - \min_{k \in \text{hoy}}(L_k)}{\text{ADR}_{14}}$$
   - *Regla de Veto*: Si $\text{ADR\_Used}_i > 0.85$ (el activo ya se ha movido más del 85% de su recorrido diario habitual), **bloquear entradas de continuación tendencial**, ya que la probabilidad de giro o estancamiento supera el 70%.

3. **Anatomía de la Vela de Gatillo (Rejection Wick & Closing Drive)**:
   - **Posición del cierre en el rango (`Close Location Value`, CLV)**:
     $$\text{CLV}_i = \frac{C_i - L_i}{\max(H_i - L_i, \epsilon)} \in [0, 1]$$
     - Para `LONG`: exigir $\text{CLV}_i \ge 0.65$ (cierre en el tercio superior de la vela, confirmando absorción compradora).
     - Para `SHORT`: exigir $\text{CLV}_i \le 0.35$ (cierre en el tercio inferior).
   - **Presión de Mecha de Rechazo (`Rejection Wick Ratio`)**:
     - Mecha inferior (soporte comprador): $\frac{\min(O_i, C_i) - L_i}{H_i - L_i}$.
     - Mecha superior (rechazo vendedor): $\frac{H_i - \max(O_i, C_i)}{H_i - L_i}$.

4. **Flujo de Volumen Relativo Desestacionalizado (`RVOL`)**:
   - El volumen de ticks en M15 varía enormemente según la hora del día. Comparar $V_i$ contra la mediana o media de las últimas 20 barras:
     $$\text{RVOL}_i = \frac{V_i}{\text{SMA}_{20}(V)_i}$$

---

## 3. Arquitecturas de Salida para Superar el 79% de Acierto

Para que un sistema supere el **79% de tasa de acierto** en datos reales con spread Bid/Ask:

### Modalidad 1: Francotirador de Impulso / Pullback Institucional (*High-Probability Target*)
- **Entrada**: Confluencia H1 cerrada + Pullback a `EMA20`/`VWAP` en M15 + Vela de giro a favor ($\text{CLV} \ge 0.65$ en compras o $\le 0.35$ en ventas) + Sesión activa + $\text{ADR\_Used} < 0.80$ + $\text{Spread}/\text{ATR} \le 0.06$.
- **Objetivo (`TP`)**: $0.50 \times \text{ATR}$ a $0.70 \times \text{ATR}$ (el impulso inmediato de salida del pullback).
- **Stop Loss (`SL`)**: $1.10 \times \text{ATR}$ a $1.30 \times \text{ATR}$ (detrás de la estructura del pullback).
- **Protección de Breakeven Causal (al cierre de vela)**: Si al cierre de la barra $j$ el beneficio ejecutable (al `Bid` en compras, al `Ask` en ventas) supera $+0.40 \times \text{ATR}$, en la barra $j+1$ el Stop Loss se sitúa en $\text{Entry} + 0.05 \times \text{ATR}$.

### Modalidad 2: Reversión a la Media en Rango Acotado (*Mean-Reversion to Fair Value*)
- **Ideal para**: `EURUSD`, `[SP500]` y `GERMANY40` cuando el régimen H1/M15 tiene baja direccionalidad ($\text{ADX} < 22$).
- **Entrada**: Exceso estadístico fuera de Banda de Bollinger $(20, 2.0)$ con mecha de rechazo y giro de RSI.
- **Objetivo (`TP`)**: Retorno parcial hacia la media central ($0.55 \times \text{ATR}$).
- **Stop Loss (`SL`)**: $1.15 \times \text{ATR}$.
