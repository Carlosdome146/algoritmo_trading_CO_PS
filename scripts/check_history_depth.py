"""Comprobación de profundidad histórica en MT5 para M15 y M30."""
from datetime import datetime, timezone
import MetaTrader5 as mt5

if not mt5.initialize():
    print("Error conectando a MT5")
    exit(1)

symbols = ["GERMANY40", "[SP500]", "US100", "EURUSD", "GOLD"]

print("=" * 70)
print("PROFUNDIDAD DE BARRAS DISPONIBLE EN MT5 (DEMO ADMIRALS)")
print("=" * 70)

for sym in symbols:
    print(f"Activo: {sym}")
    mt5.symbol_select(sym, True)
    for name, tf in [("M15", mt5.TIMEFRAME_M15), ("M30", mt5.TIMEFRAME_M30), ("H1", mt5.TIMEFRAME_H1), ("D1", mt5.TIMEFRAME_D1)]:
        r = mt5.copy_rates_from_pos(sym, tf, 0, 100000)
        if r is not None and len(r) > 0:
            d_start = datetime.fromtimestamp(r[0]["time"], timezone.utc).strftime("%Y-%m-%d")
            d_end = datetime.fromtimestamp(r[-1]["time"], timezone.utc).strftime("%Y-%m-%d")
            years = (datetime.fromtimestamp(r[-1]["time"], timezone.utc) - datetime.fromtimestamp(r[0]["time"], timezone.utc)).days / 365.25
            print(f"  {name:<4}: {len(r):>6} barras | {d_start} -> {d_end} ({years:.1f} años)")
        else:
            print(f"  {name:<4}: Sin datos")
    print("-" * 70)

mt5.shutdown()
