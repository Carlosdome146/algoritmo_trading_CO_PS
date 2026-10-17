"""Tests Strategy Lab: señales causales, embargo y auditoría de pérdidas."""
import unittest
import numpy as np
import pandas as pd
from scripts import investigar_admirals_v2 as prior
from trading_v2.strategies import STRATEGIES, generate_signals
from trading_v2.strategies.candidates import supertrend_direction
from trading_v2.research.strategy_lab import LabConfig, windows, loss_patterns, research_market, HORIZONS


def bars(n=1000,seed=123):
    rng=np.random.default_rng(seed)
    times=pd.date_range('2026-01-01',periods=n,freq='15min',tz='UTC')
    move=rng.normal(0,.2,n)
    c=100+np.cumsum(move)
    b=pd.DataFrame({'Open':c,'Close':c+.03,'High':c+.25,'Low':c-.25,
                    'Spread':np.full(n,5)},index=times)
    h=b.resample('1h').agg({'Open':'first','Close':'last','High':'max','Low':'min'})
    return prior.causal_indicators(b,h)


class StrategyLabTests(unittest.TestCase):
    def test_strategies_long_short_or_zero(self):
        base=bars()
        for name in STRATEGIES:
            out=generate_signals(base,name,.01)
            self.assertTrue(set(out.signal.unique()).issubset({-1,0,1}),name)
            self.assertEqual(len(out),len(base))

    def test_baseline_preserved(self):
        base=bars()
        out=generate_signals(base,'ema_rsi_baseline',.01)
        self.assertTrue((out.signal==base.signal).all())

    def test_future_cannot_change_historical_signals(self):
        base=bars(1100)
        for name in STRATEGIES:
            prev=generate_signals(base,name,.01)
            future=base.copy()
            cut=850
            for col in ('Open','High','Low','Close','rsi','ema20','ema50','atr','atr_ratio'):
                future.loc[future.index[cut]:,col]*=1.15
            changed=generate_signals(future,name,.01)
            self.assertTrue((prev.signal.iloc[:cut]==changed.signal.iloc[:cut]).all(),name)

    def test_donchian_breakout_uses_prior_high(self):
        base=bars(300)
        base['h1_direction']=1
        base['atr_ratio']=1
        base.iloc[-1,base.columns.get_loc('Close')]=base.High.iloc[-21:-1].max()+1
        base.iloc[-1,base.columns.get_loc('High')]=base.Close.iloc[-1]+.1
        signal=generate_signals(base,'donchian_breakout',.01)
        self.assertEqual(signal.signal.iloc[-1],1)

    def test_supertrend_returns_timed_states(self):
        base=bars()
        st=supertrend_direction(base)
        self.assertEqual(len(st),len(base))
        self.assertTrue(set(st).issubset({-1,0,1}))
        self.assertTrue((st.iloc[:9]==0).all())

    def test_missing_indicator_fails(self):
        with self.assertRaises(ValueError):
            generate_signals(pd.DataFrame({'Close':[1,2]}),'donchian_breakout',.01)

    def test_negative_point_fails(self):
        with self.assertRaises(ValueError):
            generate_signals(bars(200),'supertrend_follow',0)

    def test_embargo_and_fold_nonoverlap(self):
        f,(endtrain,test_start,n)=windows(12000,LabConfig())
        self.assertEqual(endtrain,int(.78*12000))
        self.assertEqual(test_start-endtrain,40)
        self.assertTrue(all(start-train==40 for train,start,end in f))
        self.assertTrue(f[0][2]<=f[1][1] and f[1][2]<=test_start)

    def test_unsafe_embargo_rejected(self):
        with self.assertRaises(ValueError):
            LabConfig(embargo=32)

    def test_no_candidate_no_holdout(self):
        b=bars(3200)
        ohlc=b[['Open','High','Low','Close','Spread']].copy()
        h=ohlc.resample('1h').agg({'Open':'first','Close':'last','High':'max','Low':'min'})
        r=research_market(ohlc,h,.01,LabConfig(min_pf=100000.))
        self.assertEqual(r['decision'],'NO_TRADE')
        self.assertIsNone(r['holdout'])
        self.assertEqual(len(r['validation_candidates']),len(STRATEGIES)*len(HORIZONS)*2)

    def test_empty_loss_report(self):
        b=bars(100)
        r=loss_patterns(b,[],None,None,4,.01,50,100,LabConfig())
        self.assertEqual(r['losers'],0)
        self.assertIsNone(r['median_spread_atr_losses'])

    def test_no_mt5_import(self):
        import sys
        self.assertNotIn('MetaTrader5',sys.modules)


class ResearchDecisionTests(unittest.TestCase):
    def test_archive_gate_rejects_non_demo(self):
        from trading_v2.research.strategy_lab import run_archive
        import zipfile, json, tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            zpath=Path(td)/'sample.zip'
            with zipfile.ZipFile(zpath,'w') as z:
                z.writestr('admirals_manifest.json', json.dumps({'account':{'demo':False,'company':'Admirals Group AS','currency':'EUR'}}))
            with self.assertRaisesRegex(ValueError,'Admirals DEMO'):
                run_archive(zpath, LabConfig())

    def test_loss_report_for_real_selected_candidate(self):
        # Umbrales permisivos SOLO para ejercitar la ruta del test.
        base=bars(3300)
        ohlc=base[['Open','High','Low','Close','Spread']].copy()
        h=ohlc.resample('1h').agg({'Open':'first','Close':'last','High':'max','Low':'min'})
        r=research_market(ohlc,h,.01,LabConfig(min_pf=0,min_mean_r=-100,min_trades_fold=1,min_trades_final=1))
        self.assertIsNotNone(r['chosen'])
        self.assertIsNotNone(r['holdout'])
        la=r['holdout']['loss_analysis']
        self.assertEqual(la['trades_recorded'],r['holdout']['spread_plus_slippage']['trades'])
        self.assertLessEqual(la['losers'],la['trades_recorded'])
        self.assertIn(r['decision'],('NO_TRADE','FURTHER_RESEARCH_ONLY'))


if __name__=='__main__':
    unittest.main()
