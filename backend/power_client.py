"""NASA POWER data client with a robust on-disk cache."""
import datetime
import json
import math
import random
import time
import urllib.request
import urllib.error
import threading
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

BASE = "https://power.larc.nasa.gov/api/temporal/monthly/point"
UA = {"User-Agent": "Mozilla/5.0 (TerraTrend SpaceApps demo)"}
CACHE_DIR = Path(__file__).resolve().parent / "cache"
CACHE_TTL = 30 * 24 * 3600  # 30 days
MAX_WORKERS = 6
MAX_RETRIES = 4

_CACHE_INDEX = None
_CACHE_LOCK = threading.RLock()


def _get_cache_index():
    """Index cached files by (param, lon, lat), keeping each file's own period.

    The period is part of the key: a cached 2005-2024 file must never answer a
    2015-2024 request, because it would silently return 20 years of data for a
    10-year question (and the caller would report the wrong trend with full
    confidence).
    """
    global _CACHE_INDEX
    with _CACHE_LOCK:
        if _CACHE_INDEX is None:
            idx = {}
            for p in CACHE_DIR.glob("*.json"):
                match = re.fullmatch(r"P(.+)_S(\d+)_E(\d+)_x(-?[\d.]+)_y(-?[\d.]+)\.json", p.name)
                if match:
                    param, start, end, lon, lat = match.groups()
                    idx.setdefault((param, lon, lat), []).append((int(start), int(end), p))
            _CACHE_INDEX = idx
    return _CACHE_INDEX


def _slice_months(data, start, end):
    """Restrict a YYYYMM-keyed series to the requested years."""
    lo, hi = start * 100, end * 100 + 12
    return {k: v for k, v in data.items() if lo <= int(k) <= hi}


def _cache_path(lon, lat, param, start, end):
    name = f"P{param}_S{start}_E{end}_x{lon:.2f}_y{lat:.2f}.json"
    return CACHE_DIR / name


def _fetch_one(lon, lat, param, start, end):
    """Fetch monthly series for one point. Returns dict[YYYYMM -> value].

    The returned series is guaranteed to lie inside [start, end]. A cache hit
    is only used when the cached file fully covers the request.
    """
    cpath = _cache_path(lon, lat, param, start, end)
    if cpath.exists():
        try:
            blob = json.loads(cpath.read_text())
            if time.time() - blob.get("t", 0) < CACHE_TTL:
                return blob["data"]
        except Exception:
            pass

    # Reuse an existing cached file ONLY when it fully covers the requested
    # period. A partial cover would drop whole years and bias the trend.
    idx = _get_cache_index()
    matches = idx.get((param, f"{lon:.2f}", f"{lat:.2f}"), [])
    best = None
    for cstart, cend, path in matches:
        if cstart <= start and cend >= end:
            if best is None or (cend - cstart) < (best[1] - best[0]):
                best = (cstart, cend, path)
    if best is not None:
        try:
            blob = json.loads(best[2].read_text())
            data = blob.get("data", {})
            sliced = _slice_months(data, start, end)
            if sliced:
                return sliced
        except Exception:
            pass

    url = (f"{BASE}?community=AG&longitude={lon:.4f}&latitude={lat:.4f}"
           f"&start={start}&end={end}&parameters={param}&format=JSON")
    last_err = None
    for attempt in range(2):
        try:
            # small jitter keeps bursts from tripping POWER's rate limiter
            time.sleep(random.random() * 0.12 * (attempt + 1))
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=10) as r:
                d = json.loads(r.read())
            p = d.get("properties", {}).get("parameter", {})
            series = p.get(param, {})
            if not series:
                msgs = d.get("messages", [])
                raise RuntimeError(f"empty series {msgs[:2]}")
            cpath.parent.mkdir(parents=True, exist_ok=True)
            cpath.write_text(json.dumps({"t": time.time(), "data": series}))
            # a new file changes what the index can serve
            global _CACHE_INDEX
            with _CACHE_LOCK:
                _CACHE_INDEX = None
            return series
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(2 + attempt * 4)
    raise RuntimeError(f"POWER fetch failed lon={lon} lat={lat} {param}: {last_err}")


def _clean(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or f < -900:
        return None
    return f


# POWER returns radiation in MJ/m^2/day. The catalog advertises these
# variables in the units scientists actually quote them in, so convert once at
# ingest rather than leaving every downstream "how much is it changing" wrong
# by a constant factor.
UNIT_SCALE = {
    "ALLSKY_SFC_LW_DWN": 1e6 / 86400.0,   # MJ/m^2/day -> W/m^2
    "ALLSKY_SFC_SW_DNI": 1.0 / 3.6,       # MJ/m^2/day -> kWh/m^2/day
}


def _scale(param, value):
    factor = UNIT_SCALE.get(param)
    if factor is None or value is None:
        return value
    return value * factor


def fetch_grid(param, bbox, start, end, nx=5, ny=5):
    """Fetch monthly time series on an (nx x ny) grid inside bbox.

    Returns {lon: {lat: {YYYYMM: value}}}. Raises on total failure.
    """
    lon0, lat0, lon1, lat1 = bbox
    xs = [lon0 + (lon1 - lon0) * i / (nx - 1) for i in range(nx)]
    ys = [lat0 + (lat1 - lat0) * j / (ny - 1) for j in range(ny)]
    jobs = [(round(x, 2), round(y, 2)) for x in xs for y in ys]
    results = {}

    def work(pt):
        lon, lat = pt
        return pt, _fetch_one(lon, lat, param, start, end)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = [ex.submit(work, pt) for pt in jobs]
        for fut in as_completed(futs):
            pt, series = fut.result()
            lon, lat = pt
            results.setdefault(lon, {})[lat] = {
                k: _scale(param, _clean(v)) for k, v in series.items()
            }

    got = sum(1 for lo in results for la in results[lo]
              if any(v is not None for v in results[lo][la].values()))
    if got < nx * ny * 0.6:
        raise RuntimeError(f"only {got}/{nx*ny} grid points usable")
    return results


def prune_cache(max_age=CACHE_TTL):
    now = time.time()
    for f in CACHE_DIR.glob("*.json"):
        try:
            if now - f.stat().st_mtime > max_age:
                f.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Availability probe
#
# POWER publishes monthly data with a lag of roughly 1-2 months, while its
# daily product runs within about a day. This probe asks POWER directly (no
# cache, so the answer is never stale) and the result is memoised for 6 hours.
# ---------------------------------------------------------------------------
_AVAIL = {"ts": 0.0, "data": None}
AVAIL_TTL = 6 * 3600
PROBE_POINT = (0.0, 14.0)  # Sahel: a long, continuous record


def _raw_fetch(temporal, lon, lat, param, start, end):
    url = (f"https://power.larc.nasa.gov/api/temporal/{temporal}/point"
           f"?community=AG&longitude={lon:.4f}&latitude={lat:.4f}"
           f"&start={start}&end={end}&parameters={param}&format=JSON")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read())
    return d.get("properties", {}).get("parameter", {}).get(param, {})


def probe_availability(force=False):
    """Report the newest month/day POWER can actually serve.

    Never raises: on failure it returns ok=False plus the last good answer.
    """
    now = time.time()
    if not force and _AVAIL["data"] and now - _AVAIL["ts"] < AVAIL_TTL:
        return _AVAIL["data"]

    today = datetime.date.today()
    year = today.year
    result = {"ok": False, "max_year": year}

    try:
        monthly = _raw_fetch("monthly", PROBE_POINT[0], PROBE_POINT[1],
                             "T2M", year - 1, year)
        valid_m = sorted(
            k for k, v in monthly.items()
            if len(k) == 6 and k[4:] != "13" and _clean(v) is not None
        )
        latest_month = valid_m[-1] if valid_m else None

        recent = today - datetime.timedelta(days=140)
        daily = _raw_fetch("daily", PROBE_POINT[0], PROBE_POINT[1],
                           "T2M", recent.strftime("%Y%m%d"),
                           today.strftime("%Y%m%d"))
        valid_d = sorted(k for k, v in daily.items()
                         if _clean(v) is not None)
        latest_day = valid_d[-1] if valid_d else None

        result = {
            "ok": True,
            "max_year": year,
            "latest_month": latest_month,
            "latest_month_label": (
                f"{latest_month[:4]}-{latest_month[4:]}" if latest_month else None
            ),
            "latest_day": latest_day,
            "latest_day_label": (
                f"{latest_day[:4]}-{latest_day[4:6]}-{latest_day[6:]}"
                if latest_day else None
            ),
            "probed_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "source": "NASA POWER",
        }
    except Exception as e:  # noqa: BLE001
        result = {"ok": False, "max_year": year, "error": str(e)}
        if _AVAIL["data"] and _AVAIL["data"].get("ok"):
            return _AVAIL["data"]  # serve the last good answer

    _AVAIL.update(ts=time.time(), data=result)
    return result
