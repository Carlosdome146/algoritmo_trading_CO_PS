"""
Historical Downloader: Fetches maximum available history (61,000+ bars / 14 years)
Directly from MetaTrader 5 Broker for:
- DE40 (DAX 40)
- US500 (S&P 500)
- US30 (Dow Jones 30)
- EURUSD (EUR/USD)
"""

import os
from datetime import datetime
import pandas as pd
import MetaTrader5 as mt5

TARGETS = [
    ("DE40", "DAX 40"),
    ("US500", "S&P 500"),
    ("US30", "Dow Jones"),
    ("EURUSD", "EUR/USD")
]

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)


def download_14years():
    print("=" * 70)
    print("DESCARGA DE MÁXIMA PROFUNDIDAD HISTÓRICA (HASTA 14 AÑOS / 2012-2026)")
    print("=" * 70)

    if not mt5.initialize():
        print(f"[!] Error al conectar con MT5: {mt5.last_error()}")
        return

    summary = []

    for symbol, name in TARGETS:
        if not mt5.symbol_select(symbol, True):
            continue

        print(f"\n[+] Solicitando histórico máximo para {name} ({symbol}) en H1...")
        # Request up to 70,000 bars
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 70000)

        if rates is None or len(rates) == 0:
            print(f"    [!] Error al obtener datos para {symbol}: {mt5.last_error()}")
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

        filename = f"{symbol}_H1_14years.csv"
        filepath = os.path.join(DATA_DIR, filename)
        df.to_csv(filepath)

        n_bars = len(df)
        t_start = str(df.index[0])[:10]
        t_end = str(df.index[-1])[:10]
        fsize = os.path.getsize(filepath) / (1024 * 1024)

        print(f"    -> Guardado en: {filename} ({fsize:.2f} MB)")
        print(f"    -> {n_bars:,} barras obtenidas desde {t_start} hasta {t_end}")

        summary.append({
            "Símbolo": symbol,
            "Activo": name,
            "Barras Totales": f"{n_bars:,}",
            "Inicio": t_start,
            "Fin": t_end,
            "Años": round(n_bars / (250 * 14), 1),
            "Tamaño": f"{fsize:.2f} MB"
        })

    mt5.shutdown()
    sum_df = pd.DataFrame(summary)
    print("\n" + "=" * 70)
    print("RESUMEN DE HISTÓRICO MASIVO EXTRAÍDO")
    print("=" * 70)
    print(sum_df.to_string(index=False))


if __name__ == "__main__":
    download_14years()
