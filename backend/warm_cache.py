"""Pre-warm the on-disk cache for demo regions and variables.

Run once before judging so every demo click returns instantly:
    python warm_cache.py
"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, ".")

BASE = "http://127.0.0.1:8517/api/analyze"

# hero stories first, then the rest of the globe
JOBS = [
    ("PRECTOTCORR", "sahel"),
    ("T2M", "europe"),
    ("T2M", "madagascar"),
    ("T2M", "arctic"),
    ("T2M", "california"),
    ("PRECTOTCORR", "amazon"),
    ("T2M", "amazon"),
    ("T2M", "sahel"),
    ("T2M", "congo"),
    ("T2M", "arabia"),
    ("T2M", "china"),
    ("T2M", "brazil"),
    ("T2M", "bengal"),
    ("T2M", "australia"),
    ("T2M", "greenland"),
    ("T2M", "sahara"),
    ("T2M", "siberia"),
    ("T2M", "pacific"),
]


def main():
    ok, fail = 0, 0
    for var, region in JOBS:
        url = f"{BASE}?variables={var}&region={region}&start=2005&end=2024"
        t0 = time.time()
        try:
            with urllib.request.urlopen(url, timeout=600) as r:
                d = json.loads(r.read())
            o = d["series"][0]["overall"]
            print(f"  {var:14s} {region:12s} {time.time()-t0:6.1f}s "
                  f"{o.get('direction', '—'):8s} p={o.get('p', 1):.3f}")
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"  {var:14s} {region:12s} FAILED after "
                  f"{time.time()-t0:.0f}s: {e}")
            fail += 1
    print(f"\nwarmed {ok} jobs, {fail} failed")


if __name__ == "__main__":
    main()
