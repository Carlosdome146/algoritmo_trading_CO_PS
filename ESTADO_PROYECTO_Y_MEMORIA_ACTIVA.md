# 🧠 MEMORIA ACTIVA Y ESTADO DEL PROYECTO: BOT TRADING

> **Ubicación del Workspace Oficial:** `C:\Users\julix\.gemini\antigravity\brain\BOT TRADING`  
> **Proyecto Antigravity ID:** `313a50c1-b53b-4313-a9c1-dc7a859ccb14`  
> **Repositorio Git:** `https://github.com/Carlosdome146/algoritmo_trading_CO_PS.git` (`origin/main`)  
> **Última Actualización:** 07 de Noviembre de 2026

---

## 1. Resumen Ejecutivo
Este proyecto desarrolla, valida y ejecuta un sistema cuantitativo algorítmico institucional para **MetaTrader 5** enfocado en índices bursátiles (`GERMANY40`, `[SP500]`, `US100`, `[DJI30]`, `[IBEX35]`), materias primas (`GOLD`) y divisas (`EURUSD`).

El sistema opera con controles estrictos de riesgo de cola, modelado exacto de comisiones y spreads del bróker, dimensionamiento fraccional asintótico y filtros de régimen de volatilidad.

---

## 2. Cuenta de Bróker en Producción (DEMO)
- **Bróker:** Admirals (AdmiralsGroup-Demo)
- **Tipo de Cuenta:** Trade.MT5 (Netting/Hedging CFD)
- **Número de Cuenta:** `#58678879`
- **Balance Actual:** `3,058.12 EUR`
- **Equity Flotante:** `3,058.12 EUR`
- **Apalancamiento:** 1:100
- **Historial Real Consolidado:** 13 operaciones cerradas | 10 victorias / 3 pérdidas (**76.9% Win Rate**, **+58.21 EUR** beneficio neto).

---

## 3. Salvaguardas Críticas Desplegadas
Tras la auditoría forense del Trade #13 (viernes 6 de noviembre, impacto por dato macro de Producción Industrial de Alemania), se han fijado las siguientes reglas institucionales inmutables:

1. **Riesgo por Operación al 1.00% Exacto:**
   - Presupuesto de riesgo máximo: `~30.58 EUR` sobre balance actual (reducido desde el 1.50%).
   - Rechazo automático de operaciones si el lote mínimo excede este presupuesto.
2. **Filtro Macroeconómico Tier-1 Multi-País (`trading_v2/execution/macro_news_filter.py`):**
   - Veto de ±15 a ±30 minutos antes y después de publicaciones de alto impacto de:
     - **Alemania (DE):** Producción Industrial, Pedidos de Fábrica, IFO, Balanza Comercial, IPC/HICP.
     - **España (ES):** IPC INE, PMI Manufacturero/Servicios, PIB Trimestral, Desempleo.
     - **Eurozona / BCE (EU):** Decisiones de Tipos de Interés, Ruedas de Prensa de Lagarde, IPC Eurozona.
     - **Estados Unidos (US):** NFP (Nóminas no Agrícolas), CPI, PPI, Reuniones FOMC / Powel, Core PCE, ISM.
3. **Filtro de Campana de Apertura Opción A1 (`OPENING_BELL_WINDOWS_UTC`):**
   - Veto de los primeros 5 minutos de alta volatilidad al abrir las bolsas:
     - 07:00–07:05 UTC (08:00 CET: Futuros Eurex / DAX e IBEX).
     - 08:00–08:05 UTC (09:00 CET: Contado Xetra / Bolsa de Madrid).
     - 13:30–13:35 UTC (14:30 CET: Apertura de Wall Street para S&P 500, Nasdaq, Dow Jones, Oro y EURUSD).
4. **Protección Weekend Auto-Square:** Cierre forzoso de cualquier posición residual los viernes a las 20:30 UTC para evitar riesgo de Weekend Gaps.
5. **Circuit Breaker RiskPause:** Pausa de 60 minutos tras 2 pérdidas consecutivas; congelación del día si se alcanza -1.50% de Drawdown.

---

## 4. Test A/B en Vivo: Modelo A vs Modelo B
A petición del usuario (Julio), el sistema ejecuta dos modelos simultáneos para dirimir con datos en vivo cuál maximiza la rentabilidad y seguridad:

| Métrica / Característica | **Modelo A (Live DEMO en MT5)** | **Modelo B (Operador Fantasma en Sombra)** |
| :--- | :--- | :--- |
| **Naturaleza** | Ejecución Real en cuenta DEMO `#58678879` | Simulación en Sombra (*Read-Only, Zero Riesgo*) |
| **Salida en Índices y Oro** | Scalping 100% TP Fijo (M15/M30) | **Híbrido 70/30:** 70% TP rápido + Breakeven + 30% Runner Trailing EMA20 |
| **Estrategia Forex (EURUSD)** | M15 Scalp (TP 3.5 pips / SL 5.5 pips) | **H1 Mean Reversion** (TP +40 pips / SL -35 pips, elimina fricción spread) |
| **Riesgo por Trade** | **1.00%** (~30.58 €) | **1.00%** (~30.00 € sobre capital virtual base 3,000 €) |
| **Filtros Macro y Campana** | ✅ Activos | ✅ Activos |
| **Archivo de Persistencia** | Historial oficial MT5 | `data/ghost_trader_state.json` |

### Enlaces de Seguimiento en Vivo:
- **Nube 4G/5G (Móvil):** [GitHub Gist de Monitorización](https://gist.github.com/julio7gil/58af579d3d6fc1961143e3293d51b40b) (Actualización cada 30 segundos).
- **Dashboard Web Local:** `http://localhost:8080` (o IP local Wi-Fi en puerto 8080).
- **Endpoint API JSON:** `http://localhost:8080/json`.

---

## 5. Lanzadores y Scripts de Operación
Todos los scripts `.bat` están listos en la raíz de este proyecto:

1. **`INICIAR_TRADING_Y_MONITOR_DEMO.bat`**:
   - Arranca en un solo clic los 3 componentes:
     - [1/3] Servidor del Monitor Móvil (`scripts/dashboard_movil.py`).
     - [2/3] Modelo A: Ejecutor en MetaTrader 5 DEMO (`trading_v2/execution/demo_paper_trader.py`).
     - [3/3] Modelo B: Operador Fantasma Híbrido 70/30 (`trading_v2/execution/ghost_shadow_trader.py`).
2. **`EJECUTAR_BOT_LOCAL.bat`**: Lanza de forma independiente el bot real DEMO (Modelo A).
3. **`EJECUTAR_FANTASMA_LOCAL.bat`**: Lanza de forma independiente el Operador Fantasma (Modelo B).
4. **`VER_CUADRO_MANDO.bat`**: Visualizador en consola.

---

## 6. Arquitectura del Código y Tests

- **`trading_v2/`**:
  - `execution/demo_paper_trader.py`: Motor de ejecución en MetaTrader 5 con gestión de órdenes, límites de correlación y filtros.
  - `execution/ghost_shadow_trader.py`: Motor del operador fantasma en sombra para pruebas A/B.
  - `execution/macro_news_filter.py`: Calendario e inteligencia de veto macroeconómico Tier-1.
  - `backtesting/contract_specs.py`: Especificaciones contractuales auditadas de Admirals e IC Markets, cálculo exacto de lotes y conversión de divisas.
  - `strategies/micro_scalping.py`: Algoritmo `institutional_sniper_scalp` (Micro-Sweep Reclaim).
- **`scripts/`**:
  - `dashboard_movil.py`: Servidor HTTP y sincronizador continuo con GitHub Gist.
  - `forensic_cross_asset_audit_4y.py`: Auditoría forense de 60,000 barras (2021–2026).
  - `research_optimal_architecture_4y.py`: Simulación matemática del modelo Híbrido 70/30.
- **`tests/`**:
  - 148 pruebas unitarias pasando al 100% (`python -m unittest discover tests`).

---

## 7. Instrucciones para Continuar en Futuras Sesiones
Si un nuevo agente de IA o el usuario reanuda el trabajo desde este proyecto:
1. **Verificar Estado del Mercado:** Los fines de semana las bolsas están cerradas. Las cotizaciones se reanudan el domingo por la noche (23:00 UTC / 00:00 CET para Forex y futuros).
2. **No Alterar el Riesgo Máximo:** El riesgo por operación debe mantenerse en el **1.00%** salvo orden explícita del usuario.
3. **Mantener Cero Riesgo en el Fantasma:** El archivo `ghost_shadow_trader.py` NUNCA debe invocar `order_send` en MT5; debe permanecer estrictamente en modo solo lectura.
4. **Ejecutar Suite de Tests antes de cualquier Push:** Asegurarse de que `python -m unittest discover tests` pasa con 148/148 OK.
