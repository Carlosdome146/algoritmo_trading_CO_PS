path = "HISTORICO_OPERACIONES.md"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

new_section = """
---

## 🎯 Cartera Activa y Configuración de Operaciones (Riesgo 1.0%)

A fecha **29/10/2026**, tras el escaneo masivo multi-activo en MetaTrader 5 y la validación cuantitativa de Julio y Carlos, se ha ampliado la cartera a **6 activos de élite** y se ha incrementado el riesgo por operación al **`1.00%`** (presupuesto: `~30.18 €` por operación sobre los `3.017,59 €` de capital).

### 📋 Especificaciones por Activo en el Bot en Vivo:

| Activo | Símbolo MT5 | Sesión Operativa (CET) | Win Rate (WR) | Profit Factor | Take Profit | Stop Loss | Ganancia Est. por Acierto |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **DAX 40** | `GERMANY40` | 09:00 – 16:30 | **89.47% (M30)** | **2.29** | `12.0 pts` | `35.0 pts` | **+10.32 € a +15.00 €** |
| **IBEX 35** | `[IBEX35]` | 09:00 – 13:00 | **88.24% (M15)** | **2.37** | `15.0 pts` | `25.0 pts` | **+18.00 €** |
| **EUR / USD** | `EURUSD` | 09:00 – 17:00 | **78.95% (M15)** | **1.38** | `3.0 pips` | `5.0 pips` | **+15.05 €** |
| **Dow Jones 30** | `[DJI30]` | 15:30 – 21:30 | **81.82% (M15)** | **2.75** | `55.0 pts` | `110.0 pts` | **+14.78 €** |
| **Oro Spot** | `GOLD` | 14:00 – 20:00 | **84.62% (M15)** | **2.04** | `4.0 $` | `12.0 $` | **+16.13 €** |
| **S&P 500** | `[SP500]` | 15:30 – 21:30 | **84.09% (M15)** | **1.51** | `4.0 pts` | `7.5 pts` | **+15.77 €** |

### 🛡️ Reglas de Protección Activa:
1. **Breakeven Causal**: En cuanto la posición alcanza el `+40%` del recorrido hacia el Take Profit, el Stop Loss se eleva automáticamente a `Entrada + 1.5 * Spread` (eliminando cualquier riesgo de pérdida monetaria).
2. **Control de Racha y Freno**: Enfriamiento obligatorio de 60 minutos tras pérdida. Bloqueo diario si se acumulan 3 pérdidas consecutivas o una caída del `-1.5%`.
"""

marker = "_Registro generado automáticamente por el sistema cuantitativo de trading en MetaTrader 5._"
if marker in c:
    c_updated = c.replace(marker, new_section + "\n\n" + marker)
else:
    c_updated = c + "\n" + new_section

with open(path, "w", encoding="utf-8", newline="\n") as f:
    f.write(c_updated)

print("HISTORICO_OPERACIONES.md updated successfully.")
