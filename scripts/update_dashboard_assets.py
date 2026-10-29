# 1. Update scanner_diario_senales.py
scanner_path = "scripts/scanner_diario_senales.py"
with open(scanner_path, "r", encoding="utf-8") as f:
    text = f.read()

old_symbols = """SYMBOLS_TO_SCAN = [
    ("DAX40", "GERMANY40", "idx_dax_bollinger_dip"),
    ("SP500", "[SP500]", "idx_rsi2_dip_regime"),
    ("EURUSD", "EURUSD", "fx_eurusd_ker_exhaustion"),
    ("IBEX35", "[IBEX35]", "idx_ibex_bollinger_dip"),
]"""

new_symbols = """SYMBOLS_TO_SCAN = [
    ("DAX40", "GERMANY40", "idx_dax_bollinger_dip"),
    ("IBEX35", "[IBEX35]", "idx_ibex_bollinger_dip"),
    ("EURUSD", "EURUSD", "fx_eurusd_ker_exhaustion"),
    ("DOW30", "[DJI30]", "idx_rsi2_dip_regime"),
    ("ORO", "GOLD", "idx_rsi2_dip_regime"),
    ("SP500", "[SP500]", "idx_rsi2_dip_regime"),
]"""

text_norm = text.replace("\r\n", "\n")
old_norm = old_symbols.replace("\r\n", "\n")
if old_norm in text_norm:
    text_new = text_norm.replace(old_norm, new_symbols)
    with open(scanner_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text_new)
    print("scanner_diario_senales.py updated successfully.")
else:
    print("old_symbols not found in scanner_diario_senales.py")

# 2. Update scripts/dashboard_movil.py to render enhanced portfolio info
dashboard_path = "scripts/dashboard_movil.py"
with open(dashboard_path, "r", encoding="utf-8") as f:
    d_text = f.read()

# Let's inspect the render_markdown in dashboard_movil.py
old_render_end = """    lines.extend([
        "",
        "### 🛡️ Transparencia de Costes y Comisiones",
        "- **Broker Demo Actual:** Admirals DEMO `#58678879` (Cuenta Trade.MT5: comisión 0.00 EUR en broker; coste integrado en spread).",
        "- **Modelo Cuantitativo Auditado:** IC Markets Raw ECN (Forex: comisión 3.50 USD/lado = ~6.30 EUR/lote round-trip + 0.1 pip spread crudo; Índices: 1.0 pt DAX / 0.4 pt SP500).",
        "- **Spread y Deslizamiento:** Descontados causalmente al Bid/Ask en cada señal y ejecución.",
        "",
        "---",
        "*Actualizado automáticamente desde el motor local en segundo plano.*",
    ])"""

new_render_end = """    lines.extend([
        "",
        "### 🎯 Cartera Activa y Configuración en Producción (Riesgo 1.0%)",
        "- **Riesgo por Operación:** **1.00%** (~30.18 EUR por trade sobre balance actual).",
        "- **Beneficio Estimado por Acierto:** **+15.00 EUR a +18.00 EUR** netos.",
        "- **Gestión Activa:** Take Profit Asimétrico + Breakeven Causal (eleva Stop Loss a entrada + costes al alcanzar el 40% del recorrido).",
        "",
        "| Activo | Símbolo MT5 | Sesión Operativa | Tasa de Acierto (WR) | Profit Factor (ROI) | Salida (TP / SL) |",
        "| :--- | :--- | :---: | :---: | :---: | :---: |",
        "| **DAX 40** | `GERMANY40` | Mañana Europa (09:00 - 16:30 CET) | **89.47% (M30)** / **82.35% (M15)** | **2.29** / **1.40** | TP: 12 pts / SL: 35 pts |",
        "| **IBEX 35** | `[IBEX35]` | Mañana Europa (09:00 - 13:00 CET) | **88.24% (M15)** | **2.37** | TP: 15 pts / SL: 25 pts |",
        "| **EUR / USD** | `EURUSD` | Sesión Europea (09:00 - 17:00 CET) | **78.95% (M15)** | **1.38** | TP: 3 pips / SL: 5 pips |",
        "| **Dow Jones 30** | `[DJI30]` | Tarde Wall Street (15:30 - 21:30 CET) | **81.82% (M15)** / **76.92% (M30)** | **2.75** / **2.15** | TP: 55 pts / SL: 110 pts |",
        "| **Oro Spot** | `GOLD` | Solapamiento Londres/NY (14:00 - 20:00 CET) | **84.62% (M15)** / **75.00% (M30)** | **2.04** / **2.28** | TP: 4.0$ / SL: 12.0$ |",
        "| **S&P 500** | `[SP500]` | Tarde Wall Street (15:30 - 21:30 CET) | **84.09% (M15)** | **1.51** | TP: 4.0 pts / SL: 7.5 pts |",
        "",
        "### 🛡️ Transparencia de Costes y Comisiones",
        "- **Broker Demo Actual:** Admirals DEMO `#58678879` (Cuenta Trade.MT5: comisión 0.00 EUR en broker; coste integrado en spread).",
        "- **Modelo Cuantitativo Auditado:** IC Markets Raw ECN (Forex: comisión 3.50 USD/lado = ~6.30 EUR/lote round-trip + 0.1 pip spread crudo; Índices: 1.0 pt DAX / 0.4 pt SP500).",
        "- **Spread y Deslizamiento:** Descontados causalmente al Bid/Ask en cada señal y ejecución.",
        "",
        "---",
        "*Actualizado automáticamente desde el motor local en segundo plano.*",
    ])"""

d_text_norm = d_text.replace("\r\n", "\n")
old_render_norm = old_render_end.replace("\r\n", "\n")
if old_render_norm in d_text_norm:
    d_text_new = d_text_norm.replace(old_render_norm, new_render_end)
    with open(dashboard_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(d_text_new)
    print("dashboard_movil.py updated successfully.")
else:
    print("old_render_end not found in dashboard_movil.py")
