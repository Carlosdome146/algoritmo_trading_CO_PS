import MetaTrader5 as mt5
from trading_v2.execution.demo_paper_trader import DemoPaperTrader, DemoTraderConfig
from trading_v2.strategies.micro_scalping import compute_sniper_indicators, SniperScalpConfig, generate_sniper_signals

mt5.initialize()
bot = DemoPaperTrader(DemoTraderConfig(strategy='institutional_sniper_scalp', symbols=['[SP500]']), adapter=mt5)
bot.initialize()

rates = mt5.copy_rates_from_pos('[SP500]', mt5.TIMEFRAME_M30, 0, 50)
df = bot._build_dataframe_from_rates(rates)
ind = compute_sniper_indicators(df)

cfg_sp = SniperScalpConfig(
    symbol='[SP500]',
    target_units=4.0,
    stop_units=7.5,
    session_start_h=13,
    session_end_h=20,
    max_holding_bars=4,
    min_sweep_units=2.5,
    min_rejection_wick=0.45,
    use_h1_filter=True,
    use_keltner_filter=False,
    max_opposite_wick=0.12,
)
sigs = generate_sniper_signals(df, cfg_sp)

for idx, r in sigs.tail(8).iterrows():
    c = r['Close']
    o = r['Open']
    h = r['High']
    l = r['Low']
    sig = r['signal']
    lw = r['lower_wick']
    uw = r['upper_wick']
    clv = r['clv']
    e20 = r['ema20']
    s200 = r['sma200']
    rlo8 = r['recent_low_8']
    rlo16 = r['recent_low_16']
    rsi = r['rsi2']
    hr = idx.hour
    print(f"Time: {idx} (hour={hr}) | Sig={sig} | C={c:.2f}, O={o:.2f}, L={l:.2f}, H={h:.2f}")
    print(f"   lw={lw:.2f}, uw={uw:.2f}, clv={clv:.2f}, rlo8={rlo8:.2f}, rlo16={rlo16:.2f}, e20={e20:.2f}, s200={s200:.2f}")
