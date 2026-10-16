# Trade Algorithim - Sistema Cuantitativo y Bot de Trading Automatizado

Sistema algorítmico multi-factor con filtrado predictivo de Machine Learning (Meta-Labeling) y ejecución desatendida en **MetaTrader 5 (MT5)**.

---

## 📁 Estructura del Proyecto

```text
Trade Algorithim/
├── data/                      # Históricos OHLCV diarios y horarios (CSV)
│   ├── DAX40_1d.csv & 1h.csv
│   ├── SP500_1d.csv & 1h.csv
│   ├── DOW_JONES_1d.csv & 1h.csv
│   └── EURUSD_1d.csv & 1h.csv
├── download_data.py           # Descargador automático de datos de mercado
├── backtester.py              # Motor de simulación con validación In-Sample / Out-of-Sample
├── ml_strategy.py             # Modelo de Machine Learning (Meta-Labeling con NumPy puro)
├── enhanced_strategy.py       # Estrategia con reglas de Freqtrade, vn.py y TradingAgents
├── test_mt5_connection.py     # Comprobación de estado y símbolos de MetaTrader 5
├── live_trader_mt5.py         # Bot de ejecución en vivo conectado a MetaTrader 5
└── README.md                  # Manual y documentación técnica
```

---

## 🚀 Cómo Ejecutar el Bot

Abre un terminal en esta carpeta (`C:\Users\Usuario\Desktop\Trade Algorithim`):

### 1. Modo Simulación / Dry-Run (Recomendado para observar):
Calcula los indicadores y la probabilidad de éxito en cada tick sin enviar órdenes al broker:
```powershell
python live_trader_mt5.py
```

### 2. Modo Operativo Real (Cuenta DEMO):
Ejecuta las operaciones en tu cuenta demo cuando el modelo de ML aprueba la entrada ($> 52\%$ de probabilidad):
```powershell
python live_trader_mt5.py --live
```

---

## 🛡️ Parámetros de Control y Protección de Capital

| Parámetro | Valor | Propósito |
| :--- | :--- | :--- |
| **Portafolio Multi-Activo** | `DE40`, `US500`, `US30`, `XAUUSD` | Escaneo simultáneo de DAX 40, S&P 500, Dow Jones y Oro. |
| **Selector de Oportunidad** | Convicción Máxima | Si varios activos dan señal, solo dispara en el activo con mayor probabilidad de éxito ML. |
| **Auto-Reentrenamiento** | Diario a medianoche (00:00) | Actualiza las bases históricas con las velas del día y recalibra los modelos ML. |
| **Riesgo por trade** | `1.0%` del Balance | Con $3.000 USD de cuenta, el riesgo máximo es de $30 USD por operación. |
| **Stop Loss / Take Profit** | $1.0 \times \text{ATR}$ / $1.5 \times \text{ATR}$ | Dinámicos según la volatilidad del activo en ese instante. |
| **Breakeven (Freqtrade)** | $+0.9 \times \text{ATR}$ | Mueve el Stop Loss a coste cero en cuanto la operación va a favor. |
| **Límite de concurrencia**| Máx. 1 posición simultánea | Protege la cuenta evitando acumular riesgo correlacionado. |
