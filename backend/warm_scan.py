"""Pre-warm a full 16-variable scan for demo regions.

The scan grid is identical to the analysis grid, so warming these also makes
every single-variable analysis instant.

    python warm_scan.py sahel europe madagascar
"""
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8517/api/scan"
START, END = 2005, 2026


def main(regions):
    total_ok = 0
    for region in regions:
        t0 = time.time()
        url = f"{BASE}?region={region}&start={START}&end={END}"
        try:
            with urllib.request.urlopen(url, timeout=3600) as r:
                d = json.loads(r.read())
            s = d["summary"]
            nodata = [x["name"] for x in d["scanned"] if not x.get("ok")]
            print(f"{region:14s} {time.time()-t0:6.1f}s  "
                  f"sig={s['significant']}/{s['analysable']}  "
                  f"nodata={len(nodata)}", flush=True)
            if nodata:
                print("   failed:", ", ".join(nodata[:6]), flush=True)
            total_ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"{region:14s} FAILED after {time.time()-t0:.0f}s: {e}",
                  flush=True)
        time.sleep(3)
    print(f"\nwarmed {total_ok}/{len(regions)} regions")


if __name__ == "__main__":
    regions = sys.argv[1:] or ["sahel", "europe", "madagascar"]
    main(regions)
