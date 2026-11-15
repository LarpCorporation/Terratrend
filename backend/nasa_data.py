"""Automatic native-grid MERRA-2 subsets from NASA GES DISC.

These are the collections exposed by the challenge's Giovanni resource, fetched
through NASA's current OPeNDAP service. No POWER fallback or synthetic values.
CMR discovery is public; observation downloads require an Earthdata bearer token.
"""
import datetime as dt
import hashlib
import io
import json
import math
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from pathlib import Path
from urllib.parse import quote, unquote, urlencode, urlparse

import numpy as np
import requests

import jobs
import spatial
import earthdata_credentials

CACHE = Path(__file__).resolve().parent / "cache" / "nasa"
VERSION = "merra2-native-v1"
PRODUCTS = {
    "M2TMNXSLV": "C1276812859-GES_DISC",
    "M2TMNXLND": "C1276812856-GES_DISC",
    "M2TMNXFLX": "C1276812868-GES_DISC",
}
# The full catalogue includes POWER-specific/derived fields. Only equivalent
# native measurements are enabled; monthly vector means are not wind speed,
# monthly maxima are not means of daily maxima, and absorbed flux is not DNI.
FIELDS = {
    "T2M": ("M2TMNXSLV", "T2M", "K", 1., -273.15),
    "TS": ("M2TMNXSLV", "TS", "K", 1., -273.15),
    "QV2M": ("M2TMNXSLV", "QV2M", "kg kg-1", 1000., 0.),
    "PS": ("M2TMNXSLV", "PS", "Pa", .001, 0.),
    "GWETROOT": ("M2TMNXLND", "GWETROOT", "1", 1., 0.),
    "GWETTOP": ("M2TMNXLND", "GWETTOP", "1", 1., 0.),
    "EVLAND": ("M2TMNXLND", "EVLAND", "kg m-2 s-1", 86400., 0.),
    "PRECTOTCORR": ("M2TMNXFLX", "PRECTOTCORR", "kg m-2 s-1", 86400., 0.),
}
_TOKEN = ""
_LOCK = threading.RLock()
_NETCDF_LOCK = threading.Lock()  # The HDF5 library is not generally thread-safe.
_DOWNLOAD_LIMIT = threading.BoundedSemaphore(3)
_CACHE_LOCKS = [threading.Lock() for _ in range(32)]


class EarthdataRequired(ValueError):
    pass


def token():
    with _LOCK:
        return _TOKEN or os.environ.get("EARTHDATA_TOKEN", "").strip() or earthdata_credentials.load()


def status():
    import importlib.util
    return {"configured": bool(token()), **earthdata_credentials.status(), "reader_installed": importlib.util.find_spec("netCDF4") is not None,
            "variables": list(FIELDS), "resource": "Giovanni", "source": "NASA GES DISC / MERRA-2",
            "login_url": "https://urs.earthdata.nasa.gov/", "storage": "Desktop credential store or owner-only local configuration when remembered; otherwise session memory. EARTHDATA_TOKEN is also supported."}


def _request(url, bearer="", limit=24_000_000):
    """Bounded HTTPS requests; tokens never enter URLs, logs or disk caches."""
    allowed = {"cmr.earthdata.nasa.gov", "opendap.earthdata.nasa.gov"}
    with requests.Session() as session:
        # Prevent Requests from silently using unrelated ~/.netrc credentials.
        session.auth = lambda request: request
        for attempt in range(3):
            jobs.check_cancelled()
            if urlparse(url).scheme != "https" or urlparse(url).hostname not in allowed:
                raise ValueError("Unsupported NASA data-service destination")
            headers = {"User-Agent": "TerraTrend/1.0 (NASA Space Apps)", "Accept": "*/*"}
            if bearer and urlparse(url).hostname == "opendap.earthdata.nasa.gov":
                headers["Authorization"] = "Bearer " + bearer
            try:
                with _DOWNLOAD_LIMIT, session.get(url, headers=headers, timeout=(15, 75), stream=True, allow_redirects=False) as response:
                    location=response.headers.get("Location", "")
                    if response.status_code in {401, 403} or (300 <= response.status_code < 400 and ("urs.earthdata.nasa.gov" in location or urlparse(location).path.startswith("/login/urs"))):
                        raise EarthdataRequired("NASA requires a valid Earthdata token and GES DISC authorization. Open Data & Methods → Connect Earthdata; downloads then run automatically.")
                    if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                        delay = min(5., max(1., float(response.headers.get("Retry-After", 1))))
                    else:
                        if response.status_code != 200:
                            raise ValueError(f"NASA data service returned HTTP {response.status_code}. Retry later; observations were not replaced or invented.")
                        parts, size = [], 0
                        for part in response.iter_content(64_000):
                            jobs.check_cancelled(); size += len(part)
                            if size > limit: raise ValueError("NASA subset exceeds the download limit")
                            parts.append(part)
                        return b"".join(parts)
            except requests.RequestException as exc:
                if attempt == 2:
                    raise ValueError("Cannot reach NASA's data service. Check the server's internet connection and retry.") from exc
                delay = 1.
            time.sleep(delay)
    raise ValueError("NASA data service could not complete the download")


def granules(product, start, end):
    """Use real published month/revision metadata, never construct file names."""
    params = {"collection_concept_id": PRODUCTS[product], "page_size": 1000,
              "temporal": f"{start}-01-01T00:00:00Z,{end}-12-31T23:59:59Z", "sort_key": "start_date"}
    path = CACHE / "catalog" / f"{product}-{start}-{end}.json"
    try:
        stored = json.loads(path.read_text())
        if time.time()-stored["fetched"] < 86400: return stored["granules"]
    except (OSError, ValueError, KeyError): pass
    body = json.loads(_request("https://cmr.earthdata.nasa.gov/search/granules.json?"+urlencode(params), limit=8_000_000))
    entries = body["feed"]["entry"]
    by_month = {}
    for entry in entries:
        date = entry["time_start"][:7]; month = int(date.replace("-", ""))
        if not start*100 < month <= end*100+12: continue
        links = [link["href"] for link in entry.get("links", []) if urlparse(link.get("href", "")).hostname == "opendap.earthdata.nasa.gov" and "/granules/" in link["href"] and not link.get("inherited")]
        if not links: continue
        row = {"month": month, "id": entry["id"], "title": entry["title"], "updated": entry.get("updated", ""), "url": links[0]}
        # CMR can publish a reprocessed revision alongside the old granule.
        if month not in by_month or row["updated"] > by_month[month]["updated"]: by_month[month] = row
    rows = sorted(by_month.values(), key=lambda row: row["month"])
    if not rows: raise ValueError("NASA CMR lists no downloadable monthly granules for this variable and period.")
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, json.dumps({"fetched": time.time(), "granules": rows}).encode())
    return rows


def _atomic_write(path, content):
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
        temporary = Path(output.name); output.write(content)
    try: temporary.replace(path)
    finally: temporary.unlink(missing_ok=True)


def windows(cells):
    """Smallest circular longitude span, split at the native date line."""
    xs = sorted({int(round((lon+180)/.625)) % 576 for lon, _, _ in cells})
    ys = [int(round((lat+90)/.5)) for _, lat, _ in cells]
    if not xs: raise ValueError("The selected geometry has no native source cells")
    gaps = [(xs[(i+1) % len(xs)] + (576 if i == len(xs)-1 else 0) - x, i) for i, x in enumerate(xs)]
    _, cut = max(gaps)
    first, last = xs[(cut+1) % len(xs)], xs[cut]
    ranges = [(first, last)] if first <= last else [(first, 575), (0, last)]
    return [(min(ys), max(ys), lo, hi) for lo, hi in ranges]


def subset_url(granule, field, window):
    y0, y1, x0, x1 = window
    parsed = urlparse(granule["url"])
    if parsed.hostname != "opendap.earthdata.nasa.gov" or not re.fullmatch(r"[A-Z][A-Z0-9_]+", field):
        raise ValueError("Invalid NASA subset identity")
    # NASA's documented Copy encoded Data URL encodes the colon-bearing
    # granule identifier twice for the DAP4 download handler.
    prefix, identifier = parsed.path.split("/granules/", 1)
    base = "https://opendap.earthdata.nasa.gov"+prefix+"/granules/"+quote(quote(unquote(identifier), safe=""), safe="")
    constraint = f"/{field}[0:1:0][{y0}:1:{y1}][{x0}:1:{x1}];/lat[{y0}:1:{y1}];/lon[{x0}:1:{x1}]"
    return base+".dap.nc4?"+urlencode({"dap4.ce": constraint})


def decode_subset(raw, variable, window):
    try: from netCDF4 import Dataset
    except ImportError as exc: raise ValueError("NASA NetCDF reader is missing. Start TerraTrend with ./start.sh to install its data dependencies.") from exc
    if not (raw.startswith(b"\x89HDF") or raw.startswith(b"CDF")):
        raise ValueError("NASA returned a login/error page instead of a scientific NetCDF subset")
    _, field, expected, factor, offset = FIELDS[variable]
    y0, y1, x0, x1 = window
    with _NETCDF_LOCK, Dataset("subset.nc4", memory=raw) as data:
        if field not in data.variables or "lon" not in data.variables or "lat" not in data.variables:
            raise ValueError("NASA subset lacks the requested field or coordinate axes")
        value = data.variables[field]
        unit = str(getattr(value, "units", "")).strip().replace("**", "").replace("^", "")
        unit = " ".join(unit.split())
        aliases = {"kg kg-1": {"kg kg-1", "kg/kg"}, "kg m-2 s-1": {"kg m-2 s-1", "kg/m2/s"}, "1": {"1", "dimensionless"}}
        if unit not in aliases.get(expected, {expected}):
            raise ValueError(f"NASA {field} units differ from the verified mapping; refusing an unverified conversion")
        lons, lats = np.asarray(data.variables["lon"][:]), np.asarray(data.variables["lat"][:])
        if lons.shape != (x1-x0+1,) or lats.shape != (y1-y0+1,) or not np.allclose(lons, -180+np.arange(x0, x1+1)*.625, atol=1e-5) or not np.allclose(lats, -90+np.arange(y0, y1+1)*.5, atol=1e-5):
            raise ValueError("NASA coordinates do not match the native 0.625° × 0.5° grid")
        array = np.ma.asarray(value[:], dtype=float)
        if array.shape != (1, y1-y0+1, x1-x0+1): raise ValueError("NASA subset has an unexpected time/grid shape")
        values = np.asarray(np.ma.filled(array[0], np.nan))*factor+offset
        values[~np.isfinite(values)] = np.nan
        return values


def download_month(granule, variable, window, bearer):
    product, field, *_ = FIELDS[variable]
    key = hashlib.sha256(json.dumps([VERSION, variable, granule["id"], granule["updated"], window]).encode()).hexdigest()
    path = CACHE / "subsets" / (key+".nc4")
    with _CACHE_LOCKS[int(key[:4], 16) % len(_CACHE_LOCKS)]:
        jobs.check_cancelled()
        if path.exists():
            try: return decode_subset(path.read_bytes(), variable, window), True
            except (OSError, ValueError): path.unlink(missing_ok=True)
        raw = _request(subset_url(granule, field, window), bearer)
        values = decode_subset(raw, variable, window)
        _atomic_write(path, raw)
        return values, False


def connect(bearer, remember=True):
    global _TOKEN
    bearer = str(bearer).strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{20,4096}", bearer): raise ValueError("Paste the Earthdata-generated token, without 'Bearer' or quotation marks")
    rows = granules("M2TMNXSLV", 2024, 2024)
    # A real one-cell observation verifies credentials, authorization and parser.
    raw = _request(subset_url(rows[0], "T2M", (180, 180, 288, 288)), bearer)
    decode_subset(raw, "T2M", (180, 180, 288, 288))
    if remember:earthdata_credentials.remember(bearer)
    else:earthdata_credentials.forget()
    with _LOCK: _TOKEN = bearer
    return {**status(), "verified": True, "message": "Connected. Analyze now downloads and caches the required NASA grid subsets automatically."}


def disconnect():
    global _TOKEN
    earthdata_credentials.forget()
    with _LOCK: _TOKEN = ""
    return status()


def fetch_region(variable, feature, start, end):
    if variable not in FIELDS:
        raise ValueError(f"{variable} has no verified automatic mapping yet. Supported NASA measurements: air/surface temperature, specific humidity, pressure, root/surface soil moisture, land evaporation and precipitation.")
    bearer = token()
    if not bearer: raise EarthdataRequired("Connect your Earthdata account in Data & Methods once. TerraTrend then fetches the observations automatically; no CSV upload is needed.")
    jobs.progress(0, 1, "Preparing native NASA cells for the exact selected boundary")
    planned = spatial.cells(feature["id"], .625, .5)
    product, field, *_ = FIELDS[variable]
    rows = granules(product, start, end)
    bounds = windows(planned)
    grid = spatial.Grid(weights={(lon, lat): weight for lon, lat, weight in planned})
    grid.expected_weight = sum(grid.weights.values())
    # Store only cells intersecting the polygon, including tiny islands and holes.
    indices = []
    for window in bounds:
        y0, y1, x0, x1 = window
        indices.append([(lon, lat, int(round((lat+90)/.5))-y0, int(round((lon+180)/.625)) % 576-x0)
                        for lon, lat, _ in planned if x0 <= int(round((lon+180)/.625)) % 576 <= x1])
    total = len(rows)*len(bounds); completed = cached = 0
    pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="nasa-subset")
    pending = {}
    try:
        # Submit at most one small batch at a time, keeping cancellation bounded.
        tasks = [(row, i, window) for row in rows for i, window in enumerate(bounds)]
        for offset in range(0, len(tasks), 3):
            jobs.check_cancelled(); pending = {}
            for row, i, window in tasks[offset:offset+3]:
                future = pool.submit(copy_context().run, download_month, row, variable, window, bearer)
                pending[future] = (row, i)
            for future in as_completed(pending):
                jobs.check_cancelled(); row, index = pending[future]; values, hit = future.result()
                for lon, lat, iy, ix in indices[index]:
                    number = float(values[iy, ix])
                    if math.isfinite(number): grid.setdefault(lon, {}).setdefault(lat, {})[row["month"]] = number
                completed += 1; cached += int(hit)
                jobs.progress(completed, total, f"NASA {field}: {completed}/{total} monthly subsets ready ({cached} from cache)")
    finally:
        for future in pending: future.cancel()
        pool.shutdown(wait=False, cancel_futures=True)
    available = sum(w for (lon, lat), w in grid.weights.items() if grid.get(lon, {}).get(lat))
    months = sorted({month for col in grid.values() for series in col.values() for month in series})
    grid.provenance = {"provider": "nasa-merra2", "source": "NASA GES DISC / MERRA-2", "resource": "Giovanni",
        "dataset": product, "collection_version": "5.12.4", "field": field, "policy": "challenge_resource",
        "access": "Automatic CMR discovery → authenticated OPeNDAP native-grid subset → local cache",
        "citation": "https://disc.gsfc.nasa.gov/datasets/"+product+"_5.12.4/summary",
        "dlon": .625, "dlat": .5, "geometry_version": feature["geometry_version"],
        "aggregation": "Native-cell polygon overlap × cos(latitude); at least 80% selected area each month",
        "expected_cells": len(planned), "available_cells": sum(len(col) for col in grid.values()),
        "available_area_fraction": min(1., available/grid.expected_weight) if grid.expected_weight else 0.,
        "first_observed_month": months[0] if months else None, "last_observed_month": months[-1] if months else None,
        "published_months": len(rows), "requested_months": 12*(end-start+1), "cached_subsets": cached,
        "retrieved_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "quality": "Provider fill values/masks excluded; model reanalysis, not a direct measurement at every location",
        "granules": [{k: row[k] for k in ("id", "month", "title", "updated")} for row in rows]}
    return grid
