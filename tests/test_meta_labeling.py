"""Pruebas unitarias para el módulo de Meta-Labeling Cuantitativo y Sincronía Intermercado."""
import unittest

from trading_v2.research.meta_labeling import (
    AssetRegimeSnapshot,
    evaluate_meta_label,
)


class MetaLabelingTests(unittest.TestCase):
    def test_high_conviction_synchronized_bull_dip(self):
        dax = AssetRegimeSnapshot("GERMANY40", close=25000.0, sma200=24000.0, rsi2=6.5, ibs=0.12, z_bollinger=2.15)
        sp500 = AssetRegimeSnapshot("[SP500]", close=7600.0, sma200=7200.0, rsi2=14.0, ibs=0.25, z_bollinger=1.80)
        ibex = AssetRegimeSnapshot("[IBEX35]", close=18900.0, sma200=18200.0, rsi2=19.0, ibs=0.30, z_bollinger=1.60)

        res = evaluate_meta_label(dax, side=1, peer_snapshots=[sp500, ibex])
        self.assertEqual(res.tier, "HIGH_CONVICTION")
        self.assertGreaterEqual(res.meta_score, 85.0)
        self.assertEqual(res.risk_multiplier, 1.25)
        self.assertEqual(res.bull_peers_count, 3)
        self.assertEqual(res.sync_pullback_count, 3)

    def test_standard_conviction_isolated_signal(self):
        dax = AssetRegimeSnapshot("GERMANY40", close=25000.0, sma200=24000.0, rsi2=8.0, ibs=0.35, z_bollinger=1.50)
        sp500 = AssetRegimeSnapshot("[SP500]", close=7000.0, sma200=7200.0, rsi2=55.0, ibs=0.60, z_bollinger=0.40)

        res = evaluate_meta_label(dax, side=1, peer_snapshots=[sp500])
        self.assertEqual(res.tier, "STANDARD")
        self.assertEqual(res.risk_multiplier, 0.75)
        self.assertGreaterEqual(res.meta_score, 40.0)
        self.assertLess(res.meta_score, 70.0)

    def test_veto_when_below_sma200_and_weak_stretch(self):
        dax = AssetRegimeSnapshot("GERMANY40", close=23000.0, sma200=24000.0, rsi2=30.0, ibs=0.50, z_bollinger=0.80)
        res = evaluate_meta_label(dax, side=1, peer_snapshots=[])
        self.assertEqual(res.tier, "LOW_CONVICTION_VETO")
        self.assertEqual(res.risk_multiplier, 0.0)
        self.assertLess(res.meta_score, 40.0)

    def test_invalid_side_raises(self):
        dax = AssetRegimeSnapshot("GERMANY40", close=25000.0, sma200=24000.0, rsi2=8.0, ibs=0.15, z_bollinger=2.0)
        with self.assertRaises(ValueError):
            evaluate_meta_label(dax, side=0)


if __name__ == "__main__":
    unittest.main()
