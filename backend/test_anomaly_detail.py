"""Anomaly decomposition, episode detection and per-month drill-down.

These tests exercise the behaviour the interface explains to a reader:

* the baseline is a calendar-month climatology plus a linear trend fitted to
  the whole supplied series, so ``expected`` can be reconstructed exactly;
* episodes are listed for the high side *and* the low side, are never joined
  across a missing month, and a completed episode is never dropped at a gap;
* zero variance and short coverage produce honest states instead of a
  misleading "0 months above threshold";
* the report distinguishes above- from below-baseline behaviour and never
  claims an extreme event or an attribution.
"""
import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import interconnect  # noqa: E402


def months(n, start_year=2000):
    return ["%04d-%02d" % (start_year + i // 12, i % 12 + 1) for i in range(n)]


def seasonal(n, *, trend=0.02, amplitude=1.0, noise=0.0, seed=7, base=10.0):
    """Synthetic series: linear trend + strict 12-month cycle (+ optional noise)."""
    rnd = random.Random(seed)
    values = []
    for i in range(n):
        cycle = amplitude * math.sin(2 * math.pi * (i % 12) / 12.0)
        jitter = rnd.gauss(0, noise) if noise else 0.0
        values.append(base + trend * i + cycle + jitter)
    return values


class BaselineTests(unittest.TestCase):
    def test_expected_reconstructs_a_known_series(self):
        n = 120
        values = seasonal(n)
        detail = interconnect.anomaly_detail(values, months(n))
        self.assertEqual(detail["status"], "ok")
        self.assertEqual(len(detail["months"]), n)
        # Away from the residual scale the fitted baseline should reproduce the
        # observations of a noiseless trend+cycle series almost exactly.
        worst = max(abs(row["observed"] - row["expected"]) for row in detail["months"])
        self.assertLess(worst, 0.05, "expected should reconstruct a noiseless seasonal+trend series")
        for row in detail["months"]:
            self.assertAlmostEqual(row["departure"], row["observed"] - row["expected"], places=6)

    def test_baseline_describes_period_threshold_and_method(self):
        n = 120
        detail = interconnect.anomaly_detail(seasonal(n, noise=0.3), months(n))
        baseline = detail["baseline"]
        self.assertIsInstance(baseline, dict)
        text = " ".join(str(value) for value in baseline.values())
        self.assertIn("climatology", text)
        self.assertIn("trend", text)
        self.assertEqual(detail["threshold_sigma"], 1.0)
        self.assertEqual(detail["baseline_period"]["valid_months"], n)
        self.assertEqual(detail["summary"]["missing_months"], 0)

    def test_missing_months_are_reported_without_imputation(self):
        n = 120
        values = seasonal(n, noise=0.2)
        values[40] = None
        detail = interconnect.anomaly_detail(values, months(n))
        self.assertEqual(detail["status"], "ok")
        row = detail["months"][40]
        self.assertIsNone(row["observed"])
        self.assertIsNone(row["departure"])
        self.assertIsNone(row["sigma_units"])
        self.assertIsNotNone(row["expected"], "the fitted baseline still exists for a missing month")
        self.assertEqual(detail["summary"]["missing_months"], 1)

    def test_window_never_refits_a_different_baseline(self):
        n = 120
        values = seasonal(n, noise=0.25)
        whole = interconnect.anomaly_detail(values, months(n))
        windowed = interconnect.anomaly_detail(values, months(n), start=months(n)[24], end=months(n)[60])
        self.assertEqual(len(windowed["months"]), 37)
        by_month = {row["month"]: row for row in whole["months"]}
        for row in windowed["months"]:
            self.assertAlmostEqual(row["expected"], by_month[row["month"]]["expected"], places=6)


class EpisodeTests(unittest.TestCase):
    def test_high_side_episode_is_found_with_its_length(self):
        n = 120
        values = [0.0] * n
        for i in range(20, 26):
            values[i] = 2.0
        episodes = interconnect.anomaly_episodes(values, months(n), sigma=1.0)
        self.assertEqual(len(episodes), 1)
        self.assertEqual(episodes[0]["side"], "above")
        self.assertEqual(episodes[0]["months"], 6)
        self.assertEqual(episodes[0]["n"], 6)
        self.assertEqual(episodes[0]["start"], months(n)[20])
        self.assertEqual(episodes[0]["end"], months(n)[25])
        self.assertFalse(episodes[0]["truncated"])

    def test_low_side_episode_is_found(self):
        n = 120
        values = [0.0] * n
        for i in range(50, 56):
            values[i] = -1.8
        episodes = interconnect.anomaly_episodes(values, months(n), sigma=1.0)
        self.assertEqual(len(episodes), 1)
        self.assertEqual(episodes[0]["side"], "below")
        self.assertLess(episodes[0]["peak_sigma"], 0)
        self.assertEqual(episodes[0]["months"], 6)

    def test_both_sides_are_separate_episodes(self):
        n = 120
        values = [0.0] * n
        for i in range(10, 13):
            values[i] = 2.0
        for i in range(40, 44):
            values[i] = -2.0
        episodes = interconnect.anomaly_episodes(values, months(n), sigma=1.0)
        self.assertEqual([e["side"] for e in episodes], ["above", "below"])

    def test_a_gap_closes_an_episode_instead_of_dropping_it(self):
        n = 120
        values = [0.0] * n
        for i in range(20, 31):
            values[i] = 2.0
        values[25] = None  # a missing month inside the run
        episodes = interconnect.anomaly_episodes(values, months(n), sigma=1.0)
        self.assertEqual(len(episodes), 2, "the completed run before the gap must not be lost")
        self.assertEqual(episodes[0]["start"], months(n)[20])
        self.assertEqual(episodes[0]["end"], months(n)[24])
        self.assertEqual(episodes[0]["months"], 5)
        self.assertEqual(episodes[1]["start"], months(n)[26])
        self.assertEqual(episodes[1]["end"], months(n)[30])
        self.assertEqual(episodes[1]["months"], 5)
        # Observations are never joined across the gap.
        self.assertNotEqual(episodes[0]["end"], episodes[1]["start"])

    def test_trailing_episode_is_marked_truncated(self):
        n = 120
        values = [0.0] * n
        for i in range(115, 120):
            values[i] = 2.0
        episodes = interconnect.anomaly_episodes(values, months(n), sigma=1.0)
        self.assertEqual(len(episodes), 1)
        self.assertTrue(episodes[0]["truncated"])

    def test_episode_threshold_and_mean_are_reported(self):
        n = 120
        values = [0.0] * n
        values[10:14] = [1.5, 2.5, 3.5, 1.2]
        episodes = interconnect.anomaly_episodes(values, months(n), sigma=1.0)
        self.assertEqual(len(episodes), 1)
        episode = episodes[0]
        self.assertEqual(episode["threshold_sigma"], 1.0)
        self.assertEqual(episode["peak_sigma"], 3.5)
        self.assertEqual(episode["peak_month"], months(n)[12])
        self.assertAlmostEqual(episode["mean_sigma"], (1.5 + 2.5 + 3.5 + 1.2) / 4)


class HonestStateTests(unittest.TestCase):
    def test_zero_variance_is_its_own_state(self):
        n = 120
        values = [5.0] * n
        detail = interconnect.anomaly_detail(values, months(n))
        self.assertEqual(detail["status"], "zero_variance")
        self.assertEqual(detail["episodes"], [])
        self.assertIsNone(detail["summary"]["months_above"])
        report = interconnect.anomaly_report(values, months(n))
        self.assertEqual(report["status"], "zero_variance")
        self.assertNotIn("peak +0.0", report["narrative"])

    def test_insufficient_coverage_is_its_own_state(self):
        n = 8
        values = seasonal(n)
        detail = interconnect.anomaly_detail(values, months(n))
        self.assertEqual(detail["status"], "insufficient_data")
        self.assertIsNone(detail["baseline"])
        self.assertEqual(detail["episodes"], [])
        self.assertIn("months", detail["message"])
        report = interconnect.anomaly_report(values, months(n))
        self.assertEqual(report["status"], "insufficient_data")

    def test_all_missing_series_does_not_invent_an_analysis(self):
        report = interconnect.anomaly_report([None] * 120, months(120))
        self.assertIsNone(report)


class ReportTests(unittest.TestCase):
    def test_report_adds_sides_baseline_and_threshold(self):
        n = 120
        # anomaly_report consumes RESIDUALS (the seasonal cycle and the fitted
        # trend already removed), which is what every caller passes.
        values = interconnect.decompose_monthly(seasonal(n, noise=0.0))["values"]
        values[30] = values[30] + 6.0     # a strong positive departure
        values[70] = values[70] - 6.0     # a strong negative departure
        report = interconnect.anomaly_report(values, months(n))
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["threshold_sigma"], 1.0)
        self.assertIn("baseline_period", report)
        self.assertIn("valid_months", report["baseline_period"])
        self.assertIn("episodes_above", report)
        self.assertIn("episodes_below", report)
        self.assertGreaterEqual(report["months_above"], 1)
        self.assertGreaterEqual(report["months_below"], 1)
        self.assertIn("side_narrative", report)
        sides = report["side_narrative"]
        self.assertIn("above", sides.lower())
        self.assertIn("below", sides.lower())

    def test_report_episodes_keep_their_side(self):
        n = 120
        values = interconnect.decompose_monthly(seasonal(n, noise=0.0))["values"]
        values[30] = values[30] + 6.0
        values[70] = values[70] - 6.0
        report = interconnect.anomaly_report(values, months(n))
        sides = {episode.get("side") for episode in report["episodes"]}
        self.assertEqual(sides, {"above", "below"})

    def test_narrative_does_not_claim_hazard_or_attribution(self):
        n = 120
        values = interconnect.decompose_monthly(seasonal(n, noise=0.4))["values"]
        report = interconnect.anomaly_report(values, months(n))
        text = (report["narrative"] + " " + report.get("side_narrative", "")).lower()
        # It may only mention a cause or a hazard in order to disclaim one.
        for claim in ("caused by", "because of", "due to a", "this is a hazard",
                      "will cause", "leads to drought", "forecast"):
            self.assertNotIn(claim, text)
        self.assertIn("not an extreme-event or hazard assessment", text)
        self.assertIn("do not attribute a cause", text)
        self.assertIn("trend", text)

    def test_decomposition_keeps_its_existing_contract(self):
        n = 120
        values = seasonal(n, noise=0.3)
        result = interconnect.decompose_monthly(values)
        for key in ("values", "climatology", "trend_slope_per_month", "sigma"):
            self.assertIn(key, result)
        # The drift folded back into the trend must be small for a clean series.
        self.assertAlmostEqual(result["trend_slope_per_month"], 0.02, places=3)
        self.assertEqual(len(result["climatology"]), 12)

    def test_detail_episodes_match_report_episodes(self):
        n = 120
        values = seasonal(n, noise=0.15)
        for i in (44, 45, 46):
            values[i] += 5.0
        detail = interconnect.anomaly_detail(values, months(n))
        report = interconnect.anomaly_report(values, months(n))
        self.assertEqual(len(detail["episodes"]), len(report["episodes"]))
        for episode in detail["episodes"]:
            self.assertIn("side", episode)
            self.assertIn("threshold_sigma", episode)


if __name__ == "__main__":
    unittest.main()
