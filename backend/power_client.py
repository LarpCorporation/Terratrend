"""NASA POWER data client with a robust on-disk cache."""
import datetime
import json
import math
import random
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

BASE = "https://power.larc.nasa.gov/api/temporal/monthly/point"
UA = {"User-Agent": "Mozilla/5.0 (TerraTrend SpaceApps demo)"}
CACHE_DIR = Path(__file__).resolve().parent / "cache"
CACHE_TTL = 30 * 24 * 3600  # 30 days
MAX_WORKERS = 6
MAX_RETRIES = 4


def _cache_path(lon, lat, param, start, end):
    name = f"P{param}_S{start}_E{end}_x{lon:.2f}_y{lat:.2f}.json"
    return CACHE_DIR / name


def _fetch_one(lon, lat, param, start, end):
    """Fetch monthly series for one point. Returns dict[YYYYMM -> value]."""
    cpath = _cache_path(lon, lat, param, start, end)
    if cpath.exists():
        try:
            blob = json.loads(cpath.read_text())
            if time.time() - blob.get("t", 0) < CACHE_TTL:
                return blob["data"]
        except Exception:
            pass
    url = (f"{BASE}?community=AG&longitude={lon:.4f}&latitude={lat:.4f}"
           f"&start={start}&end={end}&parameters={param}&format=JSON")
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            # small jitter keeps bursts from tripping POWER's rate limiter
            time.sleep(random.random() * 0.12 * (attempt + 1))
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.loads(r.read())
            p = d.get("properties", {}).get("parameter", {})
            series = p.get(param, {})
            if not series:
                msgs = d.get("messages", [])
                raise RuntimeError(f"empty series {msgs[:2]}")
            cpath.parent.mkdir(parents=True, exist_ok=True)
            cpath.write_text(json.dumps({"t": time.time(), "data": series}))
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
            results.setdefault(lon, {})[lat] = {k: _clean(v) for k, v in series.items()}

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
