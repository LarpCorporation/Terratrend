"""Tests for data-currency logic: partial-year exclusion and year caps."""
import datetime
import unittest

import server
from server import _annualize, _complete_years, MIN_MONTHS_PER_YEAR


def months_of(year, n):
    return [f"{year}-{m:02d}" for m in range(1, n + 1)]


class TestPartialYear(unittest.TestCase):
    def test_full_year_is_complete(self):
        labels = months_of(2020, 12)
        out = _annualize(labels, [1.0] * 12)
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0]["complete"])
        self.assertEqual(out[0]["months"], 12)
        self.assertAlmostEqual(out[0]["value"], 1.0)

    def test_partial_year_flagged(self):
        labels = months_of(2026, 9)
        out = _annualize(labels, [2.0] * 9)
        self.assertEqual(len(out), 1)
        self.assertFalse(out[0]["complete"])
        self.assertEqual(out[0]["months"], 9)

    def test_eleven_months_is_not_complete(self):
        labels = months_of(2025, 11)
        out = _annualize(labels, [3.0] * 11)
        self.assertFalse(out[0]["complete"],
                         "11 months must not count as a complete year")

    def test_complete_years_filters_partial(self):
        yearly = [
            {"year": 2023, "value": 1.0, "months": 12, "complete": True},
            {"year": 2024, "value": 2.0, "months": 12, "complete": True},
            {"year": 2025, "value": 99.0, "months": 9, "complete": False},
        ]
        self.assertEqual(_complete_years(yearly), [1.0, 2.0])

    def test_partial_year_does_not_bend_the_trend(self):
        """A partial final year built from a different season must not move the slope."""
        # A clean +1.0/year series over 2005..2024 (complete years)
        labels, values = [], []
        for i, y in enumerate(range(2005, 2025)):
            labels += months_of(y, 12)
            values += [float(i)] * 12
        clean = _complete_years(_annualize(labels, values))

        # Now append a partial 2026 whose mean is wildly off (e.g. only winter months)
        labels2 = labels + months_of(2026, 9)
        values2 = values + [-50.0] * 9
        with_partial = _complete_years(_annualize(labels2, values2))

        self.assertEqual(clean, with_partial,
                         "partial year leaked into the trend input")

    def test_none_months_reduce_count(self):
        labels = months_of(2020, 12)
        values = [1.0] * 11 + [None]
        out = _annualize(labels, values)
        self.assertEqual(out[0]["months"], 11)
        self.assertFalse(out[0]["complete"])


class TestYearCaps(unittest.TestCase):
    def test_max_year_follows_calendar(self):
        self.assertEqual(server.MAX_YEAR, datetime.date.today().year)

    def test_min_months_is_twelve(self):
        self.assertEqual(MIN_MONTHS_PER_YEAR, 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
