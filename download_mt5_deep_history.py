"""
Deep Historical Data Downloader from MetaTrader 5 Broker
Downloads high-resolution M15 (15-minute) and H1 (1-hour) data directly from broker servers:
- DE40 (DAX 40)
- US500 (S&P 500)
- US30 (Dow Jones 30)
- EURUSD (Euro / US Dollar)
Includes real broker bid/ask spreads, tick volume, and exact timestamps.
"""

import os
from datetime import datetime
import pandas as pd
import MetaTrader5 as mt5

TARGETS = [
    ("DE40", "DAX 40"),
    ("US500", "S&P 500"),
    ("US30", "Dow Jones"),
    ("EURUSD", "EUR/USD Forex")
]

TIMEFRAMES = [
    ("H1", mt5.TIMEFRAME_H1, 20000),    # Up to 20,000 1-hour candles
    ("M15", mt5.TIMEFRAME_M15, 50000),  # Up to 50,000 15-min candles
]

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)


def download_all_deep_history():
    print("=" * 70)
    print("DESCARGA MASIVA DE DATOS HISTÓRICOS DE ALTA RESOLUCIÓN DESDE BROKER MT5")
    print("=" * 70)

    if not mt5.initialize():
        print(f"[!] Error al inicializar MT5: {mt5.last_error()}")
        return

    summary = []

    for symbol, friendly_name in TARGETS:
        if not mt5.symbol_select(symbol, True):
            print(f"[!] Error: No se pudo seleccionar {symbol}")
            continue

        for tf_str, tf_code, max_bars in TIMEFRAMES:
            print(f"\n[+] Descargando {friendly_name} ({symbol}) en temporalidad {tf_str} (hasta {max_bars} barras)...")
            rates = mt5.copy_rates_from_pos(symbol, tf_code, 0, max_bars)
            
            if rates is None or len(rates) == 0:
                print(f"    [!] No hay datos disponibles para {symbol} en {tf_str}")
                continue

            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s")
            df.rename(columns={
                "time": "Time",
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "tick_volume": "Volume",
                "spread": "Spread"
            }, inplace=True)
            df.set_index("Time", inplace=True)

            out_filename = f"{symbol}_{tf_str}_broker.csv"
            out_path = os.path.join(DATA_DIR, out_filename)
            df.to_csv(out_path)

            n_bars = len(df)
            start_t = str(df.index[0])[:16]
            end_t = str(df.index[-1])[:16]
            avg_spread = df["Spread"].mean()
            size_mb = os.path.getsize(out_path) / (1024 * 1024)

            print(f"    -> Guardado en: {out_filename} ({size_mb:.2f} MB)")
            print(f"    -> Total barras: {n_bars:,} | Desde {start_t} hasta {end_t} | Spread medio: {avg_spread:.1f}")

            summary.append({
                "Símbolo": symbol,
                "Activo": friendly_name,
                "Temporalidad": tf_str,
                "Barras": f"{n_bars:,}",
                "Desde": start_t,
                "Hasta": end_t,
                "Spread Medio": f"{avg_spread:.1f} pts",
                "Tamaño": f"{size_mb:.2f} MB"
            })

    mt5.shutdown()
    sum_df = pd.DataFrame(summary)
    print("\n" + "=" * 80)
    print("RESUMEN DE PROFUNDIDAD HISTÓRICA EXTRAÍDA DEL BROKER")
    print("=" * 80)
    print(sum_df.to_string(index=False))


if __name__ == "__main__":
    download_all_deep_history()
