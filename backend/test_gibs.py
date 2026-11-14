"""Tests for NASA GIBS & Worldview integration."""
import unittest
from gibs import (
    LAYERS,
    build_gibs_wms_url,
    build_worldview_url,
    get_optimal_date_slice,
    get_satellite_evidence,
)


class TestGibs(unittest.TestCase):
    def test_optimal_date_slice(self):
        # Known region mapping
        self.assertEqual(get_optimal_date_slice("sahel"), "09-15")
        self.assertEqual(get_optimal_date_slice("europe"), "08-05")
        self.assertEqual(get_optimal_date_slice("madagascar"), "09-15")

        # Unknown region: Northern vs Southern hemisphere fallback
        self.assertEqual(get_optimal_date_slice("unknown", lat=35.0), "08-15")
        self.assertEqual(get_optimal_date_slice("unknown", lat=-25.0), "02-15")

    def test_build_gibs_wms_url(self):
        bbox = [-2.0, 12.0, 2.0, 16.0]
        url = build_gibs_wms_url(bbox, "2020-09-15", "true_color", 600, 400)

        self.assertIn("gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi", url)
        self.assertIn("REQUEST=GetMap", url)
        self.assertIn("MODIS_Terra_CorrectedReflectance_TrueColor", url)
        self.assertIn("BBOX=-2.0000,12.0000,2.0000,16.0000", url)
        self.assertIn("TIME=2020-09-15", url)
        self.assertIn("SRS=EPSG:4326", url)

    def test_build_worldview_url(self):
        bbox = [6.0, 46.0, 12.0, 51.0]
        wv_url = build_worldview_url(bbox, "2023-08-05", "false_color")

        self.assertIn("worldview.earthdata.nasa.gov", wv_url)
        self.assertIn("v=6.0000,46.0000,12.0000,51.0000", wv_url)
        self.assertIn("t=2023-08-05", wv_url)
        self.assertIn("MODIS_Terra_CorrectedReflectance_Bands721", wv_url)

    def test_get_satellite_evidence_clamping(self):
        region = {
            "id": "sahel",
            "name": "Sahel Central",
            "bbox": [-2.0, 12.0, 2.0, 16.0],
        }
        # Start year 1990 should clamp to 2000 (MODIS start)
        ev = get_satellite_evidence(region, 1990, 2024, layer_key="true_color")

        self.assertEqual(ev["baseline"]["year"], 2000)
        self.assertEqual(ev["recent"]["year"], 2024)
        self.assertEqual(ev["baseline"]["date"], "2000-09-15")
        self.assertEqual(ev["recent"]["date"], "2024-09-15")
        self.assertIn("gibs.earthdata.nasa.gov", ev["baseline"]["image_url"])
        self.assertIn("worldview.earthdata.nasa.gov", ev["recent"]["worldview_url"])
        self.assertEqual(len(ev["available_layers"]), len(LAYERS))


if __name__ == "__main__":
    unittest.main()
