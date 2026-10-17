"""Regresiones de calidad, causalidad temporal y seguridad del simulador."""
import unittest
import numpy as np
import pandas as pd
from trading_v2.data.validator import validate_bars
from trading_v2.strategies.trend_following import add_indicators
from trading_v2.backtesting.engine import run_backtest, Config

def fake_bars(n=300, freq="15min"):
    idx = pd.date_range("2026-01-01", periods=n, freq=freq)
    x = np.linspace(100,112,n)
    return pd.DataFrame({"Open":x,"High":x+.4,"Low":x-.4,"Close":x+.1,"Spread":2}, index=idx)

class QualityTests(unittest.TestCase):
    def test_valid_m15(self):
        self.assertTrue(validate_bars(fake_bars(),"M15").ok)

    def test_duplicate_dates_rejected(self):
        df = fake_bars()
        df.index = df.index.where(np.arange(len(df)) != 5, df.index[4])
        self.assertFalse(validate_bars(df,"M15").ok)

    def test_invalid_ohlc_rejected(self):
        df = fake_bars()
        df.loc[df.index[5],"High"] = 1
        self.assertFalse(validate_bars(df,"M15").ok)

    def test_mixed_daily_hourly_rejected(self):
        hours = list(pd.date_range("2015-01-01",periods=55,freq="D")) + list(pd.date_range("2016-01-01",periods=300,freq="h"))
        df = fake_bars(len(hours),freq="h")
        df.index = pd.DatetimeIndex(hours)
        self.assertIn("Mezcla probable"," ".join(validate_bars(df,"H1").errors))

class CausalityTests(unittest.TestCase):
    def test_past_signals_unchanged_by_future(self):
        df = fake_bars(400)
        a = add_indicators(df)
        df2 = df.copy()
        df2.loc[df.index[350]:,"Close"] += 40
        df2.loc[df.index[350]:,"High"] += 40
        b = add_indicators(df2)
        self.assertTrue((a.loc[:df.index[349],"signal"] == b.loc[:df.index[349],"signal"]).all())

    def test_entry_not_on_signal_candle(self):
        df = fake_bars()
        df["signal"] = 0
        df["atr"] = 1.
        df.loc[df.index[150],"signal"] = 1
        df.loc[df.index[151],"High"] = 108
        _,trades = run_backtest(df,Config(point=.01,fixed_spread_points=2))
        self.assertEqual(len(trades),1)
        self.assertEqual(trades[0]["entry_at"],str(df.index[151]))

    def test_same_bar_sl_and_tp_conservatively_stop(self):
        df = fake_bars()
        df["signal"] = 0
        df["atr"] = 1.
        df.loc[df.index[150],"signal"] = 1
        df.loc[df.index[151],"High"] = float(df.loc[df.index[151],"Open"]+3)
        df.loc[df.index[151],"Low"] = float(df.loc[df.index[151],"Open"]-3)
        _,trades = run_backtest(df,Config(point=.01,fixed_spread_points=2))
        self.assertEqual(trades[0]["reason"],"SL_TP_SAME_BAR")
        self.assertLess(trades[0]["pnl_usd"],0)

    def test_no_signal_is_not_fake_profit_factor(self):
        df = fake_bars()
        df["signal"] = 0
        df["atr"] = 1.
        m,_ = run_backtest(df,Config(point=.01))
        self.assertEqual(m["trades"],0)
        self.assertIsNone(m["profit_factor"])

if __name__ == "__main__":
    unittest.main()
