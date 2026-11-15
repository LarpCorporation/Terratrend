"""Replacement requirements: a catalogue match is not accuracy validation."""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import nasa_data


EVIDENCE = Path(__file__).resolve().parents[1] / "docs/local-handoff/giovanni-2026-11-15"


def observed():
    configured = json.loads((EVIDENCE / "configured-variables.json").read_text())
    capabilities = {product: json.loads((EVIDENCE / f"capabilities-{product}.json").read_text())
                    for product in nasa_data.PRODUCTS}
    return configured, capabilities


def prospective():
    """Hypothetical complete service, explicitly not an observed NASA result."""
    configured, capabilities = observed()
    configured["configured_variables"] = [f"{product}_5_12_4_{field}"
                                          for product, field, *_ in nasa_data.FIELDS.values()]
    for cap in capabilities.values():
        cap["services"] = [{"name": "giovanni-averaging-service", "capabilities": {
            "averaging": {"area": True},
            "subsetting": {"shape": True, "bbox": True, "temporal": True, "variable": True},
            "outputFormats": [{"mimeType": "text/csv"}],
        }}]
    return configured, capabilities


class TestGiovanniCompatibility(unittest.TestCase):
    def test_observed_cloud_catalogue_cannot_replace_our_eight_monthly_fields(self):
        from giovanni_capabilities import assess
        result = assess(*observed())
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(set(result["missing_fields"]), set(nasa_data.FIELDS))
        self.assertFalse(result["replacement_verified"])
        self.assertFalse(result["ready_to_validate"])
        self.assertEqual(len(result["collections"]), 3)

    def test_higher_frequency_same_named_fields_are_not_silently_substituted(self):
        from giovanni_capabilities import assess
        configured, capabilities = prospective()
        configured["configured_variables"] = [v.replace("M2TM", "M2T1")
                                              for v in configured["configured_variables"]]
        result = assess(configured, capabilities)
        self.assertEqual(len(result["missing_fields"]), 8)
        self.assertFalse(result["ready_to_validate"])

    def test_shape_subsetting_and_averaging_in_different_services_do_not_establish_polygon_averaging(self):
        from giovanni_capabilities import assess
        configured, capabilities = prospective()
        for cap in capabilities.values():
            averaging = cap["services"][0]
            averaging["capabilities"]["subsetting"]["shape"] = False
            cap["services"].append({"name": "sds/HOSS-geographic", "capabilities": {
                "subsetting": {"shape": True}, "averaging": {"area": False}}})
            cap["summary"]["subsetting"]["shape"] = True
            cap["summary"]["averaging"]["area"] = True
        result = assess(configured, capabilities)
        self.assertEqual(result["status"], "unsupported")
        self.assertTrue(all(row["area_averaging"] for row in result["collections"]))
        self.assertTrue(all(not row["exact_shape_request"] for row in result["collections"]))

    def test_even_full_capabilities_require_scientific_validation_before_replacement(self):
        from giovanni_capabilities import assess
        result = assess(*prospective())
        self.assertEqual(result["status"], "validation_required")
        self.assertTrue(result["ready_to_validate"])
        self.assertFalse(result["replacement_verified"])
        self.assertEqual(result["missing_fields"], [])

    def test_csv_temporal_and_variable_support_are_required_together(self):
        from giovanni_capabilities import assess
        for kind in ("csv", "temporal", "variable"):
            with self.subTest(kind=kind):
                configured, capabilities = prospective()
                service = capabilities["M2TMNXSLV"]["services"][0]["capabilities"]
                if kind == "csv": service["outputFormats"] = [{"mimeType": "image/tiff"}]
                else: service["subsetting"][kind] = False
                self.assertFalse(assess(configured, capabilities)["ready_to_validate"])

    def test_malformed_or_wrong_collection_metadata_is_not_treated_as_missing_data(self):
        from giovanni_capabilities import assess
        configured, capabilities = prospective()
        cases = [(None, capabilities), ({"configured_variables": "not a list"}, capabilities),
                 (configured, {}), (configured, {**capabilities, "M2TMNXSLV": {}})]
        wrong = copy.deepcopy(capabilities)
        wrong["M2TMNXSLV"]["conceptId"] = "C999999-OTHER"
        cases.append((configured, wrong))
        for config, caps in cases:
            with self.subTest(config=config is None, collections=len(caps)):
                with self.assertRaises(ValueError): assess(config, caps)

    def test_probe_reads_only_four_public_metadata_endpoints(self):
        from giovanni_capabilities import probe, CATALOG_URL, capabilities_url
        configured, capabilities = observed()
        replies = {CATALOG_URL: configured, **{capabilities_url(p): v for p, v in capabilities.items()}}
        calls = []
        def fetch(url):
            calls.append(url)
            return replies[url]
        result = probe(fetch)
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(set(calls), set(replies))
        self.assertIn("checked_utc", result)

    def test_failed_probe_is_unavailable_rather_than_a_scientific_verdict(self):
        from giovanni_capabilities import probe
        def fail(_): raise ValueError("offline")
        result = probe(fail)
        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(result["replacement_verified"])

    def test_metadata_transport_never_sends_earthdata_credentials_or_follows_redirects(self):
        from giovanni_capabilities import get_json, CATALOG_URL
        from test_nasa_data import Session, Response
        session = Session(Response(body=b'{"configured_variables":[]}'))
        with patch("giovanni_capabilities.requests.Session", return_value=session):
            self.assertEqual(get_json(CATALOG_URL), {"configured_variables": []})
        url, options = session.calls[0]
        self.assertNotIn("Authorization", options["headers"])
        self.assertFalse(options["allow_redirects"])
        self.assertEqual(url, CATALOG_URL)
        self.assertTrue(callable(session.auth))

    def test_metadata_transport_rejects_redirects_invalid_json_oversize_and_other_hosts(self):
        from giovanni_capabilities import get_json, CATALOG_URL
        from test_nasa_data import Session, Response
        responses = [Response(302), Response(503), Response(body=b'not JSON'),
                     Response(body=b'x' * 1_000_001)]
        for response in responses:
            with self.subTest(code=response.status_code, size=len(response.body)):
                with patch("giovanni_capabilities.requests.Session", return_value=Session(response)):
                    with self.assertRaises(ValueError): get_json(CATALOG_URL)
        with patch("giovanni_capabilities.requests.Session") as session:
            with self.assertRaises(ValueError): get_json("https://example.com/")
            session.assert_not_called()
