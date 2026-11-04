import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timezone

def main():
    if not mt5.initialize():
        print("Error inicializando MT5")
        return
        
    t_from = datetime(2026, 11, 4, 6, 0, tzinfo=timezone.utc)
    t_to = datetime(2026, 11, 4, 16, 0, tzinfo=timezone.utc)
    
    # 1. Deals
    deals = mt5.history_deals_get(t_from, t_to)
    print("=== OPERACIONES DE HOY (04/11/2026) ===")
    if deals:
        for d in deals:
            dt = datetime.fromtimestamp(d.time, tz=timezone.utc)
            print(f"Deal #{d.ticket} | Time: {dt} | Sym: {d.symbol} | Type: {d.type} | Vol: {d.volume} | Px: {d.price:.5f} | PnL: {d.profit:+.2f} EUR | Comment: {d.comment}")
            
    # 2. Bars of EURUSD
    rates = mt5.copy_rates_range("EURUSD", mt5.TIMEFRAME_M15, t_from, t_to)
    if rates is not None:
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        print("\n=== BARRAS EURUSD M15 HOY ===")
        for _, r in df.iterrows():
            rng = r["high"] - r["low"]
            uw = (r["high"] - max(r["open"], r["close"])) / rng if rng > 0 else 0
            lw = (min(r["open"], r["close"]) - r["low"]) / rng if rng > 0 else 0
            clv = (r["close"] - r["low"]) / rng if rng > 0 else 0
            is_green = r["close"] > r["open"]
            col = "VERDE" if is_green else "ROJA "
            pts = rng * 10000.0
            print(f"{r['time'].strftime('%H:%M UTC')} | O:{r['open']:.5f} H:{r['high']:.5f} L:{r['low']:.5f} C:{r['close']:.5f} {col} | Rango:{pts:4.1f}p | MechaSup:{uw:.2f} | MechaInf:{lw:.2f} | CLV:{clv:.2f}")

    # 3. H1 context
    rates_h1 = mt5.copy_rates_range("EURUSD", mt5.TIMEFRAME_H1, datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc), t_to)
    if rates_h1 is not None:
        df_h1 = pd.DataFrame(rates_h1)
        df_h1["time"] = pd.to_datetime(df_h1["time"], unit="s", utc=True)
        print("\n=== TENDENCIA H1 EURUSD ÚLTIMAS HORAS ===")
        for _, r in df_h1.tail(10).iterrows():
            print(f"{r['time'].strftime('%d/%m %H:%M UTC')} | O:{r['open']:.5f} H:{r['high']:.5f} L:{r['low']:.5f} C:{r['close']:.5f}")

    mt5.shutdown()

if __name__ == "__main__":
    main()
