import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timezone

mt5.initialize()
r_m1 = mt5.copy_rates_from_pos("GERMANY40", mt5.TIMEFRAME_M1, 0, 2500)
df = pd.DataFrame(r_m1)
df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
# Filtrar entre 08:50 y 11:10 broker time (06:50 y 09:10 UTC)
sub = df[(df["dt"] >= "2026-11-06 08:50:00") & (df["dt"] <= "2026-11-06 10:15:00")]
print("Minimo y maximo en esa ventana:")
print("Min:", sub["low"].min(), "Max:", sub["high"].max())
print("\nPrimeras barras tras 09:00 broker time (07:00 UTC):")
for _, r in sub[(sub["dt"] >= "2026-11-06 09:00:00") & (sub["dt"] <= "2026-11-06 09:10:00")].iterrows():
    print(f"{r['dt'].strftime('%H:%M:%S')} | O={r['open']:.1f} H={r['high']:.1f} L={r['low']:.1f} C={r['close']:.1f}")

print("\nBarras alrededor de las 10:00 broker time (08:00 UTC / 09:00 CET apertura contado):")
for _, r in sub[(sub["dt"] >= "2026-11-06 09:55:00") & (sub["dt"] <= "2026-11-06 10:05:00")].iterrows():
    print(f"{r['dt'].strftime('%H:%M:%S')} | O={r['open']:.1f} H={r['high']:.1f} L={r['low']:.1f} C={r['close']:.1f}")
