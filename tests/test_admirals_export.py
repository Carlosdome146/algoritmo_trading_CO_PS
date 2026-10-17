"""Pruebas del exportador MT5 Admirals. No requieren terminal ni credenciales."""
import csv
import io
import unittest
from types import SimpleNamespace
from scripts.exportar_historial_admirals_mt5 import read_history, gather, SYMBOLS


def makebar(t, spread=12):
    return dict(time=t, open=100., high=101., low=99., close=100.3,
                tick_volume=123, spread=spread, real_volume=0)


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    TIMEFRAME_M15 = 15
    TIMEFRAME_H1 = 60

    def __init__(self, server="AdmiralsGroup-Demo", mode=0):
        self.server=server
        self.mode=mode
        self.read_calls=[]

    def account_info(self):
        company="Admirals Group AS" if "Admirals" in self.server else "MetaQuotes Ltd."
        return SimpleNamespace(trade_mode=self.mode, company=company,
                               server=self.server, currency="EUR", leverage=100,
                               balance=3000.)

    def symbol_info(self, symbol):
        if symbol not in SYMBOLS.values():
            return None
        return SimpleNamespace(visible=True, trade_mode=4, volume_min=.01,
                               volume_step=.01, point=.01, trade_tick_size=.01,
                               trade_contract_size=100, currency_profit="EUR",
                               path="CFD")

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(time=1792195139)

    def copy_rates_from_pos(self, symbol, timeframe, start, count):
        self.read_calls.append((symbol, timeframe, start, count))
        return [makebar(1792000000+900*j) for j in range(count)]

    def last_error(self):
        return (0, "ok")


class ExportTests(unittest.TestCase):
    def test_rows_time_and_spread(self):
        m=FakeMT5()
        data,stats=read_history(m,"GOLD",m.TIMEFRAME_M15,"M15",600)
        records=list(csv.DictReader(io.StringIO(data)))
        self.assertEqual(len(records),600)
        self.assertEqual(stats["spread_median_positive_points"],12)
        self.assertEqual(m.read_calls[0][2],1)
        self.assertEqual(stats["duplicates"],0)
        self.assertEqual(stats["out_of_order"],0)

    def test_metaquotes_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"no se identifica"):
            gather(FakeMT5(server="MetaQuotes-Demo"),500,500)

    def test_live_account_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"NO DEMO"):
            gather(FakeMT5(mode=1),500,500)

    def test_all_instruments(self):
        m=FakeMT5()
        report,files=gather(m,500,500)
        self.assertEqual(len(files),10)
        self.assertEqual(set(report["symbols"]),set(SYMBOLS))
        self.assertEqual(len(m.read_calls),10)
        self.assertTrue(all(x[2]==1 for x in m.read_calls))
        self.assertNotIn("login",report["account"])

    def test_missing_rates(self):
        m=FakeMT5()
        m.copy_rates_from_pos=lambda *args: None
        content,stats=read_history(m,"GOLD",m.TIMEFRAME_M15,"M15",500)
        self.assertIsNone(content)
        self.assertIn("error",stats)

    def test_zero_spread_warning(self):
        m=FakeMT5()
        m.copy_rates_from_pos=lambda *args: [makebar(1792000000+900*j,0) for j in range(500)]
        _,stats=read_history(m,"GOLD",m.TIMEFRAME_M15,"M15",500)
        self.assertTrue(any("NO interpretarlos" in x for x in stats["warnings"]))


if __name__=="__main__":
    unittest.main()
