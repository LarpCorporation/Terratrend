"""API contract tests: the server payload vs what the frontend reads.

Three bugs of the same shape have already shipped:
  * summary.rising      (frontend) vs summary.rising_cells (server)
  * summary.falling     (frontend) vs summary.falling_cells (server)
  * a field renamed during a merge, silently becoming undefined

These tests run fully offline (POWER / OpenAlex / GIBS are stubbed) and check
two directions:

  1. the server response contains every field the frontend dereferences
  2. the response has the structural shape the UI walks

Run:  python -m unittest test_contract -v
"""
import re
import unittest
from pathlib import Path

import server

APP_JS = Path(__file__).resolve().parent.parent / "frontend" / "app.js"

# Fields the frontend legitimately reads that the server does NOT have to
# provide: compatibility fallbacks and fields belonging to other objects that
# happen to share a variable name in the code.
COMPAT_FIELDS = {
    "sm": {"rising", "falling"},      # legacy aliases, deliberately optional
    "o": set(),
    "lit": set(),
    "d": set(),
}

# `o`, `d` and friends are also used as local variable names in the UI, so a
# naive regex picks up DOM properties. These are never payload fields.
DOM_IGNORE = {
    "textContent", "value", "style", "length", "innerHTML", "innerText",
    "appendChild", "classList", "dataset", "hidden", "disabled", "className",
    "addEventListener", "querySelector", "getContext", "createElement",
    "push", "map", "filter", "forEach", "slice", "join", "split", "replace",
    "toFixed", "find", "some", "every", "sort", "includes", "then", "catch",
}

# The literature panel was removed: OpenAlex/Crossref are non-NASA sources and
# the challenge rules restrict data to the NASA resources list.
STUB_PAPERS = {"ok": False, "papers": [], "error": "removed"}


def make_grid(param, bbox, start, end, nx=5, ny=5):
    """Synthetic monthly grid with a clean upward trend.

    The final year is deliberately incomplete (9 months), mirroring a year in
    progress, so the partial-year guard is exercised.
    """
    lon0, lat0, lon1, lat1 = bbox
    xs = [round(lon0 + (lon1 - lon0) * i / (nx - 1), 2) for i in range(nx)]
    ys = [round(lat0 + (lat1 - lat0) * j / (ny - 1), 2) for j in range(ny)]
    grid = {}
    for x in xs:
        grid[x] = {}
        for y in ys:
            series = {}
            for year in range(start, end + 1):
                last_month = 9 if year == end else 12
                for month in range(1, last_month + 1):
                    series[f"{year}{month:02d}"] = (
                        10.0 + 0.1 * (year - start) + 0.01 * month)
            grid[x][y] = series
    return grid


class _Stubs:
    """Context manager replacing the three network-facing collaborators."""

    def __enter__(self):
        self._saved = {
            "fetch_grid": server.power_client.fetch_grid,
            "satellite": server.gibs.get_satellite_evidence,
        }
        server.power_client.fetch_grid = make_grid
        server.gibs.get_satellite_evidence = lambda *a, **k: {
            "region_id": "stub", "layer": {"id": "x"}, "baseline": {},
            "recent": {}, "attribution": "stub",
        }
        return self

    def __exit__(self, *exc):
        server.power_client.fetch_grid = self._saved["fetch_grid"]
        server.gibs.get_satellite_evidence = self._saved["satellite"]
        return False


def analysed_payload():
    with _Stubs():
        return server.run_analysis(
            ["T2M", "PRECTOTCORR"], "ghana_north", 2005, 2026)


def frontend_field_reads(prefix):
    """`sm.foo` style reads of a given object in app.js."""
    if not APP_JS.exists():
        return set()
    src = APP_JS.read_text(encoding="utf-8")
    return set(re.findall(rf"\b{prefix}\.([A-Za-z_][A-Za-z0-9_]*)", src))


class TestTopLevelContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = analysed_payload()

    def test_top_level_keys(self):
        for key in ("region", "start", "end", "months", "series", "grid",
                    "window", "satellite", "sources"):
            self.assertIn(key, self.d, f"missing top-level key: {key}")

    def test_window_shape(self):
        w = self.d["window"]
        for key in ("first_month", "last_month", "partial_years"):
            self.assertIn(key, w, f"missing window.{key}")
        self.assertIsInstance(w["partial_years"], list)

    def test_each_series_block(self):
        self.assertEqual(len(self.d["series"]), 2)
        for s in self.d["series"]:
            for key in ("variable", "overall", "cells", "summary",
                        "yearly_timeseries", "monthly_timeseries",
                        "seasonal"):
                self.assertIn(key, s, f"series missing {key}")
            self.assertIn("id", s["variable"])
            self.assertIn("unit", s["variable"])

    def test_monthly_timeseries_shape(self):
        """The chart's monthly mode iterates these objects."""
        first = self.d["series"][0]["monthly_timeseries"]
        self.assertTrue(first, "monthly_timeseries is empty")
        for point in first[:3]:
            self.assertIn("month", point)
            self.assertIn("value", point)


class TestFrontendAgainstServer(unittest.TestCase):
    """Every `sm.x`, `o.x`, `lit.x` the UI reads must exist in the payload."""

    @classmethod
    def setUpClass(cls):
        cls.d = analysed_payload()
        cls.block = cls.d["series"][0]

    def _check(self, prefix, attr, server_obj):
        used = frontend_field_reads(prefix) - DOM_IGNORE
        if not used:
            self.skipTest(f"no {prefix}. reads found in app.js")
        missing = sorted(used - set(server_obj) - COMPAT_FIELDS.get(prefix, set()))
        self.assertFalse(
            missing,
            f"frontend reads {prefix}.{missing} but the server payload's "
            f"{attr} has {sorted(server_obj)}",
        )

    def test_summary_fields(self):
        self._check("sm", "summary", self.block["summary"])

    def test_overall_fields(self):
        self._check("o", "overall", self.block["overall"])

    def test_data_object_fields(self):
        used = frontend_field_reads("d")
        # `d` is also a local variable name in a few helpers; only enforce the
        # names that look like payload keys.
        payload_keys = set(self.d) | {"region", "series", "window"}
        relevant = used & payload_keys
        self.assertTrue(relevant, "expected the UI to read payload keys")


class TestSeriesFieldReferences(unittest.TestCase):
    """Series-level fields named in app.js must exist in the series payload.

    This is the check that would have caught `s.region_timeseries` (the server
    renamed it `monthly_timeseries`), which silently broke the YEAR/MONTH
    toggle, the observatory monthly view and CSV export.
    """

    SERIES_FIELDS = [
        "variable", "overall", "cells", "summary", "yearly_timeseries",
        "monthly_timeseries", "region_timeseries", "seasonal",
    ]

    def test_referenced_series_fields_exist(self):
        if not APP_JS.exists():
            self.skipTest("app.js not found")
        src = APP_JS.read_text(encoding="utf-8")
        block = analysed_payload()["series"][0]
        for field in self.SERIES_FIELDS:
            if f".{field}" not in src:
                continue
            self.assertIn(
                field, block,
                f"app.js references .{field} but the series block only has "
                f"{sorted(block)}",
            )


class TestCellSummaryConsistency(unittest.TestCase):
    """The counts must agree with each other and with the cell list."""

    @classmethod
    def setUpClass(cls):
        cls.block = analysed_payload()["series"][0]

    def test_counts_match_cells(self):
        sm = self.block["summary"]
        cells = self.block["cells"]
        self.assertEqual(sm["total_cells"], len(cells))
        self.assertEqual(
            sm["significant_cells"],
            sm.get("rising_cells", 0) + sm.get("falling_cells", 0),
            "significant_cells must equal rising + falling",
        )

    def test_valid_plus_nodata_equals_total(self):
        sm = self.block["summary"]
        nodata = sum(1 for c in self.block["cells"]
                     if c.get("direction") == "nodata")
        self.assertEqual(sm["valid_cells"] + nodata, sm["total_cells"])

    def test_no_trend_never_negative(self):
        sm = self.block["summary"]
        self.assertGreaterEqual(sm["valid_cells"] - sm["significant_cells"], 0)


class TestAnalysisFieldsPresent(unittest.TestCase):
    """Fields the UI formats directly — a missing one renders 'NaN' or blank."""

    @classmethod
    def setUpClass(cls):
        cls.o = analysed_payload()["series"][0]["overall"]

    def test_core_stats(self):
        for key in ("ok", "n", "slope", "p", "z", "tau", "significant",
                    "direction", "per_decade", "stars"):
            self.assertIn(key, self.o, f"overall missing {key}")

    def test_confidence_interval(self):
        for key in ("ci_low_per_decade", "ci_high_per_decade"):
            self.assertIn(key, self.o, f"overall missing {key}")
            self.assertIsNotNone(self.o[key])

    def test_t_test_block(self):
        for key in ("t_p", "t_df", "t_per_decade", "t_significant",
                    "methods_agree"):
            self.assertIn(key, self.o, f"overall missing {key}")

    def test_seasonal_mk_reaches_the_ui(self):
        """The observatory modal reads o.seasonal_*; they must exist."""
        for key in ("seasonal_z", "seasonal_p", "seasonal_significant"):
            self.assertIn(key, self.o, f"overall missing {key}")
            self.assertIsNotNone(self.o[key], f"overall {key} is None")

    def test_partial_year_excluded(self):
        """2026 is incomplete in the stub, so it must not enter the trend."""
        series = analysed_payload()["series"][0]
        yearly = series["yearly_timeseries"]
        total_years = len(yearly)
        complete = [y for y in yearly if y.get("complete", True)]
        self.assertEqual(series["overall"]["n"], len(complete))
        self.assertLess(series["overall"]["n"], total_years,
                        "stub ends mid-year; n must exclude the partial year")


if __name__ == "__main__":
    unittest.main(verbosity=2)
