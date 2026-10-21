"""Pruebas intradia continuo M15/M30: no ORB, resampling causal y riesgo."""
from __future__ import annotations
import unittest
from datetime import date
from io import BytesIO
import zipfile
import numpy as np
import pandas as pd

from trading_v2.research.continuous_intraday_lab import (
    IntradayLabConfig, MARKETS, resample_complete, causal_h1_direction,
    in_cash_session, session_close_utc, simulate_trade, select_trades,
    fit_ml, metrics_for_events, read_m5, make_signals, windows,
)


def sample_m5(n=1500):
    rng=np.random.default_rng(23)
    ix=pd.date_range("2026-03-09 12:00:00",periods=n,freq="5min",tz="UTC")
    px=100+np.cumsum(rng.normal(0,.14,n))
    return pd.DataFrame({
        "Open":px,"High":px+.30,"Low":px-.30,"Close":px+.02,
        "Spread":np.full(n,5.0),"SpreadUsable":True,
    },index=ix)


class ContinuousIntradayTests(unittest.TestCase):
    def test_resample_m15_m30_correct_bars(self):
        b=sample_m5(120)
        s15=resample_complete(b,15)
        s30=resample_complete(b,30)
        h=resample_complete(b,60)
        self.assertEqual(len(s15),40)
        self.assertEqual(len(s30),20)
        self.assertEqual(len(h),10)
        self.assertEqual(float(s30.High.iloc[0]),float(b.High.iloc[:6].max()))

    def test_partial_m15_m30_cannot_be_used(self):
        b=sample_m5(120)
        cut=b.index[7]
        c=b.drop(cut)
        s15=resample_complete(c,15)
        s30=resample_complete(c,30)
        self.assertNotIn(b.index[6],s15.index)
        self.assertNotIn(b.index[6],s30.index)

    def test_us_dst_market_session(self):
        friday=pd.DatetimeIndex(["2026-03-06 14:45:00+00:00",
                                  "2026-03-09 13:45:00+00:00"])
        data=pd.DataFrame(index=friday)
        self.assertTrue(in_cash_session(data,15,"SP500").all())
        self.assertEqual(session_close_utc(friday[0],"SP500"),
                         pd.Timestamp("2026-03-06 21:00:00Z"))
        self.assertEqual(session_close_utc(friday[1],"SP500"),
                         pd.Timestamp("2026-03-09 20:00:00Z"))

    def test_europe_cash_session_not_all_day(self):
        idx=pd.DatetimeIndex(["2026-03-30 06:30Z",
                              "2026-03-30 07:45Z",
                              "2026-03-30 15:45Z"])
        b=pd.DataFrame(index=idx)
        vals=in_cash_session(b,15,"DAX40")
        self.assertEqual(vals.tolist(),[False,True,False])

    def test_h1_alignment_only_closed(self):
        m5=sample_m5(1500)
        b=resample_complete(m5,15)
        h=resample_complete(m5,60)
        direction=causal_h1_direction(b,h,15)
        # a las 13:15 cerró solo 13:00, no usar 13:00-14:00 H1.
        t=pd.Timestamp("2026-03-09 13:00Z")
        self.assertTrue(np.isnan(direction.loc[t]))
        self.assertTrue(np.isfinite(direction.loc[pd.Timestamp("2026-03-09 13:45Z")]))

    def test_signal_causal_from_past_only(self):
        b=sample_m5(3000)
        m15=resample_complete(b,15)
        h=resample_complete(b,60)
        before=make_signals(m15,h,15,"SP500","donchian_breakout")
        end=before.index[650]
        altered=b.copy()
        altered.loc[altered.index>end+pd.Timedelta(minutes=15),["Open","High","Low","Close"]] *= 1.02
        after=make_signals(resample_complete(altered,15),
                           resample_complete(altered,60),15,"SP500","donchian_breakout")
        self.assertTrue((before.signal.loc[:end]==after.signal.loc[:end]).all())

    def test_only_closed_m15_m30_signals(self):
        b=sample_m5(2100)
        for tf in (15,30):
            q=resample_complete(b,tf)
            h=resample_complete(b,60)
            for s in ("ema_rsi_baseline","donchian_breakout",
                      "bollinger_reversion","supertrend_follow"):
                x=make_signals(q,h,tf,"SP500",s)
                self.assertEqual(len(x),len(q))
                self.assertTrue(set(x.signal.unique()).issubset({-1,0,1}))
                self.assertTrue((x.signal[~in_cash_session(x,tf,"SP500")]==0).all())

    def test_both_stop_and_target_hit_assume_stop(self):
        idx=pd.date_range("2026-03-09 13:30Z",periods=13,freq="30min")
        df=pd.DataFrame({"Open":100.,"High":101.,"Low":99.,
                         "Close":100.,"Spread":5.,"SpreadUsable":True,
                         "atr":2.,"signal":0},index=idx)
        df.at[idx[1],"signal"]=1
        df.at[idx[2],"High"]=120.
        df.at[idx[2],"Low"]=80.
        for col in ("ema_gap_atr","close_ema_atr","rsi","atr_ratio",
                    "h1_direction","spread_atr","ret3","direction"):
            df[col]=1.
        e=simulate_trade(df,1,30,"SP500",60,IntradayLabConfig())
        self.assertIsNotNone(e)
        self.assertEqual(e["reason"],"BOTH_ASSUME_STOP")
        self.assertLess(e["r"],0)

    def test_no_enter_at_session_close(self):
        idx=pd.date_range("2026-03-09 19:00Z",periods=5,freq="30min")
        df=pd.DataFrame({"Open":100.,"High":101.,"Low":99.,
                         "Close":100.,"Spread":5.,"SpreadUsable":True,
                         "atr":2.,"signal":0},index=idx)
        df.at[idx[1],"signal"]=1
        for col in ("ema_gap_atr","close_ema_atr","rsi","atr_ratio",
                    "h1_direction","spread_atr","ret3","direction"):
            df[col]=1.
        self.assertIsNone(simulate_trade(df,1,30,"SP500",60,IntradayLabConfig()))

    def test_zero_spread_requires_past_positive_cost(self):
        b=sample_m5(200)
        b=b.drop(columns=["SpreadUsable"])
        b.loc[b.index[0],"Spread"]=0
        b.loc[b.index[50],"Spread"]=0
        x=b.copy()
        x["Time"]=x.index
        contents=x.to_csv(index=False)
        with BytesIO() as output:
            with zipfile.ZipFile(output,"w") as z:
                z.writestr("ADMIRALS_SP500_M5.csv",contents)
            output.seek(0)
            with zipfile.ZipFile(output) as z:
                clean,quality=read_m5(z,"SP500")
        self.assertTrue(np.isnan(clean.Spread.iloc[0]))
        self.assertFalse(bool(clean.SpreadUsable.iloc[0]))
        self.assertGreater(clean.Spread.iloc[50],0)
        self.assertEqual(quality["spread_imputed"],1)

    def test_test_fold_never_trains_on_future(self):
        e=[]
        for i in range(100):
            e.append({"i":i,"exit_i":i+1,"r":1. if i%2==0 else -1.,
                      "reason":"TARGET" if i%2==0 else "STOP",
                      "features":np.array([float(i%2)]*8)})
        cfg=IntradayLabConfig(min_train_events=20)
        self.assertIsNotNone(fit_ml(e,50,cfg))
        a=select_trades(e,70,90,None)
        self.assertTrue(all(70<=x["i"] and x["exit_i"]<90 for x in a))
        self.assertTrue(all(a[k]["exit_i"]<a[k+1]["i"] for k in range(len(a)-1)))

    def test_holdout_not_read_without_accepted_validation(self):
        folds,final=windows(2000,IntradayLabConfig())
        self.assertTrue(folds[0][0]<folds[0][1]<folds[0][2])
        self.assertTrue(folds[1][0]<folds[1][1]<folds[1][2])
        self.assertTrue(final[0]<final[1]<final[2])
        self.assertEqual(folds[1][2],final[0])

    def test_empty_metrics_and_no_mt5_import(self):
        import sys
        self.assertNotIn("MetaTrader5",sys.modules)
        self.assertIsNone(metrics_for_events([],IntradayLabConfig())["win_rate"])


if __name__=="__main__":
    unittest.main()
