"""Pruebas ORB: causalidad, rango real, DST, precios ejecutables y seguridad."""
import unittest
from dataclasses import replace
from datetime import date
import numpy as np
import pandas as pd

from trading_v2.strategies.orb import (
    ORBConfig, market_open_utc, generate_orb_signals, validate_m5,
)
from trading_v2.research.orb_lab import ORBLabConfig,trade_events,event_metrics,split_sessions


def example(symbol="[SP500]", day=date(2026,3,9)):
    op=market_open_utc(symbol,day)
    idx=pd.date_range(op-pd.Timedelta(minutes=90),op+pd.Timedelta(hours=4),
                      freq="5min",tz="UTC")
    b=pd.DataFrame({"Open":100.,"High":101.,"Low":99.,"Close":100.,"Spread":5.},
                   index=idx)
    return b,op


def set_breakout(df,when,side=1):
    df.at[when,"Open"]=100.
    if side==1:
        df.at[when,"Close"]=103.
        df.at[when,"High"]=104.
        df.at[when,"Low"]=99.
    else:
        df.at[when,"Close"]=97.
        df.at[when,"High"]=101.
        df.at[when,"Low"]=96.
    return df


class ORBSignalTests(unittest.TestCase):
    def test_us_dst_changes_utc_open(self):
        self.assertEqual(market_open_utc("[SP500]",date(2026,3,6)).hour,14)
        self.assertEqual(market_open_utc("[SP500]",date(2026,3,9)).hour,13)

    def test_europe_dst_changes_utc_open(self):
        self.assertEqual(market_open_utc("GERMANY40",date(2026,3,27)).hour,8)
        self.assertEqual(market_open_utc("GERMANY40",date(2026,3,30)).hour,7)

    def test_session_open_is_not_every_15min(self):
        b,op=example()
        s=generate_orb_signals(b,ORBConfig("[SP500]",range_minutes=15),.01)
        self.assertEqual(int(s.signal.sum()),0)
        self.assertFalse(s.orb_ready.loc[op])
        self.assertTrue(s.orb_ready.loc[op+pd.Timedelta(minutes=15)])

    def test_breakout_15_only_after_range_complete(self):
        b,op=example()
        set_breakout(b,op+pd.Timedelta(minutes=15))
        s=generate_orb_signals(b,ORBConfig("[SP500]",range_minutes=15),.01)
        self.assertEqual(s.signal.loc[op+pd.Timedelta(minutes=15)],1)
        self.assertEqual(int((s.signal!=0).sum()),1)

    def test_breakout_30_ignores_move_during_opening_range(self):
        b,op=example()
        set_breakout(b,op+pd.Timedelta(minutes=15))
        b.at[op+pd.Timedelta(minutes=20),"Close"]=100.
        b.at[op+pd.Timedelta(minutes=20),"High"]=101.
        b.at[op+pd.Timedelta(minutes=20),"Low"]=99.
        s=generate_orb_signals(b,ORBConfig("[SP500]",range_minutes=30),.01)
        self.assertTrue((s.signal.loc[op:op+pd.Timedelta(minutes=25)]==0).all())

    def test_retest_requires_later_bar(self):
        b,op=example()
        breakout=op+pd.Timedelta(minutes=15)
        set_breakout(b,breakout)
        retest=breakout+pd.Timedelta(minutes=5)
        b.at[retest,"Open"]=101.
        b.at[retest,"High"]=104.
        b.at[retest,"Low"]=100.5
        b.at[retest,"Close"]=103.
        s=generate_orb_signals(b,ORBConfig("[SP500]",range_minutes=15,mode="retest"),.01)
        self.assertEqual(s.signal.loc[breakout],0)
        self.assertEqual(s.signal.loc[retest],1)

    def test_incomplete_range_cannot_trade(self):
        b,op=example()
        b=b.drop(op+pd.Timedelta(minutes=5))
        set_breakout(b,op+pd.Timedelta(minutes=15))
        s=generate_orb_signals(b,ORBConfig("[SP500]"),.01)
        self.assertEqual(int((s.signal!=0).sum()),0)

    def test_future_data_never_changes_prior_signals(self):
        b,op=example()
        set_breakout(b,op+pd.Timedelta(minutes=15))
        orig=generate_orb_signals(b,ORBConfig("[SP500]"),.01)
        limit=op+pd.Timedelta(minutes=55)
        altered=b.copy()
        for t in altered.index[altered.index>limit]:
            set_breakout(altered,t,-1)
        new=generate_orb_signals(altered,ORBConfig("[SP500]"),.01)
        self.assertTrue((orig.signal.loc[:limit]==new.signal.loc[:limit]).all())

    def test_short_breakout(self):
        b,op=example()
        set_breakout(b,op+pd.Timedelta(minutes=15),-1)
        s=generate_orb_signals(b,ORBConfig("[SP500]"),.01)
        self.assertEqual(s.signal.loc[op+pd.Timedelta(minutes=15)],-1)

    def test_bad_config_not_accepted(self):
        with self.assertRaises(ValueError):
            ORBConfig("[SP500]",range_minutes=10)
        with self.assertRaises(ValueError):
            ORBConfig("EURUSD")
        with self.assertRaises(ValueError):
            ORBConfig("[SP500]",mode="fake")

    def test_spread_zero_rejected(self):
        b,_=example()
        b.iloc[0,b.columns.get_loc("Spread")]=0
        with self.assertRaisesRegex(ValueError,"spreads"):
            validate_m5(b)

    def test_no_reconstruction_from_unsafe_timestamps(self):
        b,_=example()
        b=b.reset_index(drop=True)
        with self.assertRaisesRegex(ValueError,"DatetimeIndex"):
            validate_m5(b)

    def test_missing_session_bars_unusable(self):
        b,_=example()
        with self.assertRaisesRegex(ValueError,"100 sesiones"):
            split_sessions(generate_orb_signals(b,ORBConfig("[SP500]"),.01),"[SP500]")


class ORBBacktestTests(unittest.TestCase):
    def test_signal_executed_next_m5_open(self):
        b,op=example()
        breakout=op+pd.Timedelta(minutes=15)
        set_breakout(b,breakout)
        s=generate_orb_signals(b,ORBConfig("[SP500]"),.01)
        ev=trade_events(s,.01,1.5,ORBLabConfig())
        self.assertEqual(len(ev),1)
        self.assertEqual(pd.Timestamp(ev[0]["entry"]),breakout+pd.Timedelta(minutes=5))

    def test_same_bar_stop_before_target(self):
        b,op=example()
        breakout=op+pd.Timedelta(minutes=15)
        set_breakout(b,breakout)
        nextbar=breakout+pd.Timedelta(minutes=5)
        b.at[nextbar,"Open"]=100.
        b.at[nextbar,"High"]=110.
        b.at[nextbar,"Low"]=90.
        b.at[nextbar,"Close"]=100.
        s=generate_orb_signals(b,ORBConfig("[SP500]"),.01)
        e=trade_events(s,.01,1.0,ORBLabConfig())
        self.assertEqual(e[0]["reason"],"BOTH_ASSUME_STOP")
        self.assertLess(e[0]["r"],0)

    def test_stress_cost_never_improves_same_trade(self):
        b,op=example()
        set_breakout(b,op+pd.Timedelta(minutes=15))
        s=generate_orb_signals(b,ORBConfig("[SP500]"),.01)
        with_slip=trade_events(s,.01,1.5,ORBLabConfig(slippage_spread_fraction=.5))
        no_slip=trade_events(s,.01,1.5,ORBLabConfig(slippage_spread_fraction=0))
        self.assertEqual(len(with_slip),len(no_slip))
        self.assertLessEqual(with_slip[0]["r"],no_slip[0]["r"]+1e-8)

    def test_empty_metrics_never_fake_profit_factor(self):
        self.assertIsNone(event_metrics([],ORBLabConfig())["profit_factor"])

    def test_archive_is_offline_import(self):
        import sys
        self.assertNotIn("MetaTrader5",sys.modules)


if __name__=="__main__":
    unittest.main()
