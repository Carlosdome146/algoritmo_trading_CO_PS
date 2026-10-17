"""Pruebas de investigación multiactivo (sin terminal MetaTrader5)."""
import unittest
import numpy as np
import pandas as pd
from scripts import investigar_admirals_v2 as m

def synthetic(n=500):
    idx=pd.date_range('2026-01-01',periods=n,freq='15min',tz='UTC')
    q=np.linspace(100,130,n)
    return pd.DataFrame({'Open':q,'High':q+1,'Low':q-1,'Close':q+.1,'Spread':np.full(n,10)},index=idx)

class Verify(unittest.TestCase):
    def test_offline_import(self):
        import sys
        self.assertNotIn('MetaTrader5',sys.modules)

    def test_h1_reconstruction_perfect(self):
        bars=synthetic(2400)
        h=bars.resample('1h').agg({'Open':'first','High':'max','Low':'min','Close':'last'})
        self.assertEqual(m.check_m15_h1_consistency(bars,h)['mismatches'],0)

    def test_h1_mismatch_rejected(self):
        bars=synthetic(2400)
        h=bars.resample('1h').agg({'Open':'first','High':'max','Low':'min','Close':'last'})
        h.iloc[1,h.columns.get_loc('Close')]+=.1
        with self.assertRaisesRegex(ValueError,'no coinciden'):
            m.check_m15_h1_consistency(bars,h)

    def test_no_h1_lookahead(self):
        b=synthetic(800)
        h=b.resample('1h').agg({'Open':'first','High':'max','Low':'min','Close':'last'})
        first=m.causal_indicators(b,h)
        h.loc[h.index[-30]:,'Close']+=1000
        second=m.causal_indicators(b,h)
        self.assertTrue((first.signal.iloc[:450]==second.signal.iloc[:450]).all())

    def test_long_pays_bid_ask_spread(self):
        b=synthetic(150)
        b['atr']=1.;b['signal']=0.
        b.loc[b.index[80],'signal']=1
        r,_,_=m.simulate_event(m.arrays_from(b),80,1,.01)
        self.assertAlmostEqual(r,(b.Close.iloc[81]-b.Open.iloc[81]-.1)/1.2,places=6)

    def test_short_pays_bid_ask_spread(self):
        b=synthetic(150)
        b['atr']=1.;b['signal']=0.
        b.loc[b.index[80],'signal']=-1
        r,_,_=m.simulate_event(m.arrays_from(b),80,1,.01)
        self.assertAlmostEqual(r,(-b.Close.iloc[81]-.1+b.Open.iloc[81])/1.2,places=6)

    def test_same_bar_stop_priority(self):
        b=synthetic(150)
        b['atr']=1.;b['signal']=0.
        b.loc[b.index[80],'signal']=1
        b.loc[b.index[81],'High']=b.Open.iloc[81]+4
        b.loc[b.index[81],'Low']=b.Open.iloc[81]-4
        r,_,reason=m.simulate_event(m.arrays_from(b),80,1,.01)
        self.assertEqual(reason,'BOTH_ASSUME_STOP')
        self.assertLess(r,0)

    def test_slippage_worsens_one_trade(self):
        b=synthetic(150)
        b['atr']=1.;b['signal']=0.
        b.loc[b.index[80],'signal']=1
        a=m.arrays_from(b)
        base=m.simulate_event(a,80,1,.01,0)[0]
        stress=m.simulate_event(a,80,1,.01,.5)[0]
        self.assertLess(stress,base)

    def test_no_trades_no_fake_pf(self):
        self.assertIsNone(m.metrics([],3000)['profit_factor'])

    def test_no_future_conditional_event_filter(self):
        b=synthetic(200)
        b['signal']=0.; b['atr']=1.
        event=(197,198,1.,np.ones(len(m.FEATURES)))
        x=m.backtest_events(b,[event],None,None,4,.01,180,200,m.Params())
        self.assertEqual(x['trades'],0)

if __name__ == '__main__':
    unittest.main()
