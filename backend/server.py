"""TerraTrend server — zero-dependency stdlib HTTP server.

Serves the JSON API under /api/* and the static frontend at /.
Run:  python server.py  [port]
"""
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import catalog
import literature
import power_client
from analysis import analyze_series, seasonal_mk

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
BOOT = time.time()
MAX_VARS = 3

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


def _int(q, key, default):
    try:
        return int(q.get(key, [default])[0])
    except (TypeError, ValueError):
        return default


def _month_labels(months):
    return [f"{str(m)[:4]}-{str(m)[4:]}" for m in months]


def _annualize(month_labels, values):
    yearly = {}
    for lbl, v in zip(month_labels, values):
        if v is not None:
            yearly.setdefault(int(lbl[:4]), []).append(v)
    return [{"year": y, "value": round(sum(vs) / len(vs), 4)}
            for y, vs in sorted(yearly.items()) if vs]


def _region_series(grid, months):
    out = []
    for m in months:
        vals = []
        for lo in grid:
            for la in grid[lo]:
                v = grid[lo][la].get(m)
                if v is not None:
                    vals.append(v)
        out.append(round(sum(vals) / len(vals), 4) if vals else None)
    return out


def analyze_variable(var, grid, months, month_labels):
    """Build the per-variable analysis block (series, cells, summary)."""
    region_ts = _region_series(grid, months)
    yearly_ts = _annualize(month_labels, region_ts)
    annual_values = [p["value"] for p in yearly_ts]

    cells = []
    for lo in sorted(grid):
        for la in sorted(grid[lo]):
            raw = [grid[lo][la].get(m) for m in months]
            ann = [p["value"] for p in _annualize(month_labels, raw)]
            a = analyze_series(ann)
            cell = {"lon": lo, "lat": la, "n": a.get("n", 0)}
            if a.get("ok"):
                cell.update({
                    "slope": a["slope"], "z": a["z"], "p": a["p"],
                    "significant": a["significant"],
                    "direction": a["direction"],
                    "change_pct": a["change_pct"],
                })
            else:
                cell.update({"slope": None, "significant": False,
                             "direction": "nodata"})
            cells.append(cell)

    overall = analyze_series(annual_values)
    sz, sp, _, sh = seasonal_mk(region_ts)
    overall["seasonal_z"] = sz
    overall["seasonal_p"] = sp
    overall["seasonal_significant"] = sh

    return {
        "variable": var,
        "region_timeseries": region_ts,
        "yearly_timeseries": yearly_ts,
        "overall": overall,
        "cells": cells,
        "summary": _summarize(cells),
    }


def _summarize(cells):
    sig = [c for c in cells if c.get("significant")]
    return {
        "significant_cells": len(sig),
        "total_cells": len(cells),
        "rising": sum(1 for c in sig if c["direction"] == "rising"),
        "falling": sum(1 for c in sig if c["direction"] == "falling"),
    }


def run_analysis(variables, region, start, end, nx=5, ny=5):
    """Core analysis pipeline across one or more variables."""
    if end - start < 8:
        raise ValueError("Need at least 9 years of data (end - start >= 8)")
    if end > 2024:
        raise ValueError("Data available through 2024")

    reg = next((r for r in catalog.REGIONS if r["id"] == region), None)
    if not reg:
        raise KeyError(f"Unknown region {region}")

    vars_ = []
    for vid in variables:
        v = next((x for x in catalog.CATALOG if x["id"] == vid), None)
        if not v:
            raise KeyError(f"Unknown variable {vid}")
        vars_.append(v)
    if not vars_:
        raise ValueError("At least one variable required")

    months = None
    month_labels = None
    series = []

    for var in vars_:
        grid = power_client.fetch_grid(var["id"], reg["bbox"],
                                       start, end, nx, ny)
        if months is None:
            all_months = set()
            for lo in grid:
                for la in grid[lo]:
                    all_months.update(grid[lo][la].keys())
            months = sorted(m for m in all_months
                            if len(str(m)) == 6 and str(m)[4:] != "13")
            month_labels = _month_labels(months)

        block = analyze_variable(var, grid, months, month_labels)
        try:
            block["literature"] = literature.search_papers(
                var["id"], reg["name"])
        except Exception as e:  # noqa: BLE001
            block["literature"] = {"ok": False, "error": str(e), "papers": []}
        series.append(block)

    return {
        "region": reg, "start": start, "end": end,
        "months": month_labels,
        "series": series,
        "grid": {"nx": nx, "ny": ny, "bbox": reg["bbox"]},
        "sources": ["NASA POWER (MERRA-2 / GPCP / CERES)", "OpenAlex"],
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        q = parse_qs(parsed.query)

        try:
            if path == "/api/health":
                return self._json(200, {"ok": True,
                                        "uptime_s": round(time.time() - BOOT, 1)})
            if path == "/api/catalog":
                return self._json(200, {
                    "variables": catalog.CATALOG,
                    "regions": catalog.REGIONS,
                    "years": {"min": 1985, "max": 2024},
                    "max_variables": MAX_VARS,
                })
            if path == "/api/analyze":
                raw = q.get("variables", q.get("variable", [""]))[0]
                variables = [v.strip() for v in raw.split(",") if v.strip()]
                region = q.get("region", [""])[0]
                if not variables or not region:
                    return self._json(
                        400, {"error": "variables and region required"})
                variables = list(dict.fromkeys(variables))[:MAX_VARS]
                result = run_analysis(
                    variables, region,
                    _int(q, "start", 2000), _int(q, "end", 2024),
                    max(3, min(7, _int(q, "nx", 5))),
                    max(3, min(7, _int(q, "ny", 5))),
                )
                return self._json(200, result)
            return self._static(path)
        except KeyError as e:
            return self._json(404, {"error": str(e).strip("'\"")})
        except ValueError as e:
            return self._json(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            return self._json(502, {"error": f"Analysis failed: {e}"})

    def _static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        target = (FRONTEND_DIR / path.lstrip("/")).resolve()
        try:
            target.relative_to(FRONTEND_DIR.resolve())
        except ValueError:
            return self._json(403, {"error": "forbidden"})
        if not target.is_file():
            return self._json(404, {"error": "not found"})
        ctype = MIME.get(target.suffix.lower(), "application/octet-stream")
        return self._send(200, target.read_bytes(), ctype)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8517
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"TerraTrend running at http://127.0.0.1:{port}")
    print("Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down")


if __name__ == "__main__":
    main()
