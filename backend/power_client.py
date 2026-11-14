"""NASA POWER data client with a robust on-disk cache."""
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
