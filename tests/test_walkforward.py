"""Tests offline: sin broker, sin trade send."""
import unittest
from datetime import datetime,timedelta,timezone
import numpy as np
import pandas as pd
from trading_v2.backtesting.engine import Config,run_backtest
from trading_v2.research.walkforward import ResearchConfig, event_outcome, research, features_from_bars
from trading_v2.research.risk_pause import RiskPause
from trading_v2.strategies.trend_following import add_indicators


def fake_data(n=2500):
    idx=pd.date_range('2024-01-01',periods=n,freq='15min')
    rng=np.random.default_rng(2026)
    returns=rng.normal(0,.3,n)+.04*np.sin(np.arange(n)/40)
    mid=100+np.cumsum(returns)
    return pd.DataFrame({'Open':mid,'High':mid+.5,'Low':mid-.5,'Close':mid+.1,
                         'Spread':np.full(n,2)},index=idx)

class MLTests(unittest.TestCase):
    def test_requires_embargo(self):
        with self.assertRaises(ValueError):ResearchConfig(embargo_bars=32)

    def test_features_do_not_change_with_future(self):
        x=add_indicators(fake_data(500))
        f1=features_from_bars(x)
        y=x.copy()
        y.iloc[400:,y.columns.get_loc('Close')]+=10
        f2=features_from_bars(y)
        self.assertTrue(np.allclose(f1.iloc[100:399],f2.iloc[100:399],equal_nan=True))

    def test_event_matches_engine_one_signal(self):
        x=fake_data(300)
        x['signal']=0
        x['atr']=1.0
        x.loc[x.index[155],'signal']=-1
        conf=Config(point=.01,slippage_points=2,fixed_spread_points=2,max_bars_held=16)
        event,end=event_outcome(x,155,16,conf)
        metrics,trades=run_backtest(x,conf)
        self.assertEqual(metrics['trades'],1)
        self.assertAlmostEqual(trades[0]['realized_R'],event,places=5)
        self.assertEqual(x.index[end],pd.Timestamp(trades[0]['exit_at']))

    def test_poor_signals_abstain(self):
        x=fake_data(2600)
        res=research(x,Config(point=.01,fixed_spread_points=2),
                     ResearchConfig(min_validation_pf=1000,min_validation_trades=10,min_train_samples=20))
        self.assertEqual(res['decision'],'NO_TRADE')
        self.assertIsNone(res['chosen'])
        self.assertNotIn('test',res)

    def test_risk_pause_after_loss(self):
        g=RiskPause()
        now=datetime(2026,10,17,11,tzinfo=timezone.utc)
        g.register_closed_trade(-7,now)
        self.assertEqual(g.can_open_new_trade(now+timedelta(minutes=30))[1],'COOLDOWN')
        self.assertTrue(g.can_open_new_trade(now+timedelta(minutes=61))[0])

    def test_three_losses_halt_without_auto_restart(self):
        g=RiskPause()
        now=datetime(2026,10,17,11,tzinfo=timezone.utc)
        for j in range(3):g.register_closed_trade(-7,now+timedelta(hours=j))
        self.assertFalse(g.can_open_new_trade(now+timedelta(days=2))[0])
        with self.assertRaises(RuntimeError):g.register_closed_trade(2,now+timedelta(days=2))

    def test_daily_loss_halt(self):
        g=RiskPause()
        now=datetime(2026,10,17,11,tzinfo=timezone.utc)
        g.register_closed_trade(-46,now)
        self.assertFalse(g.can_open_new_trade(now+timedelta(hours=2))[0])

if __name__=='__main__': unittest.main()
