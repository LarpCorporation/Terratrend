"""Tests for the interconnectivity engine.

These lock in the properties that make the feature trustworthy: the engine
must recover a direction it was given, must reject pure coincidence driven by
a shared trend, and must not report physics from noise.
"""
import math
import random
import unittest

import interconnect


def _months(n):
    return [f"{2005 + i // 12}-{i % 12 + 1:02d}" for i in range(n)]


def _seasonal(n, amp=1.0, trend=0.0, phase=0.0, noise=0.15, seed=1):
    rnd = random.Random(seed)
    return [amp * math.sin((i / 12.0) * 2 * math.pi + phase)
            + trend * i + noise * rnd.gauss(0, 1) for i in range(n)]


class TestDecomposition(unittest.TestCase):
    def test_requires_enough_months(self):
        with self.assertRaises(ValueError):
            interconnect.decompose_monthly([1.0] * 10)

    def test_removes_seasonal_cycle(self):
        series = _seasonal(240, amp=5.0, noise=0.0)
        d = interconnect.decompose_monthly(series)
        # a pure seasonal signal plus no trend leaves almost no anomaly
        self.assertLess(d["sigma"], 0.5)

    def test_removes_trend(self):
        series = _seasonal(240, amp=0.0, trend=0.05, noise=0.0)
        d = interconnect.decompose_monthly(series)
        self.assertLess(d["sigma"], 1e-6)

    def test_preserves_none(self):
        series = [1.0] * 60
        series[10] = None
        d = interconnect.decompose_monthly(series)
        self.assertIsNone(d["values"][10])


class TestCrossCorrelation(unittest.TestCase):
    def test_recovers_known_lag(self):
        n = 240
        base = _seasonal(n, amp=1.0, noise=0.05, seed=3)
        lagged = [None] * 4 + base[:-4]   # lagged[t] = base[t-4]
        ccf = interconnect.cross_corr_best(lagged, base, max_lag=8)
        self.assertGreater(ccf["r"], 0.9)
        # negative lag: x trails y, i.e. base leads lagged by 4 months
        self.assertEqual(ccf["lag"], -4)

    def test_zero_lag_is_symmetric(self):
        n = 200
        a = _seasonal(n, seed=11)
        ccf = interconnect.cross_corr_best(a, a, max_lag=6)
        self.assertAlmostEqual(ccf["r"], 1.0, places=3)


class TestGranger(unittest.TestCase):
    def test_detects_predictive_direction(self):
        n = 240
        base = _seasonal(n, amp=1.0, noise=0.05, seed=5)
        follower = [0.0] * 3 + [v for v in base[:-3]]
        follower = [v + 0.05 * math.sin(i) for i, v in enumerate(follower)]
        p_ab, p_ba = interconnect.granger_f_test(base, follower)
        self.assertIsNotNone(p_ab)
        self.assertLess(p_ab, 0.05)

    def test_no_information_gives_no_signal(self):
        n = 240
        rnd = random.Random(9)
        a = [rnd.gauss(0, 1) for _ in range(n)]
        b = [rnd.gauss(0, 1) for _ in range(n)]
        p_ab, p_ba = interconnect.granger_f_test(a, b)
        self.assertGreater(p_ab, 0.01)


class TestLocalCouplings(unittest.TestCase):
    def test_relationship_explanation_squares_correlation_and_limits_attribution(self):
        pair={'a':'A','b':'B','r_lagged':.65,'p':.0000005,'r_partial':.6,'lag_months':0}
        text=interconnect.describe_coupling({'name':'Soil temperature'},{'name':'Air temperature'},pair)
        self.assertIn('42%',text);self.assertNotIn('65%',text)
        self.assertIn('p<0.001',text)
        self.assertIn('does not establish physical causation',text)
        self.assertNotIn('evidence of a direct',text)

    def test_recovers_planted_driver(self):
        n = 240
        driver = _seasonal(n, amp=1.0, noise=0.08, seed=21)
        follower = [None] * 2 + driver[:-2]
        follower = [v if v is None else v * 0.8 + 0.1 * math.sin(i)
                    for i, v in enumerate(follower)]
        series = {"A": driver, "B": follower, "T2M": _seasonal(n, seed=33)}
        pairs = interconnect.analyze_local_couplings(None, series, _months(n))
        ab = next(p for p in pairs if {p["a"], p["b"]} == {"A", "B"})
        # a noisy follower of a dominant driver: expect a strong, not perfect, r
        self.assertGreater(abs(ab["r"]), 0.6)
        self.assertEqual(ab["driver"], "A")

    def test_shared_trend_alone_is_screened(self):
        # two independent rising series: the confounder screen should leave
        # a low partial correlation even though the raw r is high
        n = 240
        rnd = random.Random(77)
        a = [0.05 * i + rnd.gauss(0, 0.4) for i in range(n)]
        b = [0.05 * i + rnd.gauss(0, 0.4) for i in range(n)]
        part = interconnect.partial_corr(a, b, [0.05 * i for i in range(n)])
        self.assertLess(abs(part["r"] or 0), 0.5)


class TestAnomaly(unittest.TestCase):
    def test_episodes_detected(self):
        n = 120
        values = [0.0] * n
        for i in range(20, 26):
            values[i] = 2.0
        eps = interconnect.anomaly_episodes(values, _months(n), sigma=1.0)
        self.assertEqual(len(eps), 1)
        self.assertEqual(eps[0]["n"], 6)

    def test_report_narrative_mentions_counts(self):
        n = 120
        values = [0.0] * n
        values[5] = 3.0
        rep = interconnect.anomaly_report(values, _months(n))
        self.assertIn("of 120 months", rep["narrative"])
        self.assertEqual(rep["peak_month"], _months(n)[5])


class TestImpactPair(unittest.TestCase):
    def test_detects_remote_response(self):
        n = 240
        src = _seasonal(n, amp=1.0, noise=0.1, seed=41)
        tgt = [v * 0.8 + 0.15 for v in src]
        diag = interconnect.impact_pair(src, tgt, _months(n))
        self.assertIsNotNone(diag)
        self.assertGreater(diag["r"], 0.7)
        self.assertLess(diag["p"], 0.05)
        self.assertGreater(abs(diag["composite"]["effect_sigma"]), 0.3)

    def test_ignores_unrelated_series(self):
        n = 240
        rnd = random.Random(101)
        src = [rnd.gauss(0, 1) for _ in range(n)]
        tgt = [rnd.gauss(0, 1) for _ in range(n)]
        diag = interconnect.impact_pair(src, tgt, _months(n))
        self.assertTrue(diag is None or diag["p"] > 0.01)


if __name__ == "__main__":
    unittest.main()
