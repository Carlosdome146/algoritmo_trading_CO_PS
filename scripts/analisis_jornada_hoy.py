import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timezone
from trading_v2.strategies.micro_scalping import SniperScalpConfig, generate_sniper_signals

mt5.initialize()

assets = [
    ('EURUSD', mt5.TIMEFRAME_M15, 3.0, 5.0, 1.5, 0.55, 7, 16, False, None, True),
    ('GERMANY40', mt5.TIMEFRAME_M30, 12.0, 25.0, 8.0, 0.45, 7, 15, True, None, False),
    ('[IBEX35]', mt5.TIMEFRAME_M30, 15.0, 25.0, 5.0, 0.50, 7, 14, False, None, False),
    ('[SP500]', mt5.TIMEFRAME_M30, 4.0, 7.5, 2.5, 0.45, 13, 20, False, 0.12, False),
]

now = datetime.now(timezone.utc)
today_str = now.strftime('%Y-%m-%d')
print(f"=== ANALISIS DE LA JORNADA HASTA AHORA ({today_str} {now.strftime('%H:%M')} UTC) ===")

for sym, tf_code, tgt, sl, sw, mw, s_start, s_end, uk, uow, allow_s in assets:
    rates = mt5.copy_rates_from_pos(sym, tf_code, 0, 120)
    if rates is None or len(rates) == 0:
        continue
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
    df.set_index('time', inplace=True)
    df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'tick_volume': 'TickVolume', 'spread': 'Spread'}, inplace=True)

    cfg = SniperScalpConfig(
        symbol=sym, target_units=tgt, stop_units=sl,
        session_start_h=s_start, session_end_h=s_end,
        min_sweep_units=sw, min_rejection_wick=mw,
        use_keltner_filter=uk, max_opposite_wick=uow,
        allow_short=allow_s, enable_m4_fade=True, enable_yeboster_reclaim=True,
    )
    sig_df = generate_sniper_signals(df, cfg)
    today_bars = sig_df[sig_df.index.strftime('%Y-%m-%d') == today_str]
    today_sigs = today_bars[today_bars['signal'] != 0]

    o_day = today_bars['Open'].iloc[0] if len(today_bars) > 0 else 0
    c_day = today_bars['Close'].iloc[-1] if len(today_bars) > 0 else 0
    h_day = today_bars['High'].max() if len(today_bars) > 0 else 0
    l_day = today_bars['Low'].min() if len(today_bars) > 0 else 0
    change_pts = c_day - o_day
    change_pct = (change_pts / o_day * 100) if o_day > 0 else 0

    last_b = today_bars.iloc[-1] if len(today_bars) > 0 else None
    print(f"\n>>> {sym}:")
    print(f"    Rango hoy: Min={l_day:.2f} | Max={h_day:.2f} | Open={o_day:.2f} | Actual={c_day:.2f} ({change_pts:+.2f} pts / {change_pct:+.2f}%)")
    print(f"    Velas hoy: {len(today_bars)} | Senales activadas hoy: {len(today_sigs)}")
    if last_b is not None:
        print(f"    Indicadores: EMA20={last_b['ema20']:.2f} | SMA200={last_b['sma200']:.2f} | RSI2={last_b['rsi2']:.1f} | KeltnerPosLow={last_b['keltner_pos_low']:.2f} | CLV={last_b['clv']:.2f}")
    if len(today_sigs) > 0:
        for idx, row in today_sigs.iterrows():
            print(f"      SEÑAL DETECTADA: {idx} | Dir={row['signal']} | C={row['Close']:.2f}")
