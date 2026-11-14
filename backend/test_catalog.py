"""Catalog integrity tests.

Structural checks always run. The live-POWER check is opt-in because it hits
the network:  TERRATREND_NET=1 python -m unittest test_catalog
"""
import os
import re
import unittest

import catalog

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class TestVariableCatalog(unittest.TestCase):
    def setUp(self):
        self.vars = catalog.CATALOG

    def test_ids_unique(self):
        ids = [v["id"] for v in self.vars]
        self.assertEqual(len(ids), len(set(ids)), "duplicate variable id")

    def test_required_fields(self):
        for v in self.vars:
            for key in ("id", "name", "unit", "color", "mission", "desc", "group"):
                self.assertIn(key, v, f"{v.get('id')} missing {key}")
                self.assertTrue(str(v[key]).strip(), f"{v.get('id')} empty {key}")

    def test_colors_are_hex(self):
        for v in self.vars:
            self.assertRegex(v["color"], HEX, f"{v['id']} bad color {v['color']}")

    def test_variable_count(self):
        self.assertGreaterEqual(len(self.vars), 16)

    def test_groups_known(self):
        allowed = {"temperature", "water", "energy"}
        for v in self.vars:
            self.assertIn(v["group"], allowed, f"{v['id']} bad group")

    def test_brief_named_variables_present(self):
        """The challenge brief names evaporation and rainfall explicitly."""
        ids = {v["id"] for v in self.vars}
        self.assertIn("PRECTOTCORR", ids)   # rainfall
        self.assertIn("T2M", ids)           # temperature
        self.assertIn("EVPTRNS", ids)       # evaporation
        self.assertIn("GWETROOT", ids)      # soil moisture / drought


class TestRegionCatalog(unittest.TestCase):
    def setUp(self):
        self.regions = catalog.REGIONS

    def test_ids_unique(self):
        ids = [r["id"] for r in self.regions]
        self.assertEqual(len(ids), len(set(ids)), "duplicate region id")

    def test_bboxes_valid(self):
        for r in self.regions:
            bbox = r["bbox"]
            self.assertEqual(len(bbox), 4, f"{r['id']} bbox length")
            lon0, lat0, lon1, lat1 = bbox
            self.assertLess(lon0, lon1, f"{r['id']} lon order")
            self.assertLess(lat0, lat1, f"{r['id']} lat order")
            self.assertTrue(-180 <= lon0 <= 180 and -180 <= lon1 <= 180,
                            f"{r['id']} lon range")
            self.assertTrue(-90 <= lat0 <= 90 and -90 <= lat1 <= 90,
                            f"{r['id']} lat range")

    def test_surfaces(self):
        for r in self.regions:
            self.assertIn(r.get("surface", "land"), {"land", "ocean"},
                          f"{r['id']} bad surface")

    def test_has_ocean_regions(self):
        """The brief asks for land, ocean, and atmosphere."""
        oceans = [r for r in self.regions if r.get("surface") == "ocean"]
        self.assertGreaterEqual(len(oceans), 3,
                                "expected at least 3 ocean regions")


@unittest.skipUnless(os.environ.get("TERRATREND_NET") == "1",
                     "set TERRATREND_NET=1 to hit the live POWER API")
class TestLivePowerVariables(unittest.TestCase):
    """Every catalog variable must actually return a series."""

    def test_all_variables_return_data(self):
        import power_client
        for v in catalog.CATALOG:
            with self.subTest(var=v["id"]):
                series = power_client._fetch_one(0.0, 14.0, v["id"], 2015, 2020)
                valid = [k for k, val in series.items()
                         if power_client._clean(val) is not None]
                self.assertGreater(len(valid), 50,
                                   f"{v['id']} returned only {len(valid)} points")


if __name__ == "__main__":
    unittest.main(verbosity=2)
