from pathlib import Path

path = Path(r"C:\Users\julix\.gemini\antigravity\scratch\algoritmo_trading_CO_PS\trading_v2\execution\demo_paper_trader.py")
text = path.read_text(encoding="utf-8")

old_block_1 = """        # 5. Generar señal según estrategia configurada
        if self.cfg.strategy == "ema_rsi_baseline":"""

new_block_1 = """        # 5. Generar señal según estrategia configurada
        target_u: float | None = None
        stop_u: float | None = None
        is_fx: bool = "EUR" in symbol

        if self.cfg.strategy == "ema_rsi_baseline":"""

assert old_block_1 in text, "old_block_1 not found"
text = text.replace(old_block_1, new_block_1, 1)

old_block_2 = """            if is_fx:
                target_u, stop_u, sweep_u, s_start, s_end = 2.5, 5.0, 1.5, 7, 16
                min_wick = 0.50
            elif is_dax:
                target_u, stop_u, sweep_u, s_start, s_end = 15.0, 25.0, 8.0, 7, 15
                min_wick = 0.35
            elif is_ibex:
                # Calibración optimizada IBEX 35 (82.8% Win Rate, Profit Factor 2.01)
                # Ventana matinal líquida de Madrid (09:00 a 13:00 CET / 07:00 a 11:00 UTC)
                target_u, stop_u, sweep_u, s_start, s_end = 15.0, 25.0, 5.0, 7, 11
                min_wick = 0.55
            else:  # [SP500] / US500
                target_u, stop_u, sweep_u, s_start, s_end = 4.5, 7.5, 2.5, 13, 20
                min_wick = 0.35"""

new_block_2 = """            if is_fx:
                # Patrón Puro Ismael Reclaim (91.67% Win Rate, Profit Factor 10.74)
                target_u, stop_u, sweep_u, s_start, s_end = 3.0, 5.0, 1.5, 7, 16
                min_wick = 0.55
            elif is_dax:
                # GERMANY40: Target determinante 12.0 pts para máxima probabilidad (89.29% Win Rate, Profit Factor 1.57)
                target_u, stop_u, sweep_u, s_start, s_end = 12.0, 25.0, 8.0, 7, 15
                min_wick = 0.45
            elif is_ibex:
                # IBEX35: Target determinante 15.0 pts en sesión matinal Madrid (87.50% Win Rate, Profit Factor 2.35)
                target_u, stop_u, sweep_u, s_start, s_end = 15.0, 25.0, 5.0, 7, 11
                min_wick = 0.55
            else:  # [SP500] / US500
                # SP500: Target determinante 4.0 pts en sesión Wall Street (80.30% Win Rate, Profit Factor 1.06)
                target_u, stop_u, sweep_u, s_start, s_end = 4.0, 7.5, 2.5, 13, 20
                min_wick = 0.45"""

assert old_block_2 in text, "old_block_2 not found"
text = text.replace(old_block_2, new_block_2, 1)

old_block_3 = """        entry_price = float(tick.ask) if sig == 1 else float(tick.bid)
        stop_dist_price = self.cfg.sl_atr * atr
        sl_price = round(entry_price - sig * stop_dist_price, spec.digits)
        tp_price = round(entry_price + sig * self.cfg.tp_atr * atr, spec.digits)"""

new_block_3 = """        entry_price = float(tick.ask) if sig == 1 else float(tick.bid)
        if self.cfg.strategy == "institutional_sniper_scalp" and target_u is not None and stop_u is not None:
            unit_mult = 0.00010 if is_fx else 1.0
            stop_dist_price = stop_u * unit_mult
            sl_price = round(entry_price - sig * stop_dist_price, spec.digits)
            tp_price = round(entry_price + sig * (target_u * unit_mult), spec.digits)
        else:
            stop_dist_price = self.cfg.sl_atr * atr
            sl_price = round(entry_price - sig * stop_dist_price, spec.digits)
            tp_price = round(entry_price + sig * self.cfg.tp_atr * atr, spec.digits)"""

assert old_block_3 in text, "old_block_3 not found"
text = text.replace(old_block_3, new_block_3, 1)

path.write_text(text, encoding="utf-8")
print("SUCCESSFULLY PATCHED demo_paper_trader.py")
