"""The curated event network must report what data supports, never more.

The catalogue's own numbers are editorial. These tests pin the two properties
that keep it honest: a real relationship is recovered from supplied series, and
a slot with no source stays explicitly unavailable instead of being filled in.
"""
import math
import random
import unittest

import event_network


def synthetic(months, lag=3, seed=7, noise=0.25):
    """A quasi-periodic signal, optionally lagged.

    Three incommensurate periods, so no half-cycle shift ties with the planted
    lag the way a pure sinusoid would. Every component is a multiple of one
    month and none is 12, so the seasonal decomposition has nothing to absorb.
    """
    rnd = random.Random(seed)
    base = [math.sin(2 * math.pi * i / 48.0)
            + 0.6 * math.sin(2 * math.pi * i / 29.0 + 1.0)
            + 0.4 * math.sin(2 * math.pi * i / 17.0 + 2.0) for i in range(months)]
    x = [v + rnd.uniform(-noise, noise) for v in base]
    y = [(base[i - lag] if i - lag >= 0 else 0.0) + rnd.uniform(-noise, noise)
         for i in range(months)]
    return x, y


class TestIndex(unittest.TestCase):
    def setUp(self):
        self.data = event_network.index()

    def test_every_catalogue_event_is_listed(self):
        self.assertEqual(len(self.data["events"]), 6)
        ids = {e["id"] for e in self.data["events"]}
        self.assertIn("el_nino_2023_2024", ids)
        self.assertIn("west_africa_ghana_1982_83", ids)
        self.assertIn("developing_el_nino_2026_2027", ids)

    def test_watch_event_is_not_presented_as_verified_history(self):
        watch = next(e for e in self.data["events"]
                     if e["id"] == "developing_el_nino_2026_2027")
        self.assertEqual(watch["status"], "ongoing_developing")
        self.assertEqual(self.data["events"][-1]["status"], "ongoing_developing")

    def test_disclaimers_travel_with_the_catalogue(self):
        self.assertIn("NOT literal wind trajectories", self.data["disclaimer"])
        self.assertIn("not standalone proof of physical causation",
                      self.data["statistical_disclaimer"])

    def test_untraceable_slot_is_declared_not_hidden(self):
        arctic = next(e for e in self.data["events"]
                      if e["id"] == "arctic_sea_ice_minimum_2012")
        self.assertIn("arctic_ice_extent", arctic["traceability"]["slots_awaiting_source"])

    def test_story_events_report_no_awaiting_slots(self):
        for event_id in ("el_nino_2023_2024", "amazon_drought_2023",
                         "southern_africa_drought_2023_2024"):
            event = next(e for e in self.data["events"] if e["id"] == event_id)
            self.assertEqual(event["traceability"]["slots_awaiting_source"], [],
                             f"{event_id} should be fully sourceable")


class TestBuild(unittest.TestCase):
    """The fake source answers on an absolute timeline anchored at 1982.

    A slot's requested window only selects a slice of that timeline, exactly
    like the real adapters, where the Pacific record begins in 1982 and the
    land chains in 2001. That is what makes an index-alignment bug visible.
    """

    def provider(self, lag=3, noise=0.25, sign=1.0):
        rnd = random.Random(7)
        cache = {}

        def wobble(i):
            if i not in cache:
                cache[i] = rnd.uniform(-noise, noise)
            return cache[i]

        def driver(i):
            return (math.sin(2 * math.pi * i / 48.0)
                    + 0.6 * math.sin(2 * math.pi * i / 29.0 + 1.0)
                    + 0.4 * math.sin(2 * math.pi * i / 17.0 + 2.0)
                    + wobble(i))

        def response(i):
            j = i - lag
            if j < 0:
                return 0.0
            return sign * (math.sin(2 * math.pi * j / 48.0)
                           + 0.6 * math.sin(2 * math.pi * j / 29.0 + 1.0)
                           + 0.4 * math.sin(2 * math.pi * j / 17.0 + 2.0))

        calls = []

        def source(region, variable, start, end):
            calls.append((region, variable, start, end))
            lo = (start - 1982) * 12
            hi = lo + (end - start + 1) * 12
            if variable in ("PRECTOTCORR", "GWETTOP", "GWETROOT", "NDVI"):
                return [response(i) for i in range(lo, hi)]
            return [driver(i) for i in range(lo, hi)]
        source.calls = calls
        return source

    def test_recovers_the_planted_lead(self):
        out = event_network.build("el_nino_2023_2024", 2026, self.provider(lag=3))
        edge = next(e for e in out["edges"] if e["id"] == "edge_elnino23_amazon")
        v = edge["verification"]
        self.assertEqual(v["status"], "verified_from_source")
        self.assertEqual(v["lag_months_observed"], 3)
        self.assertGreater(v["r_value"], 0.8)
        self.assertLess(v["p_value_neff"], 0.01)

    def test_differing_slot_windows_are_aligned_by_date_not_by_index(self):
        # Pacific starts 1982, Amazon rainfall 2001. Pairing the raw arrays
        # index-by-index compares 1982 weather with 2001 weather and destroys
        # the relationship the shipped catalogue is built on.
        out = event_network.build("el_nino_2023_2024", 2026, self.provider(lag=2))
        edge = next(e for e in out["edges"] if e["id"] == "edge_elnino23_amazon")
        v = edge["verification"]
        self.assertEqual(v["status"], "verified_from_source")
        self.assertEqual(v["lag_months_observed"], 2)
        self.assertGreater(v["r_value"], 0.8)
        # The window must be the overlap, not either slot's own range.
        self.assertEqual(v["analysis_window"], [2001, 2026])
        # The winning lag trims that many paired months off the sample.
        self.assertGreaterEqual(v["sample_months"], 300)

    def test_lag_search_stays_inside_a_season(self):
        # A +/-24 month search over a 1-3 month mechanism inflates the
        # correction family and returns spurious far-lag peaks.
        self.assertLessEqual(event_network.EVENT_MAX_LAG, 6)

    def test_inverse_pathway_keeps_its_negative_sign(self):
        # A drying pathway must read negative. impact_pair exposes the signed
        # correlation as "r" and its magnitude as "r_lagged"; reporting the
        # magnitude silently turns every inverse pathway into a direct one.
        out = event_network.build("el_nino_2023_2024", 2026,
                                  self.provider(lag=2, sign=-1.0))
        edge = next(e for e in out["edges"] if e["id"] == "edge_elnino23_amazon")
        v = edge["verification"]
        self.assertEqual(v["status"], "verified_from_source")
        self.assertLess(v["r_value"], -0.8)
        self.assertGreater(v["r_magnitude"], 0.8)

    def test_reports_the_fdr_family_it_was_selected_from(self):
        out = event_network.build("el_nino_2023_2024", 2026, self.provider())
        verified = [e for e in out["edges"]
                    if e["verification"].get("status") == "verified_from_source"]
        self.assertGreaterEqual(len(verified), 2)
        for edge in verified:
            v = edge["verification"]
            self.assertIn("p_value_fdr", v)
            self.assertGreaterEqual(v["p_value_fdr"], v["p_value_neff"])
            self.assertIn("survives_fdr", v)
            self.assertEqual(v["family_size"],
                             len([e for e in out["edges"]
                                  if "p_value_neff" in e["verification"]]))

    def test_a_lag_family_correction_is_already_applied(self):
        # cross_corr_best multiplies by (2*max_lag+1); the event layer must not
        # undo that by reporting a raw per-lag p-value.
        out = event_network.build("el_nino_2023_2024", 2026, self.provider())
        edge = next(e for e in out["edges"] if e["id"] == "edge_elnino23_amazon")
        self.assertLess(edge["verification"]["p_value_neff"], 0.05)

    def test_arctic_ice_stays_awaiting_source(self):
        out = event_network.build("arctic_sea_ice_minimum_2012", 2026, self.provider())
        edge = next(e for e in out["edges"] if e["id"] == "edge_arctic_albedo_feedback")
        self.assertEqual(edge["verification"]["status"], "awaiting_source")
        self.assertIn("NSIDC", edge["verification"]["reason"])
        self.assertNotIn("r_value", edge["verification"])

    def test_unreachable_source_is_unavailable_not_a_number(self):
        def broken(region, variable, start, end):
            raise RuntimeError("Connect Earthdata to read NASA observations")
        out = event_network.build("amazon_drought_2023", 2026, broken)
        for edge in out["edges"]:
            v = edge["verification"]
            self.assertEqual(v["status"], "unavailable")
            self.assertNotIn("r_value", v)
            self.assertIn("Earthdata", v["reason"])

    def test_identical_windows_are_fetched_once(self):
        source = self.provider()
        event_network.build("el_nino_2023_2024", 2026, source)
        keys = [(r, v, s) for r, v, s, _ in source.calls]
        # nino34_sst is the driver of three edges in this event.
        self.assertEqual(len(keys), len(set(keys)))

    def test_proxy_provenance_is_carried_with_the_numbers(self):
        out = event_network.build("el_nino_2023_2024", 2026, self.provider())
        edge = next(e for e in out["edges"] if e["id"] == "edge_elnino23_amazon")
        x = edge["verification"]["x"]
        self.assertEqual(x["source"], "NASA MERRA-2 / M2TMNXSLV / TS")
        self.assertEqual(x["proxy_for"], "NOAA ERSSTv5 Niño 3.4")
        self.assertIn("not the ERSSTv5", x["proxy_note"])

    def test_unknown_event_is_rejected(self):
        with self.assertRaises(KeyError):
            event_network.build("not_an_event", 2026, self.provider())


class TestSlotCoverage(unittest.TestCase):
    def test_every_edge_slot_is_declared(self):
        data = event_network.load_catalogue()
        for edge in data["edges"]:
            sv = edge["inspector"]["q3_what_evidence_supports_it"]["statistical_verification"]
            for key in ("x_slot", "y_slot"):
                slot = sv.get(key)
                self.assertIn(slot, event_network.SLOT_SOURCES,
                              f"{edge['id']} references undeclared slot {slot}")

    def test_every_event_variable_slot_is_declared(self):
        data = event_network.load_catalogue()
        for event in data["events"]:
            for kv in event.get("key_variables", []):
                self.assertIn(kv["data_slot"], event_network.SLOT_SOURCES,
                              f"{event['id']} lists undeclared slot {kv['data_slot']}")


if __name__ == "__main__":
    unittest.main()
