"""Tests for durable local persistence of completed analyses.

These lock in the behaviour the saved-trend-map depends on: one row per
scientific identity, honest versioning and damage labels, credential-free
payloads, and a map index that never invents a subregion value from a national
number.  Everything runs on a throw-away SQLite file, never the real cache.
"""
import json
import io
import os
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

import result_store
import server

CURRENT = result_store.CURRENT_METHOD_VERSION
GHANA = {"id": "country:gha", "name": "Ghana", "level": "country",
         "bbox": [-3.26, 4.71, 1.2, 11.17], "geometry_version": "35339921e7a23101",
         "surface": "land"}
KENYA = {"id": "country:ken", "name": "Kenya", "level": "country",
         "bbox": [33.89, -4.68, 41.86, 5.51], "geometry_version": "aabbccddeeff0011",
         "surface": "land"}
SQUARE = {"type": "Polygon",
          "coordinates": [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]]}
WIDER_SQUARE = {"type": "Polygon",
                "coordinates": [[[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0], [0.0, 0.0]]]}


@pytest.fixture()
def store(tmp_path, monkeypatch):
    path = tmp_path / "results.sqlite3"
    monkeypatch.setattr(result_store, "_db_path", lambda: str(path))
    return path


def make_spec(**overrides):
    spec = {"operation": "analyze", "variables": ["T2M"],
            "region": "country:gha", "start": 2016, "end": 2024,
            "provider": "auto", "method_version": CURRENT}
    spec.update(overrides)
    return spec


def make_block(variable="T2M", name="Air Temperature", unit="\u00b0C",
               per_decade=0.2, ok=True, reason=None, provider="nasa-merra2",
               aggregation="MERRA-2 monthly area mean"):
    overall = ({"ok": True, "per_decade": per_decade, "direction": "rising",
                "significant": True, "p": 0.01, "n": 9}
               if ok else {"ok": False, "reason": reason or "insufficient data (<8 points)"})
    return {
        "variable": {"id": variable, "name": name, "unit": unit},
        "overall": overall,
        "provenance": {"provider": provider, "source": "NASA MERRA-2",
                       "aggregation": aggregation},
        "yearly_timeseries": [{"year": 2016 + i, "complete": True} for i in range(9)],
    }


def make_result(blocks=None, region=None, start=2016, end=2024, compare=None):
    blocks = [make_block()] if blocks is None else blocks
    region = dict(GHANA if region is None else region)
    months = ["%d-%02d" % (start + i // 12, i % 12 + 1)
              for i in range((end - start + 1) * 12)]
    out = {
        "region": region, "start": start, "end": end, "months": months,
        "series": blocks,
        "grid": {"nx": 5, "ny": 5, "bbox": region.get("bbox")},
        "window": {"first_month": months[0], "last_month": months[-1],
                   "partial_years": []},
        "sources": ["NASA MERRA-2"],
        "provenance": [dict(block["provenance"]) for block in blocks],
    }
    if compare is not None:
        out["compare"] = compare
    return out


def make_compare(blocks=None, region=None):
    return {"region": dict(KENYA if region is None else region),
            "series": [make_block(per_decade=-0.3)] if blocks is None else blocks,
            "contrasts": []}


# --------------------------------------------------------------------------
# canonical identity and dedupe
# --------------------------------------------------------------------------
def test_canonical_key_ignores_display_names_and_transient_ids():
    spec = make_spec()
    result = make_result()
    baseline = result_store.canonical_key(spec, result)
    renamed = make_result(region={"id": "country:gha", "name": "Republic of Ghana",
                                  "level": "country", "bbox": GHANA["bbox"],
                                  "geometry_version": GHANA["geometry_version"]})
    renamed["job_id"] = "transient-job-123"
    renamed["started_at"] = "2026-11-15T13:19:46Z"
    renamed_spec = dict(spec, job_id="transient-job-123")
    assert result_store.canonical_key(spec, result) == baseline
    assert result_store.canonical_key(renamed_spec, renamed) == baseline


def test_saving_the_same_request_twice_keeps_one_row(store):
    spec = make_spec()
    first = result_store.save(spec, make_result())
    second = result_store.save(spec, make_result())
    assert first["ok"] is True and first["created"] is True
    assert second["ok"] is True and second["created"] is False
    assert second["updated"] is True
    assert first["id"] == second["id"]
    listing = result_store.list_results()
    assert listing["total"] == 1
    assert [row["id"] for row in listing["results"]] == [first["id"]]


def test_different_window_measurement_geometry_and_method_are_distinct_rows(store):
    base = make_spec()
    result_store.save(base, make_result())

    other_window = make_spec(start=2005, end=2014)
    result_store.save(other_window, make_result(start=2005, end=2014))

    ndvi_spec = make_spec(variables=["NDVI"])
    ndvi_result = make_result(blocks=[make_block("NDVI", "Vegetation Greenness (NDVI)",
                                                 "index", 0.05)])
    result_store.save(ndvi_spec, ndvi_result)

    for label, geometry in (("a", SQUARE), ("b", WIDER_SQUARE)):
        custom = {"id": "custom:test", "name": "Drawn area", "level": "custom",
                  "geometry": geometry, "bbox": [0.0, 0.0, 1.0, 1.0]}
        custom_spec = make_spec(region="custom:test", custom_areas=[custom])
        custom_result = make_result(region={"id": "custom:test", "name": "Drawn area",
                                            "level": "custom", "bbox": [0, 0, 1, 1]})
        result_store.save(custom_spec, custom_result)

    legacy_spec = make_spec(method_version="polygon-sen-calendar-fdr-v1")
    result_store.save(legacy_spec, make_result())

    keys = [row["key"] for row in result_store.list_results()["results"]]
    assert len(keys) == 6
    assert len(set(keys)) == 6


# --------------------------------------------------------------------------
# versioning and damage
# --------------------------------------------------------------------------
def test_old_method_version_is_listed_as_legacy_and_never_a_current_map_cell(store):
    legacy_spec = make_spec(method_version="polygon-sen-calendar-fdr-v1")
    saved = result_store.save(legacy_spec, make_result())
    assert saved["status"] == "legacy"

    listing = result_store.list_results()
    assert listing["total"] == 1
    row = listing["results"][0]
    assert row["status"] == "legacy"
    assert "v1" in row["stale_reason"] and CURRENT in row["stale_reason"]

    record = result_store.get_result(saved["id"])
    assert record["status"] == "legacy"
    assert record["payload"]["series"][0]["overall"]["ok"] is True

    index = result_store.map_index(variable="T2M", start=2016, end=2024)
    assert index["cells"] == []
    assert index["exact"] is False
    assert [item["result_id"] for item in index["alternatives"]] == [saved["id"]]
    assert index["alternatives"][0]["status"] == "legacy"


def test_damaged_payload_is_labelled_listed_and_excluded_from_the_map(store):
    saved = result_store.save(make_spec(), make_result())
    connection = sqlite3.connect(str(store))
    connection.execute("UPDATE results SET payload=? WHERE id=?", ("{not json", saved["id"]))
    connection.commit()
    connection.close()

    listing = result_store.list_results()
    assert listing["total"] == 1
    row = listing["results"][0]
    assert row["status"] == "damaged"
    assert row["damaged"] is True
    assert "payload" in row["reason"]

    record = result_store.get_result(saved["id"])
    assert record["status"] == "damaged"
    assert record["payload"] is None

    index = result_store.map_index(variable="T2M", start=2016, end=2024)
    assert index["cells"] == [] and index["exact"] is False

    # the audit trail survives: the row is still listed after the damage mark
    assert result_store.list_results()["total"] == 1
    assert result_store.storage_stats()["count"] == 1


def test_corrupt_or_unwritable_database_returns_an_error_marker(tmp_path, monkeypatch):
    corrupt = tmp_path / "corrupt.sqlite3"
    corrupt.write_bytes(b"this is not a sqlite database at all")
    monkeypatch.setattr(result_store, "_db_path", lambda: str(corrupt))
    marker = result_store.save(make_spec(), make_result())
    assert marker["ok"] is False and marker["saved"] is False
    assert "id" in marker and marker["id"] is None
    assert marker["error"]

    directory = tmp_path / "is-a-directory.sqlite3"
    directory.mkdir()
    monkeypatch.setattr(result_store, "_db_path", lambda: str(directory))
    marker = result_store.save(make_spec(), make_result())
    assert marker["ok"] is False and marker["error"]

    # reads and stats degrade instead of raising too
    assert result_store.list_results()["total"] == 0
    assert result_store.get_result("whatever") is None
    assert result_store.delete_result("whatever") is False
    assert "error" in result_store.storage_stats()


# --------------------------------------------------------------------------
# credentials
# --------------------------------------------------------------------------
def test_credentials_are_stripped_before_disk_and_before_return(store):
    result = make_result()
    result["token"] = "supersecret-token-value"
    result["api_key"] = "ABC123SECRET"
    result["password"] = "hunter2"
    result["request"] = {"headers": {"Authorization": "Bearer abcdefghijklmnop"},
                         "note": "Bearer abcdefghijklmnop",
                         "apiKey": "nested-secret"}
    result["provenance"][0]["access"] = "Bearer topsecretEARTHDATA123"
    result["provenance"][0]["cookie"] = "session=abc"
    saved = result_store.save(make_spec(), result)
    assert saved["ok"] is True

    record = result_store.get_result(saved["id"])
    payload = record["payload"]
    for forbidden in ("token", "api_key", "password", "apiKey", "Authorization", "cookie"):
        assert forbidden not in payload
    assert "Bearer" not in json.dumps(payload)
    assert "hunter2" not in json.dumps(payload)
    assert "Bearer" not in json.dumps(record["provenance"])

    raw = sqlite3.connect(str(store)).execute(
        "SELECT payload, provenance FROM results").fetchone()
    assert "hunter2" not in raw[0]
    assert "supersecret-token-value" not in raw[0]
    assert "Bearer" not in raw[1]


def test_sanitize_handles_nested_containers():
    value = {"ok": 1, "token": "x", "nested": [{"Authorization": "y", "keep": 2},
                                                "Bearer abcdefghijkl"],
             "headers": {"note": "Bearer zzzzzzzzzzzz", "fine": "text"}}
    clean = result_store.sanitize(value)
    assert clean["ok"] == 1
    assert "token" not in clean
    assert clean["nested"] == [{"keep": 2}]
    assert "note" not in clean["headers"]
    assert clean["headers"]["fine"] == "text"


# --------------------------------------------------------------------------
# map index
# --------------------------------------------------------------------------
def test_comparison_produces_two_independent_area_cells(store):
    spec = make_spec(compare_region="country:ken")
    result = make_result(compare=make_compare())
    saved = result_store.save(spec, result)
    assert saved["kind"] == "compare"

    index = result_store.map_index(variable="T2M", start=2016, end=2024)
    assert index["exact"] is True
    assert len(index["cells"]) == 2
    cells = {cell["area_id"]: cell for cell in index["cells"]}
    assert set(cells) == {"country:gha", "country:ken"}
    assert cells["country:gha"]["verdict"]["per_decade"] == 0.2
    assert cells["country:ken"]["verdict"]["per_decade"] == -0.3
    both = {cell["result_id"] for cell in index["cells"]}
    assert both == {saved["id"]}


def test_national_result_never_colours_a_subregion(store):
    region = dict(GHANA)
    region["children"] = ["region:gha:ashanti", "region:gha:volta"]
    saved = result_store.save(make_spec(), make_result(region=region))

    index = result_store.map_index(variable="T2M", start=2016, end=2024)
    assert [cell["area_id"] for cell in index["cells"]] == ["country:gha"]
    assert all(not cell["area_id"].startswith("region:") for cell in index["cells"])

    # asking for regional cells must not relabel the national aggregate
    subregional = result_store.map_index(variable="T2M", start=2016, end=2024,
                                         level="region")
    assert subregional["cells"] == []
    assert subregional["exact"] is False
    assert saved["areas"][0]["id"] == "country:gha"


def test_a_different_saved_window_is_offered_as_an_alternative(store):
    old = result_store.save(make_spec(start=2005, end=2024),
                            make_result(start=2005, end=2024))
    index = result_store.map_index(variable="T2M", start=2016, end=2024)
    assert index["cells"] == []
    assert index["exact"] is False
    assert [item["result_id"] for item in index["alternatives"]] == [old["id"]]
    assert index["alternatives"][0]["window"]["start"] == 2005
    assert index["window"] == {"start": 2016, "end": 2024}


def test_insufficient_data_is_a_cell_and_not_a_missing_area(store):
    block = make_block(ok=False, reason="insufficient data (<8 points)")
    result_store.save(make_spec(), make_result(blocks=[block]))
    index = result_store.map_index(variable="T2M", start=2016, end=2024)
    assert len(index["cells"]) == 1
    verdict = index["cells"][0]["verdict"]
    assert verdict["ok"] is False
    assert verdict["reason"] == "insufficient data (<8 points)"
    assert verdict["per_decade"] is None
    assert index["cells"][0]["area_id"] == "country:gha"


def test_level_filter_and_variable_filter(store):
    result_store.save(make_spec(), make_result())
    ndvi_spec = make_spec(variables=["NDVI"])
    result_store.save(ndvi_spec, make_result(
        blocks=[make_block("NDVI", "Vegetation Greenness (NDVI)", "index", 0.05)]))

    temperature = result_store.map_index(variable="T2M", start=2016, end=2024)
    assert len(temperature["cells"]) == 1
    assert temperature["cells"][0]["variables"][0]["id"] == "T2M"

    vegetation = result_store.map_index(variable="NDVI", start=2016, end=2024)
    assert len(vegetation["cells"]) == 1
    assert vegetation["cells"][0]["verdict"]["per_decade"] == 0.05

    wrong_level = result_store.map_index(variable="T2M", start=2016, end=2024,
                                         level="continent")
    assert wrong_level["cells"] == []


# --------------------------------------------------------------------------
# custom geometry
# --------------------------------------------------------------------------
def test_custom_polygon_round_trips_and_is_part_of_the_key(store):
    spec = make_spec(region="custom:test",
                     custom_areas=[{"id": "custom:test", "name": "Drawn lasso",
                                    "level": "custom", "geometry": SQUARE,
                                    "bbox": [0.0, 0.0, 1.0, 1.0]}],
                     geometry_versions={"custom:test": "v-custom-1"})
    result = make_result(region={"id": "custom:test", "name": "Drawn lasso",
                                 "level": "custom", "bbox": [0.0, 0.0, 1.0, 1.0]})
    saved = result_store.save(spec, result)
    record = result_store.get_result(saved["id"])
    area = record["areas"][0]
    assert area["geometry"] == SQUARE
    assert area["boundary_version"] == "v-custom-1"
    assert record["payload"] is not None

    moved = make_spec(region="custom:test",
                      custom_areas=[{"id": "custom:test", "name": "Drawn lasso",
                                     "level": "custom", "geometry": WIDER_SQUARE,
                                     "bbox": [0.0, 0.0, 2.0, 2.0]}],
                      geometry_versions={"custom:test": "v-custom-1"})
    other = result_store.save(moved, result)
    assert other["key"] != saved["key"]
    assert other["id"] != saved["id"]


# --------------------------------------------------------------------------
# concurrency
# --------------------------------------------------------------------------
def test_concurrent_saves_leave_exactly_one_row(store):
    spec = make_spec()
    result = make_result()
    barrier = threading.Barrier(8)

    def writer():
        barrier.wait()
        return result_store.save(spec, result)

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = [future.result() for future in
                    [pool.submit(writer) for _ in range(8)]]

    assert all(outcome["ok"] for outcome in outcomes)
    assert len({outcome["id"] for outcome in outcomes}) == 1
    listing = result_store.list_results()
    assert listing["total"] == 1

    connection = sqlite3.connect(str(store))
    rows = connection.execute("SELECT COUNT(*) FROM results").fetchone()[0]
    connection.close()
    assert rows == 1


# --------------------------------------------------------------------------
# stats, delete, listing
# --------------------------------------------------------------------------
def test_storage_stats_and_delete_are_honest(store):
    analysis = result_store.save(make_spec(), make_result())
    compare = result_store.save(make_spec(compare_region="country:ken"),
                                make_result(compare=make_compare()))
    stats = result_store.storage_stats()
    assert stats["count"] == 2
    assert stats["kinds"] == {"analysis": 1, "compare": 1}
    assert stats["bytes"] > 0
    assert not os.path.isabs(stats["path"])
    assert stats["path"].endswith("results.sqlite3")
    assert stats["oldest"] and stats["newest"]
    assert "error" not in stats

    assert result_store.delete_result(analysis["id"]) is True
    assert result_store.delete_result(analysis["id"]) is False
    assert result_store.delete_result("unknown-id") is False
    assert result_store.get_result(compare["id"])["kind"] == "compare"
    assert result_store.storage_stats()["count"] == 1


def test_list_filters_pagination_and_identity_lookup(store):
    analysis = result_store.save(make_spec(), make_result())
    compare = result_store.save(make_spec(compare_region="country:ken"),
                                make_result(compare=make_compare()))
    ndvi = result_store.save(
        make_spec(variables=["NDVI"]),
        make_result(blocks=[make_block("NDVI", "Vegetation Greenness (NDVI)",
                                       "index", 0.05)]))

    assert result_store.list_results(kind="compare")["total"] == 1
    assert result_store.list_results(kind="analysis")["total"] == 2
    assert result_store.list_results(variable="NDVI")["total"] == 1
    assert result_store.list_results(query="kenya")["total"] == 1
    assert result_store.list_results(query="2016")["total"] == 3
    assert result_store.list_results(query="no-such-area")["total"] == 0

    page = result_store.list_results(limit=1)
    assert page["total"] == 3 and len(page["results"]) == 1
    second = result_store.list_results(limit=1, offset=1)
    assert second["results"][0]["id"] != page["results"][0]["id"]

    found = result_store.find_saved(make_result(), make_spec())
    assert found["id"] == analysis["id"]
    found_without_spec = result_store.find_saved(make_result())
    assert found_without_spec["id"] == analysis["id"]
    assert result_store.find_saved({"series": []}) is None
    assert {analysis["id"], compare["id"], ndvi["id"]} == {
        row["id"] for row in result_store.list_results()["results"]}


# --------------------------------------------------------------------------
# import / validate
# --------------------------------------------------------------------------
def test_import_rejects_unknown_schema_and_marks_old_methods_legacy(store):
    saved = result_store.save(make_spec(), make_result())
    record = result_store.get_result(saved["id"])
    ok, errors = result_store.validate_record(record)
    assert ok is True and errors == []

    broken = dict(record, schema_version=99)
    ok, errors = result_store.validate_record(broken)
    assert ok is False
    assert any("schema_version" in error for error in errors)
    rejected = result_store.import_record(broken)
    assert rejected["ok"] is False
    assert "Invalid historical record" == rejected["error"]
    assert result_store.storage_stats()["count"] == 1

    legacy = dict(record, method_version="polygon-sen-calendar-fdr-v1")
    legacy.pop("key")
    imported = result_store.import_record(legacy)
    assert imported["ok"] is True
    assert imported["status"] == "legacy"
    assert imported["id"] != saved["id"]
    assert imported["stale_reason"]
    assert result_store.storage_stats()["count"] == 2

    same = result_store.import_record(record)
    assert same["ok"] is True
    assert same["id"] == saved["id"]
    assert same["updated"] is True
    assert result_store.storage_stats()["count"] == 2


def test_validate_record_names_every_missing_field():
    ok, errors = result_store.validate_record({"kind": "nonsense"})
    assert ok is False
    joined = " ".join(errors)
    for field in ("schema_version", "operation", "title", "created_at",
                  "method_version", "provider_family", "areas", "variables",
                  "window", "payload"):
        assert field in joined


# --------------------------------------------------------------------------
# defensive shapes for other operations
# --------------------------------------------------------------------------
def test_other_operations_store_a_usable_title_and_area(store):
    scan_spec = {"operation": "scan", "variables": ["T2M", "PRECTOTCORR"],
                 "region": "country:gha", "start": 2016, "end": 2024,
                 "provider": "auto", "method_version": CURRENT}
    scan_result = {
        "region": dict(GHANA), "start": 2016, "end": 2024,
        "grid": {"nx": 5, "ny": 5, "bbox": GHANA["bbox"]},
        "window": {"last_month": None, "partial_years": []},
        "scanned": [{"id": "T2M", "name": "Air Temperature", "unit": "\u00b0C",
                     "ok": True, "per_decade": 0.2, "significant": True,
                     "direction": "rising", "provenance": {"provider": "nasa-merra2"}},
                    {"id": "PRECTOTCORR", "name": "Precipitation", "unit": "mm/day",
                     "ok": False, "error": "no data",
                     "provenance": {"provider": "nasa-hydrology"}}],
        "summary": {}, "sources": ["NASA MERRA-2"],
    }
    saved = result_store.save(scan_spec, scan_result)
    assert saved["ok"] is True
    assert saved["kind"] == "discovery"
    assert "Ghana" in saved["title"] and "2016" in saved["title"]
    assert {variable["id"] for variable in saved["variables"]} == {"T2M", "PRECTOTCORR"}

    overview_spec = {"operation": "overview", "variables": ["T2M"],
                     "features": ["country:gha", "country:ken"],
                     "start": 2016, "end": 2024, "provider": "auto",
                     "method_version": CURRENT}
    overview_result = {"rows": [{"id": "country:gha", "overall": {"ok": True}},
                                {"id": "country:ken", "overall": {"ok": False}}],
                       "variable": "T2M", "start": 2016, "end": 2024}
    layer = result_store.save(overview_spec, overview_result)
    assert layer["ok"] is True
    assert layer["kind"] == "layer"
    assert len(layer["areas"]) == 2
    assert {area["id"] for area in layer["areas"]} == {"country:gha", "country:ken"}
    assert "2 areas" in layer["title"]

    relationship_spec = {"operation": "interconnections", "variables": ["T2M"],
                         "relationship_variables": ["T2M", "NDVI"],
                         "region": "country:gha", "start": 2016, "end": 2024,
                         "provider": "auto", "method_version": CURRENT}
    relationship_result = {"region": dict(GHANA), "start": 2016, "end": 2024,
                           "variables": [{"id": "T2M", "name": "Air Temperature",
                                          "unit": "\u00b0C"},
                                         {"id": "NDVI", "name": "Vegetation Greenness (NDVI)",
                                          "unit": "index"}],
                           "local": {}, "global": None, "scope": "local"}
    relationships = result_store.save(relationship_spec, relationship_result)
    assert relationships["ok"] is True
    assert relationships["kind"] == "relationships"
    assert {variable["id"] for variable in relationships["variables"]} == {"T2M", "NDVI"}
    assert result_store.map_index(variable="T2M", start=2016, end=2024)["cells"] == []


# --------------------------------------------------------------------------
# HTTP routes added for the saved trend map
# --------------------------------------------------------------------------
class _FakeHandler(server.Handler):
    """Exercise the HTTP routing without opening a network socket."""

    def __init__(self, path, body=None):
        self.path = path
        raw = json.dumps(body).encode() if body is not None else b""
        self.headers = {"Content-Length": str(len(raw))}
        self.rfile = io.BytesIO(raw)
        self.result = None

    def _json(self, status, body):
        json.dumps(body, allow_nan=False)
        self.result = (status, body)
        return self.result

    def _static(self, path):
        return self._json(404, {"error": "not found"})


def test_http_routes_expose_saved_records_without_absolute_paths(store):
    saved = result_store.save(make_spec(), make_result())

    handler = _FakeHandler("/api/results")
    handler.do_GET()
    code, listing = handler.result
    assert code == 200
    assert listing["total"] == 1
    assert listing["storage"]["count"] == 1
    assert not os.path.isabs(listing["storage"]["path"])

    handler = _FakeHandler("/api/results/map?variable=T2M&start=2016&end=2024")
    handler.do_GET()
    code, index = handler.result
    assert code == 200
    assert index["exact"] is True and len(index["cells"]) == 1

    handler = _FakeHandler("/api/results/map")
    handler.do_GET()
    assert handler.result[0] == 400
    handler = _FakeHandler("/api/results/map?variable=T2M")
    handler.do_GET()
    assert handler.result[0] == 400

    handler = _FakeHandler("/api/results/%s" % saved["id"])
    handler.do_GET()
    assert handler.result[0] == 200
    assert handler.result[1]["id"] == saved["id"]
    handler = _FakeHandler("/api/results/missing-record")
    handler.do_GET()
    assert handler.result[0] == 404

    handler = _FakeHandler("/api/results", {"action": "delete", "id": saved["id"]})
    handler.do_POST()
    assert handler.result[0] == 200 and handler.result[1]["deleted"] is True
    handler = _FakeHandler("/api/results", {"action": "delete", "id": saved["id"]})
    handler.do_POST()
    assert handler.result[0] == 404
    handler = _FakeHandler("/api/results", {"action": "nonsense"})
    handler.do_POST()
    assert handler.result[0] == 400
    assert result_store.storage_stats()["count"] == 0


def test_http_import_route_round_trips_historical_evidence(store):
    saved = result_store.save(make_spec(), make_result())
    record = result_store.get_result(saved["id"])

    handler = _FakeHandler("/api/results", {"action": "import", "record": record})
    handler.do_POST()
    assert handler.result[0] == 201
    assert handler.result[1]["id"] == saved["id"]

    handler = _FakeHandler("/api/results", {"action": "import",
                                            "record": dict(record, schema_version=99)})
    handler.do_POST()
    assert handler.result[0] == 400
    assert "schema_version" in " ".join(handler.result[1]["errors"])

    handler = _FakeHandler("/api/results", {"action": "import", "record": "nope"})
    handler.do_POST()
    assert handler.result[0] == 400
    assert result_store.storage_stats()["count"] == 1
