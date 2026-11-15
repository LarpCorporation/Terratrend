"""Pre-warm the event-network series so the Events tab opens instantly.

Each event's first visit downloads and caches its NASA series; without this,
a live demo waits on the network. Run it once before judging, with the server
already up and Earthdata connected:

    python backend/warm_events.py

Events are warmed in story order. Paths that legitimately have no source (the
NSIDC sea-ice extent) report that and are not retried.
"""
import json
import sys
import time
import urllib.request
from datetime import date

BASE = "http://127.0.0.1:8517/api/events"
END_YEAR = date.today().year

# Hero story first, then the rest of the catalogue.
ORDER = [
    "el_nino_2023_2024",
    "west_africa_ghana_1982_83",
    "amazon_drought_2023",
    "southern_africa_drought_2023_2024",
    "developing_el_nino_2026_2027",
    "arctic_sea_ice_minimum_2012",
]

STATUS_LABEL = {
    "verified_from_source": "verified",
    "awaiting_source": "awaiting",
    "unavailable": "not connected",
    "insufficient_data": "thin",
}


def warm(event_id):
    """Fetch one event and report the state of each pathway."""
    t0 = time.time()
    with urllib.request.urlopen(f"{BASE}/{event_id}", timeout=1800) as r:
        data = json.loads(r.read())
    rows = []
    for edge in data.get("edges", []):
        v = edge.get("verification", {})
        label = STATUS_LABEL.get(v.get("status"), v.get("status", "?"))
        detail = ""
        if v.get("status") == "verified_from_source":
            detail = (f"r={v.get('r_value')} lag={v.get('lag_months_observed')}m "
                      f"p={v.get('p_value_neff')} fdr={v.get('p_value_fdr')} "
                      f"n={v.get('sample_months')}")
        elif v.get("reason"):
            detail = str(v["reason"])[:70]
        rows.append((edge.get("id", "?"), label, detail))
    return round(time.time() - t0, 1), rows


def main():
    try:
        with urllib.request.urlopen(BASE, timeout=30) as r:
            index = json.loads(r.read())
    except Exception as exc:  # noqa: BLE001
        print(f"Cannot reach {BASE}: {exc}")
        print("Start the server first:  python backend/server.py 8517")
        return 1

    if not any(p.get("configured") for p in _providers()):
        print("Warning: no NASA provider is connected yet. Pathways will be")
        print("reported as 'not connected'. Connect Earthdata in Data & Methods.\n")

    ids = [e["id"] for e in index.get("events", [])]
    ordered = [i for i in ORDER if i in ids] + [i for i in ids if i not in ORDER]

    verified = 0
    for event_id in ordered:
        print(f"{event_id}")
        try:
            seconds, rows = warm(event_id)
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED: {exc}\n")
            continue
        for edge_id, label, detail in rows:
            if label == "verified":
                verified += 1
            print(f"  {edge_id[:38]:40s} {label:14s} {detail}")
        print(f"  ({seconds}s)\n")

    print(f"{verified} pathways verified from source.")

    # Photographs are cached too, so the gallery never waits on a remote host
    # during a presentation and a rate-limited download cannot leave a gap.
    try:
        import event_images
        ok, failed = event_images.warm()
        print(f"{ok} event photographs cached"
              + (f", {failed} could not be fetched" if failed else ""))
    except Exception as exc:  # noqa: BLE001
        print(f"photographs not cached: {exc}")

    print("Reopen the Events tab; cached events load without new downloads.")
    return 0


def _providers():
    try:
        with urllib.request.urlopen(
                "http://127.0.0.1:8517/api/data-sources", timeout=30) as r:
            return json.loads(r.read()).get("providers", [])
    except Exception:  # noqa: BLE001
        return []


if __name__ == "__main__":
    sys.exit(main())
