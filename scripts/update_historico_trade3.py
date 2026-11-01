path = "HISTORICO_OPERACIONES.md"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

# Update header date and metrics
text = text.replace("Última actualización:** `28/10/2026 23:34:21`", "Última actualización:** `30/10/2026 10:35:00`")
text = text.replace("**`3,017.59 €`** | `+17.59 €`", "**`3,034.75 €`** | `+34.75 €`")
text = text.replace("**`+0.59%`** | 🚀 En verde", "**`+1.16%`** | 🚀 En verde")
text = text.replace("**Total Operaciones Cerradas** | **`2`**", "**Total Operaciones Cerradas** | **`3`**")
text = text.replace("**Operaciones Ganadoras** | **`2`**", "**Operaciones Ganadoras** | **`3`**")

# Update table
old_table_row = "| **2** | 27/10/2026 12:34 | **`[IBEX35]`** | `SELL` | `0.60` | `18,980.26` | `18,965.17` | `+15.09` | `3m 49s` | Take Profit | 🟢 **`+9.05 €`** | `3,017.59 €` |"
new_table_row = (
    "| **2** | 27/10/2026 12:34 | **`[IBEX35]`** | `SELL` | `0.60` | `18,980.26` | `18,965.17` | `+15.09` | `3m 49s` | Take Profit | 🟢 **`+9.05 €`** | `3,017.59 €` |\n"
    "| **3** | 30/10/2026 09:32 | **`GERMANY40`** | `BUY` | `1.20` | `25,966.97` | `25,981.27` | `+14.30` | `2m 14s` | Take Profit | 🟢 **`+17.16 €`** | `3,034.75 €` |"
)
text = text.replace(old_table_row, new_table_row)

# Insert Ficha Técnica Operación #3
ficha_op3 = """### Operación #3 — `GERMANY40` (🟢 GANADORA — 1.0% RIESGO)
- **Ticket Posición MT5:** `#1234146654` (Orden Entrada `#1234146654`, Orden Salida `#1234147131`, Deal Entrada `#1157128147`, Deal Salida `#1157128417`)
- **Estrategia / Gatillo:** `V2_M15_LONG` (Apertura Frankfurt / Institutional Reclaim)
- **Dirección:** `BUY` | **Volumen:** `1.20` lotes (Riesgo calibrado al 1.0%)
- **Momento Entrada:** `30/10/2026 09:30:03` a precio `25966.97`
- **Momento Salida:** `30/10/2026 09:32:17` a precio `25981.27`
- **Tiempo en Mercado:** `2m 14s` (Salida relámpago)
- **Configuración Inicial:** Stop Loss en `25942.47` (riesgo 30.00 €) | Take Profit en `25979.47`
- **Motivo de Ejecución de Cierre:** `Take Profit` (`[tp 25979.47]`, ejecutado con slippage positivo a `25981.27`)
- **Desglose Económico:** Beneficio bruto: `+17.16 €` | Swap: `+0.00 €` | Comisión: `+0.00 €`
- **Beneficio Neto:** **`+17.16 €`**

"""

ficha_op2_anchor = "### Operación #2 — `[IBEX35]` (🟢 GANADORA)"
text = text.replace(ficha_op2_anchor, ficha_op3 + ficha_op2_anchor)

with open(path, "w", encoding="utf-8", newline="\n") as f:
    f.write(text)

print("HISTORICO_OPERACIONES.md updated with trade #3.")
