"""Diagnóstico del estado del mercado y señales en lo que va de día (2026-10-23)."""
from __future__ import annotations

from datetime import datetime, timezone
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

from trading_v2.strategies.micro_scalping import (
    SniperScalpConfig,
    generate_sniper_signals,
)


def main():
    if not mt5.initialize():
        print("Error al inicializar MT5")
        return

    now = datetime.now(timezone.utc)
    today_start = datetime(2026, 10, 23, 0, 0, 0, tzinfo=timezone.utc)
    
    print(f"================================================================================")
    print(f"REPORTE DE ESTADO DEL MERCADO HOY: {now.strftime('%Y-%m-%d %H:%M:%S UTC')} (14:22 Hora España)")
    print(f"================================================================================")

    acc = mt5.account_info()
    print(f"CUENTA: #{acc.login} ({acc.server}) | Balance: {acc.balance:.2f} {acc.currency} | Equidad: {acc.equity:.2f} | Posiciones Abiertas: {len(mt5.positions_get()) if mt5.positions_get() else 0}\n")

    symbols = ["GERMANY40", "[SP500]", "EURUSD"]
    
    for sym in symbols:
        r15 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 200)
        df15 = pd.DataFrame(r15)
        df15["time"] = pd.to_datetime(df15["time"], unit="s", utc=True)
        df15.set_index("time", inplace=True)
        df15.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "spread": "Spread"}, inplace=True)
        
        # Velas de hoy
        df_today = df15[df15.index >= today_start]
        cur_tick = mt5.symbol_info_tick(sym)
        spread_pts = (cur_tick.ask - cur_tick.bid) if cur_tick else 0.0
        
        # Calcular RSI2 y Bollinger
        c = df15["Close"]
        delta = c.diff()
        up = delta.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
        dn = (-delta.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
        rsi2 = (100 - 100 / (1 + up / dn.replace(0, np.nan))).iloc[-1]
        
        sma20 = c.rolling(20).mean().iloc[-1]
        std20 = c.rolling(20).std(ddof=0).iloc[-1]
        bb_up = sma20 + 2.0 * std20
        bb_lo = sma20 - 2.0 * std20
        
        # ATR14
        tr = pd.concat([df15["High"] - df15["Low"], (df15["High"] - c.shift(1)).abs(), (df15["Low"] - c.shift(1)).abs()], axis=1).max(axis=1)
        atr14 = tr.rolling(14).mean().iloc[-1]
        
        # SMA200
        sma200 = c.rolling(200, min_periods=50).mean().iloc[-1]
        
        # Tendencia H1
        rh1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 50)
        dfh1 = pd.DataFrame(rh1)
        dfh1["time"] = pd.to_datetime(dfh1["time"], unit="s", utc=True)
        dfh1.set_index("time", inplace=True)
        c_h1 = dfh1["close"]
        ema20_h1 = c_h1.ewm(span=20, adjust=False).mean().iloc[-1]
        ema50_h1 = c_h1.ewm(span=50, adjust=False).mean().iloc[-1]
        h1_trend = "ALCISTA" if ema20_h1 > ema50_h1 else "BAJISTA"
        
        print(f"--- ACTIVO: {sym} ---")
        if cur_tick:
            print(f"  Precio actual: Bid={cur_tick.bid} | Ask={cur_tick.ask} | Spread={spread_pts:.5f}")
        if len(df_today) > 0:
            open_day = df_today.iloc[0]["Open"]
            high_day = df_today["High"].max()
            low_day = df_today["Low"].min()
            cur_price = df_today.iloc[-1]["Close"]
            chg = ((cur_price - open_day) / open_day) * 100
            print(f"  Rango Hoy: Open={open_day:.2f} | High={high_day:.2f} | Low={low_day:.2f} | Último={cur_price:.2f} | Variación={chg:+.2f}%")
        
        print(f"  Métricas Técnicas M15: RSI(2)={rsi2:.1f} | BB_Lo={bb_lo:.2f} | BB_Up={bb_up:.2f} | ATR(14)={atr14:.2f} | Tendencia H1={h1_trend}")
        
        # Señal de Francotirador M15 hoy
        cfg = SniperScalpConfig(
            symbol=sym,
            target_units=15.0 if "GERMANY" in sym else (4.0 if "SP500" in sym else 2.5),
            stop_units=25.0 if "GERMANY" in sym else (7.0 if "SP500" in sym else 5.0),
            session_start_h=7 if "GERMANY" in sym or "EURUSD" in sym else 13,
            session_end_h=15 if "GERMANY" in sym or "EURUSD" in sym else 19,
            max_holding_bars=4,
            min_sweep_units=8.0 if "GERMANY" in sym else (2.0 if "SP500" in sym else 1.5),
            min_rejection_wick=0.35,
            max_trades_per_day=None,
            cooldown_bars=4,
            use_h1_filter=True,
        )
        sig_df = generate_sniper_signals(df15, cfg)
        today_sigs = sig_df[(sig_df.index >= today_start) & (sig_df["signal"] != 0)]
        print(f"  Señales Sniper generadas hoy: {len(today_sigs)}")
        if len(today_sigs) > 0:
            for s_time, s_row in today_sigs.iterrows():
                tipo = "COMPRA (LONG)" if s_row["signal"] == 1 else "VENTA (SHORT)"
                print(f"    -> {s_time.strftime('%H:%M UTC')}: {tipo} al precio {s_row['Close']}")
        else:
            print("    -> Sin gatillo activado (las velas de hoy no superaron el filtro de barrido + absorción con confluencia H1)")
        print()

    mt5.shutdown()


if __name__ == "__main__":
    main()
