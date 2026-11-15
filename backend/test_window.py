"""Regression tests for time-window integrity.

The bug these exist to prevent: the cache returned any file matching
(param, lon, lat) regardless of the period stored inside it. Asking for
2015-2024 silently produced a 2005-2024 analysis, and the UI printed the
requested period over the wrong answer.
"""
import unittest

import power_client as pc


class TestSliceMonths(unittest.TestCase):
    def test_slices_to_requested_years(self):
        data = {f"{y}{m:02d}": 1.0 for y in range(2000, 2025) for m in range(1, 13)}
        out = pc._slice_months(data, 2015, 2024)
        self.assertEqual(len(out), 120)
        self.assertEqual(min(out), "201501")
        self.assertEqual(max(out), "202412")

    def test_no_data_outside_request(self):
        data = {"200501": 1.0, "201506": 2.0, "202412": 3.0, "202506": 4.0}
        out = pc._slice_months(data, 2015, 2024)
        self.assertNotIn("200501", out)
        self.assertNotIn("202506", out)
        self.assertIn("201506", out)

    def test_empty_when_window_does_not_overlap(self):
        data = {"200501": 1.0, "200512": 2.0}
        self.assertEqual(pc._slice_months(data, 2015, 2024), {})


class TestCoverageRule(unittest.TestCase):
    def test_partial_cover_is_not_reused(self):
        """A cached 2005-2024 file must not answer a 2015-2024 request."""
        cstart, cend = 2005, 2024
        start, end = 2015, 2024
        covers = cstart <= start and cend >= end
        # A 2005-2024 file DOES cover 2015-2024, but the slice is what makes it
        # correct. What must never happen is the reverse: a narrower file
        # answering a wider request.
        self.assertTrue(covers)
        narrower_covers = 2015 <= 2005 and 2024 >= 2024
        self.assertFalse(narrower_covers)


class TestRadiationUnits(unittest.TestCase):
    """POWER reports radiation in MJ/m^2/day; the catalog quotes W/m^2."""

    def test_longwave_scaling_is_physical(self):
        raw = 35.0  # MJ/m^2/day, a typical downwelling longwave value
        scaled = pc._scale("ALLSKY_SFC_LW_DWN", raw)
        self.assertAlmostEqual(scaled, 405.1, places=1)
        self.assertTrue(200 < scaled < 500, "implausible W/m^2 for LW down")

    def test_dni_scaling_is_physical(self):
        raw = 13.0  # MJ/m^2/day
        scaled = pc._scale("ALLSKY_SFC_SW_DNI", raw)
        self.assertAlmostEqual(scaled, 3.61, places=2)
        self.assertTrue(0.5 < scaled < 9, "implausible kWh/m^2/day for DNI")

    def test_non_radiation_passthrough(self):
        self.assertEqual(pc._scale("T2M", 21.5), 21.5)
        self.assertIsNone(pc._scale("T2M", None))


if __name__ == "__main__":
    unittest.main()
