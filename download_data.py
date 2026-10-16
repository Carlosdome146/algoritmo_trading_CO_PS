"""
Data Downloader for Quantitative Strategy Development
Downloads 4 years of daily and hourly historical data for:
- S&P 500 (^GSPC)
- Dow Jones Industrial Average (^DJI)
- DAX 40 (^GDAXI)
- EUR/USD (EURUSD=X)
"""

import os
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf

# Target assets configuration
ASSETS = {
    "SP500": {"symbol": "^GSPC", "name": "S&P 500 Index"},
    "DOW_JONES": {"symbol": "^DJI", "name": "Dow Jones Industrial Average"},
    "DAX40": {"symbol": "^GDAXI", "name": "DAX 40 Index"},
    "EURUSD": {"symbol": "EURUSD=X", "name": "EUR/USD Forex Pair"}
}

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)


def download_historical_data(years: int = 4):
    print("=" * 60)
    print("DESCARGANDO HISTÓRICOS (Diario 4 años y Horario 1h - 2 años)")
    print("=" * 60)

    end_date = datetime.now()
    start_date = end_date - timedelta(days=years * 365 + 30)

    for name, info in ASSETS.items():
        symbol = info["symbol"]
        
        # 1. Daily data (4 years)
        print(f"\n[+] {name} (Diario 1d)...")
        df_1d = yf.download(symbol, start=start_date.strftime('%Y-%m-%d'), end=end_date.strftime('%Y-%m-%d'), progress=False)
        if not df_1d.empty:
            if isinstance(df_1d.columns, pd.MultiIndex):
                df_1d.columns = df_1d.columns.get_level_values(0)
            df_1d = df_1d[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
            df_1d["Return"] = df_1d["Close"].pct_change()
            df_1d.to_csv(os.path.join(DATA_DIR, f"{name}_1d.csv"))
            print(f"    -> {len(df_1d)} barras diarias guardadas.")

        # 2. Hourly data (2 years max for 1h in yfinance)
        print(f"[+] {name} (Horario 1h)...")
        df_1h = yf.download(symbol, period="730d", interval="1h", progress=False)
        if not df_1h.empty:
            if isinstance(df_1h.columns, pd.MultiIndex):
                df_1h.columns = df_1h.columns.get_level_values(0)
            df_1h = df_1h[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
            df_1h["Return"] = df_1h["Close"].pct_change()
            df_1h.to_csv(os.path.join(DATA_DIR, f"{name}_1h.csv"))
            print(f"    -> {len(df_1h)} barras horarias guardadas.")


if __name__ == "__main__":
    download_historical_data(years=4)
