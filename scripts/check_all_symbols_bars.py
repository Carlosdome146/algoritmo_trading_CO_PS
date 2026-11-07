import MetaTrader5 as mt5

mt5.initialize()
symbols = ["GERMANY40", "[SP500]", "US100", "[DJI30]", "[IBEX35]", "GOLD", "EURUSD"]
for s in symbols:
    tf = mt5.TIMEFRAME_M15 if s in ["EURUSD", "[IBEX35]"] else mt5.TIMEFRAME_M30
    mt5.symbol_select(s, True)
    bars = mt5.copy_rates_from_pos(s, tf, 0, 60000)
    count = len(bars) if bars is not None else 0
    tf_str = "M15" if tf == mt5.TIMEFRAME_M15 else "M30"
    print(f"{s:<12s} | TF: {tf_str:<3s} | Bars loaded: {count:6d}")
