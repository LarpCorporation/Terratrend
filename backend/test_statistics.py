"""Tests for the statistical corrections added after the audit.

Covers: AR(1) variance correction, percent-change suppression on interval
scales, and the slope-difference test that regional contrast now relies on.
"""
import math
import unittest

from analysis import (
    analyze_series, analyze_regional_contrast, mk_test,
    _lag1_autocorr, _ar1_variance_factor,
)


def approx(a, b, tol=1e-6):
    return abs(a - b) <= tol


class TestAutocorrelationCorrection(unittest.TestCase):
    def test_white_noise_has_no_autocorrelation(self):
        # a detrended alternating series is negatively autocorrelated
        ys = [1.0, -1.0] * 10
        self.assertLess(_lag1_autocorr(ys), 0)

    def test_persistent_series_is_positive(self):
        """A series whose *residuals* persist must show positive r1."""
        import random
        rng = random.Random(7)
        noise = 0.0
        ys = []
        for x in range(30):
            noise = 0.8 * noise + rng.gauss(0, 1)   # strong AR(1) noise
            ys.append(10.0 + 0.1 * x + noise)
        self.assertGreater(_lag1_autocorr(ys), 0.3)

    def test_perfect_trend_does_not_look_autocorrelated(self):
        """Detrending is what keeps a real trend from erasing itself."""
        ys = [0.5 * x for x in range(20)]
        r1 = _lag1_autocorr(ys)
        self.assertLess(abs(r1), 0.5, f"detrended r1 should be small, got {r1}")
        factor, _ = _ar1_variance_factor(ys)
        self.assertAlmostEqual(factor, 1.0, places=6)

    def test_factor_never_shrinks_variance(self):
        """A correction must never make a test more confident."""
        for ys in ([1.0, -1.0] * 10,
                   [1.0, 2.0, 1.5, 2.5, 2.0, 3.0, 2.5, 3.5, 3.0, 4.0,
                    3.5, 4.5, 4.0, 5.0, 4.5, 5.5, 5.0, 6.0, 5.5, 6.5]):
            factor, _ = _ar1_variance_factor(ys)
            self.assertGreaterEqual(factor, 1.0)

    def test_correction_never_lowers_p_value(self):
        ys = [10.0 + 0.5 * x + (0.4 if x % 2 else -0.4) for x in range(20)]
        _z0, p_raw, _t0, _h0 = mk_test(ys, autocorr=False)
        _z1, p_cor, _t1, _h1 = mk_test(ys, autocorr=True)
        self.assertLessEqual(p_cor, p_raw + 1e-12)

    def test_positive_autocorr_widens_interval(self):
        """A persistent series must lose significance, not gain it."""
        import random
        rng = random.Random(11)
        noise = 0.0
        ys = []
        for x in range(24):
            noise = 0.85 * noise + rng.gauss(0, 1)
            ys.append(10.0 + 0.05 * x + noise)
        _z0, p_raw, _t, _h = mk_test(ys, autocorr=False)
        _z1, p_cor, _t1, _h1 = mk_test(ys, autocorr=True)
        self.assertGreater(p_cor, p_raw)


class TestPercentChange(unittest.TestCase):
    def test_interval_scale_suppresses_percent(self):
        ys = [10.0 + 0.5 * x for x in range(20)]
        r = analyze_series(ys, percent_ok=False)
        self.assertIsNone(r["change_pct"])
        self.assertIsNotNone(r["change_total"])

    def test_ratio_scale_reports_percent(self):
        ys = [10.0 + 0.5 * x for x in range(20)]
        r = analyze_series(ys, percent_ok=True)
        self.assertIsNotNone(r["change_pct"])

    def test_diagnostics_are_present(self):
        ys = [10.0 + 0.5 * x for x in range(20)]
        r = analyze_series(ys)
        for key in ("autocorr_r1", "autocorr_factor", "p_uncorrected"):
            self.assertIn(key, r)


class TestRegionalContrastDifference(unittest.TestCase):
    var = {"id": "T2M", "name": "Air Temperature", "unit": "C"}
    ra = {"name": "Region A"}
    rb = {"name": "Region B"}

    @staticmethod
    def stats(slope_dec, se_dec, p):
        return {
            "slope": slope_dec / 10.0,
            "t_se": se_dec / 10.0,
            "direction": "rising" if slope_dec > 0 else "falling",
            "p": p,
            "significant": p < 0.05,
        }

    def contrast(self, a, b):
        return analyze_regional_contrast(
            self.var, self.ra, self.rb, [], [], a, b)

    def test_opposite_signs_with_clean_estimates_is_divergent(self):
        c = self.contrast(self.stats(1.0, 0.2, 0.01), self.stats(-1.0, 0.2, 0.02))
        self.assertEqual(c["verdict"], "DIVERGENT / OPPOSING")
        self.assertLess(c["p_diff"], 0.05)

    def test_opposite_signs_but_noisy_is_not_divergent(self):
        """The old code called this DIVERGENT from the sign alone."""
        c = self.contrast(self.stats(1.0, 2.0, 0.60), self.stats(-1.0, 2.0, 0.70))
        self.assertNotEqual(c["verdict"], "DIVERGENT / OPPOSING")
        self.assertEqual(c["verdict"], "NO SIGNIFICANT DIFFERENCE")
        self.assertGreater(c["p_diff"], 0.05)

    def test_same_sign_different_rates(self):
        c = self.contrast(self.stats(1.0, 0.2, 0.01), self.stats(0.1, 0.1, 0.02))
        self.assertEqual(c["verdict"], "SIGNIFICANTLY DIFFERENT RATES")

    def test_p_diff_is_reported(self):
        c = self.contrast(self.stats(1.0, 0.2, 0.01), self.stats(-1.0, 0.2, 0.02))
        self.assertIn("p_diff", c)
        self.assertIsNotNone(c["p_diff"])


if __name__ == "__main__":
    unittest.main()
