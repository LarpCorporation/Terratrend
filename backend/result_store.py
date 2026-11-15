"""Durable, honest local storage for completed TerraTrend analyses.

One SQLite database under ``backend/cache/results.sqlite3`` (the ``cache`` tree
is git-ignored) holds exactly one row per canonical scientific result.  A row
keeps a compact queryable identity (areas + measurements + window + source
family) next to the exact completed result object as a JSON payload, so a
"Saved trend map" can colour areas without re-downloading anything and without
inventing numbers the analysis did not produce.

Rules this module enforces:

* the row identity is the *science* -- method version, operation, source
  family, ordered area geometry hashes, measurements with units, requested
  years, aggregation/grid identity.  Never the transient job id, never a
  timestamp, never a display name on its own;
* the same request saved twice updates one row, it never duplicates it;
* a record saved under an older method version stays readable but is labelled
  ``legacy`` and is never used to colour a current map cell;
* a record whose payload JSON cannot be decoded is labelled ``damaged``, is
  excluded from the map index, but still listed so the app can be honest;
* a corrupt, unwritable or foreign database never raises out of :func:`save`;
  it logs to stderr and returns an error marker;
* credentials are stripped from the payload and provenance before insert *and*
  again before return, so a token can never be persisted or handed back.

The geographic rule that matters scientifically: :func:`map_index` only emits
the area identity that the stored record actually analysed.  A national
aggregate never becomes a subregion cell; the caller matches on area id *and*
level.
"""
import hashlib
import json
import os
import re
import sqlite3
import sys
import threading
import datetime

CURRENT_SCHEMA_VERSION = 1
# Kept in step with the immutable request identity stamped by server.do_POST
# (spec["method_version"] = "polygon-sen-calendar-fdr-v2-auto").
CURRENT_METHOD_VERSION = "polygon-sen-calendar-fdr-v2-auto"

DB_FILENAME = "results.sqlite3"
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

KINDS = ("analysis", "compare", "discovery", "relationships", "layer", "event")
STATUSES = ("current", "legacy", "damaged")
PROVIDER_FAMILIES = ("auto", "nasa-merra2", "nasa-giovanni", "nasa-appeears",
                     "multi-source", "nasa-hydrology", "noaa-cdo", "other")

DEFAULT_LIST_LIMIT = 100
MAX_LIST_LIMIT = 1000
DEFAULT_MAP_LIMIT = 400
MAX_MAP_LIMIT = 2000

_LOCK = threading.RLock()

_SECRET_KEY = re.compile(
    r"(?i)(token|password|secret|authorization|cookie|api[_-]?key|bearer|credential)")
_SECRET_VALUE = re.compile(
    r"(?i)("
    r"\bbearer\s+[a-z0-9._~+/=-]{8,}"
    r"|^\s*authorization\s*[:=]"
    r"|earthdata[_-]?token\s*[:=]"
    r"|\beyj[a-z0-9_-]{12,}\.[a-z0-9_-]{8,}"
    r")")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS results (
    id TEXT PRIMARY KEY,
    result_key TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    operation TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    method_version TEXT NOT NULL,
    provider_family TEXT NOT NULL,
    areas TEXT NOT NULL,
    variables TEXT NOT NULL,
    window_json TEXT NOT NULL,
    routes TEXT NOT NULL,
    payload TEXT NOT NULL,
    provenance TEXT NOT NULL,
    status TEXT NOT NULL,
    size_bytes INTEGER NOT NULL
)
"""
INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS results_created ON results (created_at)",
    "CREATE INDEX IF NOT EXISTS results_kind ON results (kind, created_at)",
)

UPSERT_SQL = """
INSERT INTO results (id, result_key, kind, operation, title, created_at,
                     schema_version, method_version, provider_family, areas,
                     variables, window_json, routes, payload, provenance,
                     status, size_bytes)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(result_key) DO UPDATE SET
    id=excluded.id,
    kind=excluded.kind,
    operation=excluded.operation,
    title=excluded.title,
    created_at=excluded.created_at,
    schema_version=excluded.schema_version,
    method_version=excluded.method_version,
    provider_family=excluded.provider_family,
    areas=excluded.areas,
    variables=excluded.variables,
    window_json=excluded.window_json,
    routes=excluded.routes,
    payload=excluded.payload,
    provenance=excluded.provenance,
    status=excluded.status,
    size_bytes=excluded.size_bytes
"""

_SUMMARY_COLUMNS = ("id, result_key, kind, operation, title, created_at, "
                    "schema_version, method_version, provider_family, areas, "
                    "variables, window_json, routes, provenance, status, "
                    "size_bytes")
_RECORD_COLUMNS = _SUMMARY_COLUMNS + ", payload"


# --------------------------------------------------------------------------
# paths / time / json helpers
# --------------------------------------------------------------------------
def _db_path():
    """Absolute path of the results database (env override wins)."""
    override = os.environ.get("TERRATREND_RESULTS_DB")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    return os.path.join(CACHE_DIR, DB_FILENAME)


def _display_path():
    """Cache-relative name only; never leak an absolute host path."""
    path = _db_path()
    try:
        rel = os.path.relpath(path, REPO_DIR)
        if not rel.startswith(".."):
            return rel.replace(os.sep, "/")
    except (ValueError, OSError):
        pass
    return os.path.basename(path)


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _coerce_iso(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        datetime.datetime.fromisoformat(candidate)
    except ValueError:
        return None
    return text


def _finite(value):
    return value == value and value not in (float("inf"), float("-inf"))


def _json_safe(value):
    """Make a value strictly JSON-encodable (non-finite floats become null)."""
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, float):
        return value if _finite(value) else None
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return str(value)


def _dumps(value):
    return json.dumps(_json_safe(value), ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False, sort_keys=True)


def _loads(text):
    if isinstance(text, (dict, list)):
        return text
    if not isinstance(text, str) or not text:
        return None
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


def _as_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clamp(value, low, high, default):
    number = _as_int(value, default)
    if number is None:
        number = default
    return max(low, min(high, number))


# --------------------------------------------------------------------------
# sanitizing
# --------------------------------------------------------------------------
def sanitize(value):
    """Return a copy with credential-looking keys and token values removed.

    Applied to the payload and provenance before insert and again before the
    record leaves the store, so a NASA Earthdata token can never be written to
    disk or handed back to a caller.
    """
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if isinstance(key, str) and _SECRET_KEY.search(key):
                continue
            if isinstance(item, str) and _SECRET_VALUE.search(item):
                continue
            out[key] = sanitize(item)
        return out
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            if isinstance(item, str) and _SECRET_VALUE.search(item):
                continue
            out.append(sanitize(item))
        return out
    return value


# --------------------------------------------------------------------------
# connections
# --------------------------------------------------------------------------
def _connect(write=False):
    """Open a short-lived connection; ``None`` when there is nothing to read."""
    path = _db_path()
    if write:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
    elif not os.path.exists(path):
        return None
    conn = sqlite3.connect(path, timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
    except sqlite3.Error:
        if write:
            conn.close()
            raise
    return conn


def _prepare(conn):
    """Create the schema under one immediate transaction (idempotent)."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(SCHEMA_SQL)
        for statement in INDEX_SQL:
            conn.execute(statement)
        conn.execute("COMMIT")
    except Exception:
        _rollback(conn)
        raise


def _rollback(conn):
    try:
        conn.execute("ROLLBACK")
    except sqlite3.Error:
        pass


def _failure(message):
    text = str(message).strip() or "unknown storage error"
    try:
        sys.stderr.write("result_store: " + text + "\n")
    except Exception:  # noqa: BLE001 - stderr is best effort
        pass
    return {"ok": False, "saved": False, "error": text, "id": None,
            "key": None, "result_id": None}


# --------------------------------------------------------------------------
# canonical identity
# --------------------------------------------------------------------------
def _geometry_hash(geometry):
    if not isinstance(geometry, dict):
        return None
    try:
        text = json.dumps(geometry, sort_keys=True, separators=(",", ":"),
                          default=str)
    except (TypeError, ValueError):
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _bbox_of(geometry):
    if not isinstance(geometry, dict):
        return None
    polys = geometry.get("coordinates")
    if not isinstance(polys, list) or not polys:
        return None
    if geometry.get("type") == "Polygon":
        polys = [polys]
    try:
        points = [point for poly in polys for point in poly[0]]
        lons = [float(p[0]) for p in points]
        lats = [float(p[1]) for p in points]
    except (TypeError, ValueError, IndexError):
        return None
    if not lons or not lats:
        return None
    return [min(lons), min(lats), max(lons), max(lats)]


def _level_from_id(area_id):
    text = str(area_id or "")
    if ":" not in text:
        return "unknown"
    prefix = text.split(":", 1)[0]
    return {"focus": "preset", "country": "country", "region": "region",
            "subcontinent": "subcontinent", "continent": "continent",
            "custom": "custom"}.get(prefix, prefix or "unknown")


def _custom_areas(spec):
    found = {}
    for area in spec.get("custom_areas") or []:
        if not isinstance(area, dict):
            continue
        props = area.get("properties") if isinstance(area.get("properties"), dict) else {}
        area_id = area.get("id") or props.get("id")
        if area_id:
            found[str(area_id)] = area
    return found


def _area(role, area_id, meta=None, custom=None, geometry_versions=None):
    meta = meta if isinstance(meta, dict) else {}
    custom = custom if isinstance(custom, dict) else {}
    props = custom.get("properties") if isinstance(custom.get("properties"), dict) else {}
    geometry = custom.get("geometry") if isinstance(custom.get("geometry"), dict) else None
    if geometry is None and isinstance(meta.get("geometry"), dict):
        geometry = meta["geometry"]
    # Accept both the Feature shape (geometry + properties) and the flatter
    # {id, name, geometry, bbox} shape a client may send in custom_areas.
    name = meta.get("name") or custom.get("name") or props.get("name") or area_id or "Unknown area"
    level = (meta.get("level") or custom.get("level") or props.get("level")
             or _level_from_id(area_id))
    bbox = meta.get("bbox") or custom.get("bbox") or props.get("bbox")
    if not (isinstance(bbox, (list, tuple)) and len(bbox) == 4):
        bbox = _bbox_of(geometry)
    # A drawn rectangle or lasso arrives with a generic label ("Coordinate
    # bounds", "Selected Area") or just its identity. Two different custom
    # areas would then look identical in the library, in a comparison legend
    # and on the chart. Derive a readable, coordinate-specific label instead.
    if bbox and _generic_area_name(name, area_id):
        name = _bbox_label(bbox)
    version = (meta.get("geometry_version") or custom.get("geometry_version")
               or props.get("geometry_version"))
    if not version and isinstance(geometry_versions, dict) and area_id:
        version = geometry_versions.get(area_id)
    if not version:
        version = _geometry_hash(geometry)
    return {
        "role": role,
        "id": str(area_id or "unknown"),
        "name": str(name),
        "level": str(level or "unknown"),
        "bbox": [float(v) for v in bbox] if bbox else None,
        "geometry": geometry,
        "boundary_version": version or None,
    }


GENERIC_AREA_NAMES = {
    "coordinate bounds", "selected area", "custom area", "custom selection",
    "custom", "area", "unknown area", "unnamed area", "selection",
}


def _generic_area_name(name, area_id):
    """True when a name carries no distinguishing information."""
    if not isinstance(name, str) or not name.strip():
        return True
    cleaned = name.strip().lower()
    if cleaned in GENERIC_AREA_NAMES:
        return True
    if area_id and cleaned == str(area_id).strip().lower():
        return True
    return cleaned.startswith("custom:")


def _bbox_label(bbox):
    """Human label for a bounds rectangle, e.g. ``2°W–0°E · 6–8°N``."""
    try:
        west, south, east, north = (float(v) for v in bbox)
    except (TypeError, ValueError):
        return "Custom area"

    def lon(value):
        suffix = "°E" if value >= 0 else "°W"
        return ("%g" % abs(value)) + suffix

    def lat(value):
        suffix = "°N" if value >= 0 else "°S"
        return ("%g" % abs(value)) + suffix

    return "%s–%s · %s–%s" % (lon(west), lon(east), lat(south), lat(north))


def _compare_meta(result):
    compare = result.get("compare") if isinstance(result.get("compare"), dict) else {}
    region = compare.get("region") if isinstance(compare.get("region"), dict) else {}
    return region or None


def _areas(spec, result):
    """Ordered area list: A (analysed), B (compared), then remote targets."""
    custom = _custom_areas(spec)
    versions = spec.get("geometry_versions") if isinstance(spec.get("geometry_versions"), dict) else {}
    primary_meta = result.get("region") if isinstance(result.get("region"), dict) else {}
    compare_meta = _compare_meta(result) or {}
    areas = []

    primary_id = spec.get("region")
    if primary_id is None and primary_meta.get("id"):
        primary_id = primary_meta.get("id")
    if primary_id:
        areas.append(_area("A", primary_id, primary_meta, custom.get(str(primary_id)), versions))

    compare_id = spec.get("compare_region")
    if compare_id:
        areas.append(_area("B", compare_id, compare_meta, custom.get(str(compare_id)), versions))

    if spec.get("operation") == "overview":
        for fid in spec.get("features") or []:
            areas.append(_area("layer", fid, None, custom.get(str(fid)), versions))
        if not areas:
            areas.append(_area("layer", "unknown"))
        return areas

    if spec.get('operation')=='event':
        for request in spec.get('event_requests') or []:
            fid=request.get('region')
            if fid and fid!=primary_id and not any(a['id']==fid for a in areas):
                areas.append(_area('event-source',fid,None,custom.get(str(fid)),versions))

    if spec.get("relationship_scope") == "remote":
        for fid in spec.get("target_regions") or []:
            areas.append(_area("B", fid, None, custom.get(str(fid)), versions))
    return areas


def _catalog_variable(variable_id):
    try:
        import catalog  # local import: keeps this module usable from scripts
        return next((v for v in catalog.CATALOG if v.get("id") == variable_id), None)
    except Exception:  # noqa: BLE001 - catalog is optional metadata here
        return None


def _measurements(spec, result):
    found = {}

    def add(item, name=None, unit=None):
        if isinstance(item, dict):
            variable_id = item.get("id") or item.get("variable")
            name = item.get("name") or name
            unit = item.get("unit", unit)
        else:
            variable_id = item
        if not variable_id:
            return
        variable_id = str(variable_id)
        if variable_id in found:
            return
        found[variable_id] = {
            "id": variable_id,
            "name": str(name or variable_id),
            "unit": unit if isinstance(unit, str) else None,
        }

    series = [b for b in (result.get("series") or []) if isinstance(b, dict)]
    compare = result.get("compare") if isinstance(result.get("compare"), dict) else {}
    series += [b for b in (compare.get("series") or []) if isinstance(b, dict)]
    for block in series:
        add(block.get("variable"))
    for row in result.get("scanned") or []:
        if isinstance(row, dict):
            add({"id": row.get("id"), "name": row.get("name"),
                 "unit": row.get("unit")})
    for item in result.get("variables") or []:
        add(item)

    requested = list(spec.get("variables") or []) + list(spec.get("relationship_variables") or [])
    if isinstance(result.get("variable"), str):
        requested.append(result["variable"])
    for variable_id in requested:
        if not isinstance(variable_id, str) or variable_id in found:
            continue
        meta = _catalog_variable(variable_id) or {}
        add({"id": variable_id, "name": meta.get("name"),
             "unit": meta.get("unit")})
    return sorted(found.values(), key=lambda item: item["id"])


def _window(spec, result):
    start = _as_int(spec.get("start"), _as_int(result.get("start"), 0)) or 0
    end = _as_int(spec.get("end"), _as_int(result.get("end"), 0)) or 0
    window = result.get("window") if isinstance(result.get("window"), dict) else {}
    months = result.get("months") if isinstance(result.get("months"), list) else []
    first_month = window.get("first_month")
    last_month = window.get("last_month")
    if first_month is None and months:
        first_month = months[0]
    if last_month is None and months:
        last_month = months[-1]
    month_count = len(months) if months else max(0, (end - start + 1)) * 12
    series = [b for b in (result.get("series") or []) if isinstance(b, dict)]
    if not series:
        compare = result.get("compare") if isinstance(result.get("compare"), dict) else {}
        series = [b for b in (compare.get("series") or []) if isinstance(b, dict)]
    complete_years = 0
    if series:
        complete_years = sum(1 for point in series[0].get("yearly_timeseries") or []
                             if isinstance(point, dict) and point.get("complete"))
    return {
        "start": start,
        "end": end,
        "first_month": first_month,
        "last_month": last_month,
        "months": month_count,
        "complete_years": complete_years,
    }


def _routes(spec, result):
    routes = {}
    raw = spec.get("routes")
    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(key, str):
                routes[key] = value
    series = [b for b in (result.get("series") or []) if isinstance(b, dict)]
    compare = result.get("compare") if isinstance(result.get("compare"), dict) else {}
    series += [b for b in (compare.get("series") or []) if isinstance(b, dict)]
    for block in series:
        variable = block.get("variable") if isinstance(block.get("variable"), dict) else {}
        provenance = block.get("provenance") if isinstance(block.get("provenance"), dict) else {}
        variable_id = variable.get("id")
        provider = provenance.get("provider")
        if variable_id and provider:
            routes.setdefault(str(variable_id), provider)
    if not routes:
        for row in result.get("scanned") or []:
            if not isinstance(row, dict):
                continue
            provenance = row.get("provenance") if isinstance(row.get("provenance"), dict) else {}
            if row.get("id") and provenance.get("provider"):
                routes.setdefault(str(row["id"]), provenance["provider"])
    return routes


def _provider_family(spec, result):
    named = spec.get("provider")
    if isinstance(named, str) and named in PROVIDER_FAMILIES:
        return named
    seen = []
    series = [b for b in (result.get("series") or []) if isinstance(b, dict)]
    compare = result.get("compare") if isinstance(result.get("compare"), dict) else {}
    series += [b for b in (compare.get("series") or []) if isinstance(b, dict)]
    for block in series:
        provenance = block.get("provenance") if isinstance(block.get("provenance"), dict) else {}
        provider = provenance.get("provider")
        if provider and provider not in seen:
            seen.append(provider)
    for item in result.get("provenance") or []:
        if isinstance(item, dict):
            provider = item.get("provider")
            if provider and provider not in seen:
                seen.append(provider)
    if len(seen) == 1:
        return seen[0] if seen[0] in PROVIDER_FAMILIES else "other"
    if len(seen) > 1:
        return "multi-source"
    return "other"


def _aggregation_identity(result):
    aggregations = set()
    for item in result.get("provenance") or []:
        if isinstance(item, dict) and item.get("aggregation"):
            aggregations.add(str(item["aggregation"]))
    series = [b for b in (result.get("series") or []) if isinstance(b, dict)]
    compare = result.get("compare") if isinstance(result.get("compare"), dict) else {}
    series += [b for b in (compare.get("series") or []) if isinstance(b, dict)]
    for block in series:
        provenance = block.get("provenance") if isinstance(block.get("provenance"), dict) else {}
        if provenance.get("aggregation"):
            aggregations.add(str(provenance["aggregation"]))
    grid = result.get("grid") if isinstance(result.get("grid"), dict) else {}
    return {
        "aggregation": sorted(aggregations),
        "nx": _as_int(grid.get("nx")),
        "ny": _as_int(grid.get("ny")),
    }


def _method_version(spec):
    value = spec.get("method_version")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "unknown"


def _kind(spec, result, override=None):
    if isinstance(override, str) and override.strip():
        return override.strip()
    operation = str(spec.get("operation") or "analyze")
    if operation=='event':return 'event'
    if operation == "analyze":
        return "compare" if result.get("compare") else "analysis"
    if operation == "scan":
        return "discovery"
    if operation == "interconnections":
        return "relationships"
    if operation == "overview":
        return "layer"
    return "analysis"


def _area_label(areas):
    primary = next((a for a in areas if a["role"] == "A"), None)
    compared = next((a for a in areas if a["role"] == "B"), None)
    if primary and compared and primary["id"] != compared["id"]:
        return primary["name"] + " vs " + compared["name"]
    if primary:
        return primary["name"]
    layer = [a for a in areas if a["role"] == "layer"]
    if layer:
        return "%d areas" % len(layer)
    return "Saved area"


def _title(areas, variables, window):
    names = ", ".join(v["name"] for v in variables[:3]) or "Analysis"
    if len(variables) > 3:
        names += " +%d more" % (len(variables) - 3)
    return "%s \u00b7 %s \u00b7 %d\u2013%d" % (
        _area_label(areas), names, window["start"], window["end"])


def _trimmed_provenance(result):
    keep = ("provider", "source", "resource", "dataset", "collection_version",
            "field", "policy", "citation", "access", "aggregation", "quality",
            "geometry_version", "resolution", "retrieved_utc",
            "first_observed_month", "last_observed_month",
            "spatial_detail_available", "monthly_area_coverage_known")
    trimmed = []
    for item in result.get("provenance") or []:
        if not isinstance(item, dict):
            continue
        trimmed.append({k: item[k] for k in keep if k in item})
    return sanitize(trimmed)


def _canonical_payload(spec, result):
    areas = _areas(spec, result)
    variables = _measurements(spec, result)
    window = _window(spec, result)
    identity = _aggregation_identity(result)
    payload = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "method_version": _method_version(spec),
        "operation": str(spec.get("operation") or "analyze"),
        "provider_family": _provider_family(spec, result),
        "areas": [_area_key(a) for a in areas],
        "levels": [a["level"] for a in areas],
        "variables": [{"id": v["id"], "unit": v["unit"]} for v in variables],
        "years": [window["start"], window["end"]],
        "aggregation": identity,
    }
    if spec.get('operation')=='event':payload['event_id']=spec.get('event_id') or result.get('id')
    return payload


def _area_key(area):
    digest = _geometry_hash(area.get("geometry"))
    if digest is None and area.get("boundary_version"):
        digest = "boundary:" + str(area["boundary_version"])
    if digest is None and area.get("bbox"):
        digest = "bbox:" + ",".join("%.6f" % float(v) for v in area["bbox"])
    return {
        "role": area.get("role"),
        "id": area.get("id"),
        "level": area.get("level"),
        "geometry": digest or "unknown",
    }


def canonical_key(spec, result):
    """Stable id of the *science* in one request, independent of names/clock."""
    payload = _canonical_payload(spec if isinstance(spec, dict) else {},
                                 result if isinstance(result, dict) else {})
    return hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# row <-> record conversion
# --------------------------------------------------------------------------
def _effective_status(stored_status, method_version, payload_ok):
    if stored_status == "damaged" or not payload_ok:
        return "damaged"
    if str(method_version or "") != CURRENT_METHOD_VERSION:
        return "legacy"
    return "current"


def _stale_reason(method_version):
    return ("Saved under method version %r; the current method is %r. "
            "Readable and honest, but not used for current map colouring."
            % (str(method_version or "unknown"), CURRENT_METHOD_VERSION))


def _row_summary(row, status=None, payload_ok=True, stale_reason=None):
    areas = _loads(row["areas"]) or []
    variables = _loads(row["variables"]) or []
    window = _loads(row["window_json"]) or {}
    if status is None:
        status = _effective_status(row["status"], row["method_version"], payload_ok)
    summary = {
        "id": row["id"],
        "key": row["result_key"],
        "kind": row["kind"],
        "operation": row["operation"],
        "title": row["title"],
        "created_at": row["created_at"],
        "schema_version": row["schema_version"],
        "method_version": row["method_version"],
        "provider_family": row["provider_family"],
        "status": status,
        "size_bytes": row["size_bytes"],
        "areas": [{"role": a.get("role"), "id": a.get("id"),
                   "name": a.get("name"), "level": a.get("level")}
                  for a in areas if isinstance(a, dict)],
        "variables": variables,
        "window": window,
        "routes": _loads(row["routes"]) or {},
        "damaged": status == "damaged",
    }
    if status == "legacy":
        summary["stale_reason"] = stale_reason or _stale_reason(row["method_version"])
    if status == "damaged":
        summary["reason"] = ("Stored payload could not be decoded; the record is "
                            "kept for the audit trail but cannot be rendered.")
    return sanitize(summary)


def _record_from_row(row, status=None):
    areas = _loads(row["areas"])
    variables = _loads(row["variables"])
    window = _loads(row["window_json"])
    routes = _loads(row["routes"])
    provenance = _loads(row["provenance"])
    payload = _loads(row["payload"])
    payload_ok = payload is not None
    if status is None:
        status = _effective_status(row["status"], row["method_version"], payload_ok)
    record = {
        "id": row["id"],
        "key": row["result_key"],
        "kind": row["kind"],
        "operation": row["operation"],
        "title": row["title"],
        "created_at": row["created_at"],
        "schema_version": row["schema_version"],
        "method_version": row["method_version"],
        "provider_family": row["provider_family"],
        "areas": areas if isinstance(areas, list) else [],
        "variables": variables if isinstance(variables, list) else [],
        "window": window if isinstance(window, dict) else {},
        "routes": routes if isinstance(routes, dict) else {},
        "payload": payload if payload_ok else None,
        "provenance": provenance if isinstance(provenance, list) else [],
        "status": status,
        "size_bytes": row["size_bytes"],
        "damaged": status == "damaged",
    }
    if status == "legacy":
        record["stale_reason"] = _stale_reason(row["method_version"])
    if status == "damaged":
        record["reason"] = ("Stored payload could not be decoded; the record is "
                           "kept for the audit trail but cannot be rendered.")
    return sanitize(record)


def _payload_valid(text):
    if not isinstance(text, str) or not text.strip():
        return False
    try:
        json.loads(text)
    except (ValueError, TypeError):
        return False
    return True


# --------------------------------------------------------------------------
# writing
# --------------------------------------------------------------------------
def _store(row):
    conn = _connect(write=True)
    try:
        _prepare(conn)
        conn.execute("BEGIN IMMEDIATE")
        try:
            existing = conn.execute(
                "SELECT id FROM results WHERE result_key=?",
                (row["key"],)).fetchone()
            conn.execute(UPSERT_SQL, (
                row["id"], row["key"], row["kind"], row["operation"],
                row["title"], row["created_at"], row["schema_version"],
                row["method_version"], row["provider_family"],
                _dumps(row["areas"]), _dumps(row["variables"]),
                _dumps(row["window"]), _dumps(row["routes"]),
                row["payload"], _dumps(row["provenance"]), row["status"],
                row["size_bytes"]))
            conn.execute("COMMIT")
        except Exception:
            _rollback(conn)
            raise
    finally:
        conn.close()
    created = existing is None
    summary = {
        "id": row["id"],
        "key": row["key"],
        "kind": row["kind"],
        "operation": row["operation"],
        "title": row["title"],
        "created_at": row["created_at"],
        "schema_version": row["schema_version"],
        "method_version": row["method_version"],
        "provider_family": row["provider_family"],
        "status": row["status"],
        "size_bytes": row["size_bytes"],
        "areas": [{"role": a.get("role"), "id": a.get("id"),
                   "name": a.get("name"), "level": a.get("level")}
                  for a in row["areas"]],
        "variables": row["variables"],
        "window": row["window"],
        "routes": row["routes"],
        "damaged": row["status"] == "damaged",
        "ok": True,
        "saved": True,
        "created": created,
        "updated": not created,
    }
    if row["status"] == "legacy":
        summary["stale_reason"] = _stale_reason(row["method_version"])
    return summary


def _build_row(spec, result, kind=None, status=None, record=None):
    """Assemble one row. ``record`` supplies an explicit imported identity."""
    areas = _areas(spec, result)
    variables = _measurements(spec, result)
    window = _window(spec, result)
    payload = sanitize(result)
    payload_text = _dumps(payload)
    key = canonical_key(spec, result)
    method_version = _method_version(spec)
    status = status or ("current" if method_version == CURRENT_METHOD_VERSION
                        else "legacy")
    size_bytes = len(payload_text.encode("utf-8"))
    for blob in (areas, variables, window, _routes(spec, result),
                 _trimmed_provenance(result)):
        size_bytes += len(_dumps(blob).encode("utf-8"))
    created_at = _now_iso()
    if record is not None and _coerce_iso(record.get("created_at")):
        created_at = _coerce_iso(record.get("created_at"))
    return {
        "id": key[:24],
        "key": key,
        "kind": _kind(spec, result, kind),
        "operation": str(spec.get("operation") or "analyze"),
        "title": (result.get('title')+' · '+str(window['start'])+'–'+str(window['end'])) if spec.get('operation')=='event' and result.get('title') else _title(areas, variables, window),
        "created_at": created_at,
        "schema_version": CURRENT_SCHEMA_VERSION,
        "method_version": method_version,
        "provider_family": _provider_family(spec, result),
        "areas": areas,
        "variables": variables,
        "window": window,
        "routes": _routes(spec, result),
        "payload": payload_text,
        "provenance": _trimmed_provenance(result),
        "status": status,
        "size_bytes": size_bytes,
    }


def save(spec, result, *, kind=None):
    """Persist one completed analysis; same key updates the existing row.

    Returns a record summary with ``ok``/``saved``/``created`` flags, or an
    error marker (never raises) when the database is corrupt or unwritable.
    """
    with _LOCK:
        try:
            if not isinstance(spec, dict):
                return _failure("save() needs the request spec object")
            if not isinstance(result, dict):
                return _failure("save() needs the completed result object")
            if kind is not None and kind not in KINDS:
                return _failure("Unknown result kind %r" % (kind,))
            row = _build_row(spec, result, kind=kind)
            return _store(row)
        except (sqlite3.Error, OSError, ValueError, TypeError) as error:
            return _failure(error)
        except Exception as error:  # noqa: BLE001 - storage must never break analysis
            return _failure(error)


def delete_result(result_id):
    """Remove one stored result by id (or full canonical key)."""
    if not isinstance(result_id, str) or not result_id.strip():
        return False
    if not os.path.exists(_db_path()):
        return False
    with _LOCK:
        conn = None
        try:
            conn = _connect(write=True)
            _prepare(conn)
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = conn.execute(
                    "DELETE FROM results WHERE id=? OR result_key=?",
                    (result_id.strip(), result_id.strip()))
                deleted = cursor.rowcount > 0
                conn.execute("COMMIT")
            except Exception:
                _rollback(conn)
                raise
            return bool(deleted)
        except (sqlite3.Error, OSError):
            if conn is not None:
                try:
                    sys.stderr.write("result_store: could not delete saved result\n")
                except Exception:  # noqa: BLE001
                    pass
            return False
        finally:
            if conn is not None:
                conn.close()


# --------------------------------------------------------------------------
# reading
# --------------------------------------------------------------------------
def _list_rows(conn, kind):
    """Rows plus a payload-validity flag, using SQLite's JSON1 when present."""
    statement = "SELECT %s" % _SUMMARY_COLUMNS
    params = ()
    if kind:
        statement += ", json_valid(payload) AS payload_ok FROM results WHERE kind=?"
        params = (kind,)
    else:
        statement += ", json_valid(payload) AS payload_ok FROM results"
    statement += " ORDER BY created_at DESC, id"
    try:
        return [(row, bool(row["payload_ok"]))
                for row in conn.execute(statement, params).fetchall()]
    except sqlite3.OperationalError:
        statement = "SELECT %s, payload FROM results" % _SUMMARY_COLUMNS
        params = ()
        if kind:
            statement += " WHERE kind=?"
            params = (kind,)
        statement += " ORDER BY created_at DESC, id"
        return [(row, _payload_valid(row["payload"]))
                for row in conn.execute(statement, params).fetchall()]


def _matches_variable(variables, needle):
    if not needle:
        return True
    needle = str(needle).lower()
    for item in variables or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("id", "")).lower() == needle:
            return True
        if str(item.get("name", "")).lower() == needle:
            return True
    return False


def _matches_query(summary, needle):
    if not needle:
        return True
    haystack = [summary.get("title") or "", summary.get("operation") or "",
                summary.get("kind") or ""]
    window = summary.get("window") or {}
    haystack.extend([str(window.get("start") or ""), str(window.get("end") or ""),
                     str(window.get("first_month") or ""),
                     str(window.get("last_month") or "")])
    for area in summary.get("areas") or []:
        haystack.extend([str(area.get("id") or ""), str(area.get("name") or ""),
                         str(area.get("level") or "")])
    for variable in summary.get("variables") or []:
        haystack.extend([str(variable.get("id") or ""),
                         str(variable.get("name") or "")])
    return needle in " ".join(haystack).lower()


def list_results(*, query=None, kind=None, variable=None, limit=DEFAULT_LIST_LIMIT,
                 offset=0):
    """Page through stored summaries; never duplicate one canonical result."""
    limit = _clamp(limit, 1, MAX_LIST_LIMIT, DEFAULT_LIST_LIMIT)
    offset = max(0, _as_int(offset, 0) or 0)
    kind = kind if kind in KINDS else None
    with _LOCK:
        conn = None
        try:
            conn = _connect(write=False)
            if conn is None:
                return {"results": [], "total": 0}
            summaries = []
            for row, payload_ok in _list_rows(conn, kind):
                status = _effective_status(row["status"], row["method_version"], payload_ok)
                summary = _row_summary(row, status=status)
                if not _matches_query(summary, str(query).lower() if query else None):
                    continue
                if not _matches_variable(summary.get("variables"), variable):
                    continue
                summaries.append(summary)
            total = len(summaries)
            return {"results": summaries[offset:offset + limit], "total": total}
        except (sqlite3.Error, OSError, ValueError) as error:
            try:
                sys.stderr.write("result_store: list failed: %s\n" % error)
            except Exception:  # noqa: BLE001
                pass
            return {"results": [], "total": 0, "error": str(error)}
        finally:
            if conn is not None:
                conn.close()


def get_result(result_id):
    """Full stored record, or ``None``; unreadable payload marks ``damaged``."""
    if not isinstance(result_id, str) or not result_id.strip():
        return None
    wanted = result_id.strip()
    with _LOCK:
        conn = None
        try:
            conn = _connect(write=False)
            if conn is None:
                return None
            row = conn.execute(
                "SELECT %s FROM results WHERE id=? OR result_key=?" % _RECORD_COLUMNS,
                (wanted, wanted)).fetchone()
            if row is None:
                return None
            record = _record_from_row(row)
            if record["status"] == "damaged" and row["status"] != "damaged":
                _mark_damaged(conn, row["id"])
            return record
        except (sqlite3.Error, OSError, ValueError):
            try:
                sys.stderr.write("result_store: could not read saved result\n")
            except Exception:  # noqa: BLE001
                pass
            return None
        finally:
            if conn is not None:
                conn.close()


def _mark_damaged(conn, result_id):
    """Record the damage once so listings stay honest without re-parsing."""
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("UPDATE results SET status='damaged' WHERE id=?", (result_id,))
            conn.execute("COMMIT")
        except Exception:
            _rollback(conn)
    except sqlite3.Error:
        pass


def find_saved(result, spec=None):
    """Locate the record for a just-finished in-memory result.

    The persistence wrapper commits before the job reports ``complete``, so a
    tab that closed after the run can still find its record here by identity
    (canonical key first, then area ids + variable ids + window + kind).
    """
    if not isinstance(result, dict):
        return None
    if isinstance(spec, dict):
        try:
            record = get_result(canonical_key(spec, result)[:24])
        except Exception:  # noqa: BLE001 - a failed lookup is simply a miss
            record = None
        if record is not None:
            return record
    spec = spec if isinstance(spec, dict) else {}
    areas = _areas(spec, result)
    variables = _measurements(spec, result)
    window = _window(spec, result)
    wanted_kind = _kind(spec, result)
    area_ids = {a["id"] for a in areas}
    variable_ids = {v["id"] for v in variables}
    for summary in list_results(limit=MAX_LIST_LIMIT).get("results") or []:
        if summary.get("kind") != wanted_kind:
            continue
        saved_window = summary.get("window") or {}
        if (_as_int(saved_window.get("start")) != window["start"] or
                _as_int(saved_window.get("end")) != window["end"]):
            continue
        if not area_ids.issubset({a.get("id") for a in summary.get("areas") or []}):
            continue
        if not variable_ids.issubset({v.get("id") for v in summary.get("variables") or []}):
            continue
        return get_result(summary["id"])
    return None


# --------------------------------------------------------------------------
# map index
# --------------------------------------------------------------------------
def _verdict(overall, unit):
    overall = overall if isinstance(overall, dict) else {}
    ok = bool(overall.get("ok"))
    verdict = {
        "ok": ok,
        "per_decade": overall.get("per_decade"),
        "unit": unit,
        "direction": overall.get("direction"),
        "significant": overall.get("significant"),
        "p_value": overall.get("p"),
        "method": ("Mann-Kendall (AR(1)-corrected) with Theil-Sen slope"
                   if ok else None),
        "reason": None if ok else (overall.get("reason") or "insufficient data"),
    }
    return verdict


def _series_blocks(payload, area_role):
    if area_role == "B":
        compare = payload.get("compare") if isinstance(payload.get("compare"), dict) else {}
        blocks = compare.get("series")
    else:
        blocks = payload.get("series")
    return [b for b in (blocks or []) if isinstance(b, dict)]


def _role_area(payload, areas, role):
    if role == "B":
        compare = payload.get("compare") if isinstance(payload.get("compare"), dict) else {}
        meta = compare.get("region") if isinstance(compare.get("region"), dict) else {}
    else:
        meta = payload.get("region") if isinstance(payload.get("region"), dict) else {}
    stored = next((a for a in areas if isinstance(a, dict) and a.get("role") == role), None)
    area_id = meta.get("id") or (stored or {}).get("id")
    if not area_id:
        return None
    return {
        "id": str(area_id),
        "name": str(meta.get("name") or (stored or {}).get("name") or area_id),
        "level": str(meta.get("level") or (stored or {}).get("level")
                     or _level_from_id(area_id)),
    }


def _cells_for_record(summary, payload, variable, level):
    cells = []
    needle = str(variable).lower()
    stored_areas = summary.get("areas") or []
    for role in ("A", "B"):
        blocks = _series_blocks(payload, role)
        if not blocks:
            continue
        area = _role_area(payload, stored_areas, role)
        if not area:
            continue
        if level and str(area["level"]) != str(level):
            continue
        matched = None
        for block in blocks:
            meta = block.get("variable") if isinstance(block.get("variable"), dict) else {}
            if str(meta.get("id", "")).lower() == needle or str(meta.get("name", "")).lower() == needle:
                matched = block
                break
        if matched is None:
            continue
        variables = []
        for block in blocks:
            meta = block.get("variable") if isinstance(block.get("variable"), dict) else {}
            if not meta.get("id"):
                continue
            variables.append({"id": str(meta["id"]),
                              "name": str(meta.get("name") or meta["id"]),
                              "unit": meta.get("unit")})
        matched_meta = matched.get("variable") if isinstance(matched.get("variable"), dict) else {}
        variables.sort(key=lambda item: item["id"] != str(matched_meta.get("id")))
        cells.append({
            "result_id": summary["id"],
            "area_id": area["id"],
            "area_name": area["name"],
            "level": area["level"],
            "variables": variables,
            "window": summary.get("window") or {},
            "verdict": _verdict(matched.get("overall"), matched_meta.get("unit")),
            "saved_at": summary.get("created_at"),
            "status": summary.get("status"),
        })
    return cells


def map_index(*, variable, start, end, level=None, limit=DEFAULT_MAP_LIMIT):
    """Area-verdict cells for one measurement and one exact saved window.

    Only records whose stored window start/end equal the query populate
    ``cells``; other saved windows for the same variable are returned under
    ``alternatives`` so the app can offer them instead of pretending they are
    the same science.  ``exact`` is false when no cell matches.
    """
    limit = _clamp(limit, 1, MAX_MAP_LIMIT, DEFAULT_MAP_LIMIT)
    start_year = _as_int(start)
    end_year = _as_int(end)
    needle = str(variable or "").strip()
    with _LOCK:
        conn = None
        try:
            conn = _connect(write=False)
            if conn is None:
                return {"cells": [], "window": {"start": start_year, "end": end_year},
                        "exact": False, "alternatives": []}
            statement = ("SELECT %s, payload FROM results WHERE kind IN "
                         "('analysis','compare') ORDER BY created_at DESC, id" % _SUMMARY_COLUMNS)
            rows = conn.execute(statement).fetchall()
        except (sqlite3.Error, OSError) as error:
            try:
                sys.stderr.write("result_store: map index failed: %s\n" % error)
            except Exception:  # noqa: BLE001
                pass
            return {"cells": [], "window": {"start": start_year, "end": end_year},
                    "exact": False, "alternatives": [], "error": str(error)}
        finally:
            if conn is not None:
                conn.close()

    cells = []
    alternatives = []
    window = {"start": start_year, "end": end_year}
    for row in rows:
        payload_ok = _payload_valid(row["payload"])
        status = _effective_status(row["status"], row["method_version"], payload_ok)
        if status == "damaged":
            continue
        summary = _row_summary(row, status=status)
        if not _matches_variable(summary.get("variables"), needle):
            continue
        saved_window = summary.get("window") or {}
        matches_window = (_as_int(saved_window.get("start")) == start_year and
                          _as_int(saved_window.get("end")) == end_year)
        if not matches_window:
            if len(alternatives) < limit:
                alternatives.append({
                    "result_id": summary["id"],
                    "title": summary["title"],
                    "window": saved_window,
                    "saved_at": summary.get("created_at"),
                    "status": status,
                })
            continue
        if status != "current":
            if len(alternatives) < limit:
                alternatives.append({
                    "result_id": summary["id"],
                    "title": summary["title"],
                    "window": saved_window,
                    "saved_at": summary.get("created_at"),
                    "status": status,
                })
            continue
        payload = _loads(row["payload"])
        if not isinstance(payload, dict):
            continue
        for cell in _cells_for_record(summary, payload, needle, level):
            if len(cells) >= limit:
                break
            cells.append(cell)
        if window.get("first_month") is None and saved_window.get("first_month"):
            window["first_month"] = saved_window.get("first_month")
            window["last_month"] = saved_window.get("last_month")
    return {"cells": cells, "window": window, "exact": bool(cells),
            "alternatives": alternatives}


# --------------------------------------------------------------------------
# storage stats
# --------------------------------------------------------------------------
def storage_stats():
    """Honest disk usage and row counts; never evicts or deletes anything."""
    path = _db_path()
    stats = {"path": _display_path(), "count": 0, "bytes": 0,
             "kinds": {}, "oldest": None, "newest": None}
    for suffix in ("", "-wal", "-shm"):
        try:
            stats["bytes"] += os.path.getsize(path + suffix)
        except OSError:
            continue
    with _LOCK:
        conn = None
        try:
            conn = _connect(write=False)
            if conn is None:
                return stats
            stats["count"] = conn.execute("SELECT COUNT(*) FROM results").fetchone()[0]
            for row in conn.execute("SELECT kind, COUNT(*) AS n FROM results GROUP BY kind"):
                stats["kinds"][row["kind"]] = row["n"]
            oldest = conn.execute("SELECT MIN(created_at) FROM results").fetchone()[0]
            newest = conn.execute("SELECT MAX(created_at) FROM results").fetchone()[0]
            stats["oldest"] = oldest
            stats["newest"] = newest
        except (sqlite3.Error, OSError) as error:
            stats["error"] = str(error)
        finally:
            if conn is not None:
                conn.close()
    return stats


# --------------------------------------------------------------------------
# validation / import of historical evidence
# --------------------------------------------------------------------------
def validate_record(record):
    """Schema/version validation for an explicitly imported JSON record."""
    errors = []
    if not isinstance(record, dict):
        return False, ["record must be a JSON object"]

    schema_version = record.get("schema_version")
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        errors.append("schema_version must be an integer")
    elif schema_version > CURRENT_SCHEMA_VERSION:
        errors.append("unknown schema_version %d; this build understands up to %d"
                      % (schema_version, CURRENT_SCHEMA_VERSION))
    elif schema_version < 1:
        errors.append("schema_version must be >= 1")

    if record.get("kind") not in KINDS:
        errors.append("kind must be one of: " + ", ".join(KINDS))
    if not isinstance(record.get("operation"), str) or not record.get("operation", "").strip():
        errors.append("operation must be a non-empty string")
    if not isinstance(record.get("title"), str) or not record.get("title", "").strip():
        errors.append("title must be a non-empty string")
    if _coerce_iso(record.get("created_at")) is None:
        errors.append("created_at must be an ISO-8601 timestamp")
    if not isinstance(record.get("method_version"), str) or not record.get("method_version", "").strip():
        errors.append("method_version must be a non-empty string")
    if not isinstance(record.get("provider_family"), str) or not record.get("provider_family", "").strip():
        errors.append("provider_family must be a non-empty string")

    areas = record.get("areas")
    if not isinstance(areas, list):
        errors.append("areas must be a list")
    else:
        for index, area in enumerate(areas):
            if not isinstance(area, dict):
                errors.append("areas[%d] must be an object" % index)
                continue
            if area.get("role") not in {"A", "B", "layer"}:
                errors.append("areas[%d].role must be A, B or layer" % index)
            if not area.get("id"):
                errors.append("areas[%d].id is required" % index)
            if not area.get("level"):
                errors.append("areas[%d].level is required" % index)

    variables = record.get("variables")
    if not isinstance(variables, list):
        errors.append("variables must be a list")
    else:
        for index, variable in enumerate(variables):
            if not isinstance(variable, dict) or not variable.get("id"):
                errors.append("variables[%d] must be an object with an id" % index)

    window = record.get("window")
    if not isinstance(window, dict):
        errors.append("window must be an object")
    else:
        for key in ("start", "end"):
            if not isinstance(window.get(key), int) or isinstance(window.get(key), bool):
                errors.append("window.%s must be an integer year" % key)

    if record.get("routes") is not None and not isinstance(record.get("routes"), dict):
        errors.append("routes must be an object")
    if record.get("provenance") is not None and not isinstance(record.get("provenance"), list):
        errors.append("provenance must be a list")

    payload = record.get("payload")
    if isinstance(payload, str):
        if _loads(payload) is None:
            errors.append("payload must be a JSON object (the stored string is invalid)")
    elif not isinstance(payload, dict):
        errors.append("payload must be the completed result object")

    return (not errors), errors


def _spec_from_record(record):
    """Reconstruct the minimum request identity an imported record describes."""
    window = record.get("window") if isinstance(record.get("window"), dict) else {}
    areas = [a for a in record.get("areas") or [] if isinstance(a, dict)]
    primary = next((a for a in areas if a.get("role") == "A"), None)
    compared = next((a for a in areas if a.get("role") == "B"), None)
    spec = {
        "operation": record.get("operation") or "analyze",
        "method_version": record.get("method_version"),
        "provider": record.get("provider_family"),
        "start": window.get("start"),
        "end": window.get("end"),
        "variables": [str(v.get("id")) for v in record.get("variables") or []
                      if isinstance(v, dict) and v.get("id")],
        "routes": record.get("routes") or {},
    }
    if primary:
        spec["region"] = primary.get("id")
        if isinstance(primary.get("geometry"), dict):
            spec["custom_areas"] = [{"id": primary.get("id"),
                                     "type": "Feature",
                                     "geometry": primary.get("geometry"),
                                     "properties": {"name": primary.get("name"),
                                                    "level": primary.get("level")}}]
    if compared:
        spec["compare_region"] = compared.get("id")
    return spec


def import_record(record):
    """Validate and store externally supplied historical evidence as legacy."""
    with _LOCK:
        try:
            ok, errors = validate_record(record)
            if not ok:
                return {"ok": False, "saved": False, "error": "Invalid historical record",
                        "errors": errors, "id": None, "key": None}
            payload = record.get("payload")
            if isinstance(payload, str):
                payload = _loads(payload)
            result = dict(payload)
            spec = _spec_from_record(record)
            method_version = record.get("method_version")
            status = "current" if method_version == CURRENT_METHOD_VERSION else "legacy"
            row = _build_row(spec, result, kind=record.get("kind"), status=status,
                             record=record)
            row["operation"] = record.get("operation")
            row["title"] = record.get("title")
            row["provider_family"] = record.get("provider_family") or row["provider_family"]
            row["method_version"] = method_version
            # Keep the imported area identity verbatim: historical evidence must
            # round-trip exactly, even if its boundary metadata is old.
            row["areas"] = sanitize(record.get("areas") or [])
            row["variables"] = sanitize(record.get("variables") or [])
            row["window"] = sanitize(record.get("window") or row["window"])
            if isinstance(record.get("routes"), dict):
                row["routes"] = sanitize(record["routes"])
            if isinstance(record.get("provenance"), list):
                row["provenance"] = sanitize(record["provenance"])
            key = record.get("key")
            if isinstance(key, str) and re.fullmatch(r"[0-9a-f]{64}", key.strip()):
                row["key"] = key.strip()
                row["id"] = row["key"][:24]
            row["size_bytes"] = len(row["payload"].encode("utf-8"))
            summary = _store(row)
            summary["imported"] = True
            return summary
        except (sqlite3.Error, OSError, ValueError, TypeError) as error:
            return _failure(error)
        except Exception as error:  # noqa: BLE001 - storage must never raise
            return _failure(error)
