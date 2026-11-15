"""TerraTrend backend HTTP server.

Serves the JSON API under /api/* and the static frontend at /.
Run:  python server.py  [port]
"""
import datetime
import json
import math
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import catalog
import gibs
import interconnect
import power_client
import geography
import spatial
import data_sources
import event_images
import event_network
import jobs
from analysis import (
    analyze_series, seasonal_mk,
    analyze_cross_coupling, analyze_regional_contrast,
    calculate_pearson, pearson_significance, explain_teleconnection,
    PHYSICAL_COUPLINGS
)

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
BOOT = time.time()
MAX_VARS = 3
MIN_YEAR = 1981
MAX_YEAR = datetime.date.today().year   # data currency follows the calendar
MIN_MONTHS_PER_YEAR = 12               # a year must be complete to enter a trend
MIN_POINT_COVERAGE = 0.80              # fraction of grid points that must report

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".glsl": "text/plain; charset=utf-8",
    ".geojson": "application/geo+json; charset=utf-8",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}


def _month_labels(months):
    out = []
    for m in months:
        s = str(m)
        out.append(f"{s[:4]}-{s[4:]}")
    return out


def calendar_months(start,end):
    return [year*100+month for year in range(start,end+1) for month in range(1,13)]


def _annualize(month_labels, values):
    """Group monthly values by year.

    Each entry carries its month count and a `complete` flag. Only complete
    years may enter a trend test: a partial year (e.g. Jan-Sep of the current
    year) has a different seasonal composition and would bias the slope.
    """
    yearly = {}
    for lbl, v in zip(month_labels, values):
        if v is not None:
            yearly.setdefault(int(lbl[:4]), []).append(v)

    out = []
    for y, vs in sorted(yearly.items()):
        if not vs:
            continue
        out.append({
            "year": y,
            "value": round(sum(vs) / len(vs), 4),
            "months": len(vs),
            "complete": len(vs) >= MIN_MONTHS_PER_YEAR,
        })
    return out


def _complete_years(yearly_ts):
    return [p["value"] for p in yearly_ts if p["complete"]]


def _yearly_anomalies(values, month_labels):
    """Average a monthly anomaly series down to per-year anomaly points."""
    by_year = {}
    for lbl, v in zip(month_labels, values):
        if v is None:
            continue
        by_year.setdefault(int(lbl[:4]), []).append(v)
    out = []
    for y, vs in sorted(by_year.items()):
        out.append({
            "year": y,
            "value": round(sum(vs) / len(vs), 4),
        })
    return out


def _region_series(grid, months):
    """Area-average of the grid for each month.

    Also returns how many grid points contributed to each month, so callers can
    reject years where only a subset of the box reported. Averaging 4 of 25
    points and averaging 25 of 25 are different measurements of different
    places; silently mixing them bends the trend.
    """
    if hasattr(grid,"regional_series"):
        values=[grid.regional_series.get(m) for m in months]
        return values,[1. if value is not None else 0. for value in values]
    if isinstance(grid, spatial.Grid):
        return spatial.weighted_series(grid, months)
    out = []
    counts = []
    for m in months:
        vals = []
        for lo in grid:
            for la in grid[lo]:
                v = grid[lo][la].get(m,grid[lo][la].get(str(m)))
                if v is not None:
                    vals.append(v)
        counts.append(len(vals))
        out.append(round(sum(vals) / len(vals), 4) if vals else None)
    return out, counts


def _coverage_threshold(grid):
    """Minimum grid points that must report before a month counts as regional."""
    if isinstance(grid, spatial.Grid):
        return grid.expected_weight * MIN_POINT_COVERAGE
    total = sum(len(grid[lo]) for lo in grid)
    return max(1, int(math.ceil(total * MIN_POINT_COVERAGE)))


def covered_region_series(grid, months):
    values,counts=_region_series(grid,months)
    need=_coverage_threshold(grid)
    return [v if count>=need else None for v,count in zip(values,counts)]


def analyze_variable(var, grid, months, month_labels):
    """Build the per-variable analysis block (series, cells, summary)."""
    region_ts, month_counts = _region_series(grid, months)
    need = _coverage_threshold(grid)

    # A month is usable only when enough of the box actually reported. This
    # guards against the mixed-spatial-support artefact where early years are
    # averaged over a handful of points and later years over the full grid.
    thin = [i for i, c in enumerate(month_counts) if 0 < c < need]
    for i in thin:
        region_ts[i] = None

    yearly_ts = _annualize(month_labels, region_ts)
    annual_points = [p for p in yearly_ts if p["complete"]]
    annual_values = [p["value"] for p in annual_points]

    cells = []
    for lo in sorted(grid):
        for la in sorted(grid[lo]):
            if len(cells)%128==0:jobs.check_cancelled()
            raw = [grid[lo][la].get(m,grid[lo][la].get(str(m))) for m in months]
            ann_points = [p for p in _annualize(month_labels, raw) if p["complete"]]
            ann = [p["value"] for p in ann_points]
            a = analyze_series(
                ann, percent_ok=catalog.percent_change_ok(var["id"]), xs=[p["year"] for p in ann_points])
            cell = {"lon": lo, "lat": la, "n": a.get("n", 0)}
            if a.get("ok"):
                cell.update({
                    "slope": a["slope"],
                    "direction": a["direction"],
                    "significant": a["significant"],
                    "p": a["p"],
                    "per_decade": a["per_decade"],
                    "stars": a["stars"],
                    "ci_low_per_decade": a.get("ci_low_per_decade"),
                    "ci_high_per_decade": a.get("ci_high_per_decade"),
                    "t_p": a.get("t_p"),
                    "methods_agree": a.get("methods_agree"),
                })
            else:
                cell.update({"slope": None, "direction": "nodata",
                            "significant": False, "p": 1.0,
                            "per_decade": None, "stars": ""})
            cells.append(cell)

    overall = analyze_series(
        annual_values, percent_ok=catalog.percent_change_ok(var["id"]), xs=[p["year"] for p in annual_points])
    seasonal = seasonal_mk(region_ts, period=12)
    # The observatory modal reads these three straight off `overall`; keep them
    # there as well as in the `seasonal` tuple so the seasonal MK cross-check is
    # actually visible instead of rendering "N/A".
    sz, sp, _stau, ssig = seasonal[0], seasonal[1], seasonal[2], seasonal[3]
    overall["seasonal_z"] = sz
    overall["seasonal_p"] = sp
    overall["seasonal_significant"] = ssig

    return {
        "variable": {**var,"dataset":grid.provenance.get("dataset"),"source_field":grid.provenance.get("field")} if getattr(grid,"provenance",{}) else var,
        "provenance": getattr(grid, "provenance", {}),
        "monthly_timeseries": [
            {"month": m, "value": v} for m, v in zip(month_labels, region_ts)
        ],
        "yearly_timeseries": yearly_ts,
        "cells": cells,
        "overall": overall,
        "seasonal": seasonal,
        "summary": {**_summarize(cells),"spatial_detail_available":not hasattr(grid,"regional_series")},
    }


def _summarize(cells):
    valid = [c for c in cells if c["direction"] != "nodata"]
    sig = [c for c in valid if c["significant"]]
    rising = [c for c in sig if c["direction"] == "rising"]
    falling = [c for c in sig if c["direction"] == "falling"]
    return {
        "total_cells": len(cells),
        "valid_cells": len(valid),
        "significant_cells": len(sig),
        "rising_cells": len(rising),
        "falling_cells": len(falling),
        "consensus": (
            "rising" if len(rising) > len(valid) * 0.4 else
            "falling" if len(falling) > len(valid) * 0.4 else
            "mixed" if sig else "none"
        ),
    }


def resolve_region(region):
    return next((r for r in catalog.REGIONS if r["id"] == region), None) or geography.resolve(region)


def fetch_region(var_id, region, start, end, nx=5, ny=5):
    if region.get("geometry"):
        return data_sources.fetch_region(var_id, region, start, end)
    if data_sources.PROVIDER.get() != "legacy-live":
        fid = "focus:" + region["id"]
        if fid not in geography._FEATURES:
            x0,y0,x1,y1=region["bbox"]
            geography._FEATURES[fid]=geography._feature(fid,region["name"],"focus",{
                "type":"Polygon","coordinates":[[[x0,y0],[x1,y0],[x1,y1],[x0,y1],[x0,y0]]]})
        return data_sources.fetch_region(var_id,geography._FEATURES[fid],start,end)
    return power_client.fetch_grid(var_id, region["bbox"], start, end, nx, ny)


def region_metadata(region):
    return {k:v for k,v in region.items() if k != "geometry"}


PROVIDER_LABELS = {
    "nasa-merra2": "NASA Earthdata (MERRA-2)",
    "nasa-giovanni": "NASA Earthdata (Giovanni)",
    "nasa-hydrology": "NASA Earthdata (Hydrology)",
    "nasa-appeears": "NASA AppEEARS",
    "noaa-cdo": "NOAA Climate Data Online",
}


def _provider_configured(variable):
    """Whether the provider that owns this measurement is connected."""
    adapter = data_sources.ADAPTERS.get(data_sources.LINKED_ROUTES.get(variable))
    if adapter is None:
        return True
    try:
        return bool(adapter.status().get("configured"))
    except Exception:  # noqa: BLE001
        return True


def event_series(region_id, variable, start, end):
    """One series for the curated event network.

    Runs through exactly the same provider dispatch, native-cell weighting and
    coverage threshold as an ordinary analysis, so an event number and an
    Analyze number for the same box cannot disagree.

    An all-empty series is reported as a connection problem when the owning
    provider is not connected, rather than as "not enough months" -- those are
    different claims and only one of them is the user's to fix.
    """
    reg = resolve_region(region_id)
    if not reg:
        raise KeyError(f"Unknown event region: {region_id}")
    grid = fetch_region(variable, reg, start, end)
    values = covered_region_series(grid, calendar_months(start, end))
    if not any(v is not None for v in values):
        if not _provider_configured(variable):
            label = PROVIDER_LABELS.get(
                data_sources.LINKED_ROUTES.get(variable), "NASA Earthdata")
            raise RuntimeError(f"Connect {label} in Data & Methods to read "
                               f"{variable} observations.")
        raise RuntimeError(f"No usable {variable} observations for {region_id} "
                           f"in {start}-{end}.")
    return values


def run_analysis(variables, region, start, end, nx=5, ny=5, compare_region=None,
                 bbox=None):
    """Core analysis pipeline across one or more variables.

    bbox: optional [lon0, lat0, lon1, lat1]. When present the analysis runs on
    that exact area, which is what makes a globe click honest.
    """
    if end - start < 8:
        raise ValueError("Need at least 9 years of data (end - start >= 8)")
    if start < MIN_YEAR:
        raise ValueError(f"Data window must start at or after {MIN_YEAR}")
    if end > MAX_YEAR:
        raise ValueError(f"Data available through {MAX_YEAR}")

    reg = resolve_region(region)
    if bbox:
        reg = {
            "id": "custom",
            "name": "Selected Area",
            "bbox": bbox,
            "desc": "Area chosen on the globe",
            "surface": "land",
        }
    elif not reg:
        raise KeyError(f"Unknown region {region}")

    vars_ = []
    for vid in variables:
        v = next((x for x in catalog.CATALOG if x["id"] == vid), None)
        if v:
            vars_.append(v)
    if not vars_:
        raise ValueError("No known variables requested")

    series = []
    months = None
    month_labels = None
    first_valid = None
    last_valid = None

    for var in vars_:
        grid = fetch_region(var["id"], reg, start, end, nx, ny)

        if months is None:
            all_months = set()
            for lo in grid:
                for la in grid[lo]:
                    all_months.update(grid[lo][la].keys())
            months = calendar_months(start,end)
            month_labels = _month_labels(months)
            if month_labels:
                first_valid = month_labels[0]
                last_valid = month_labels[-1]

        block = analyze_variable(var, grid, months, month_labels)
        series.append(block)
        if len(series)==1:
            available=[p["month"] for p in block["monthly_timeseries"] if p["value"] is not None]
            first_valid=available[0] if available else None
            last_valid=available[-1] if available else None

    couplings = []
    if len(series) >= 2:
        for i in range(len(series)):
            for j in range(i + 1, len(series)):
                block_a = series[i]
                block_b = series[j]
                common = sorted({p["year"] for p in block_a["yearly_timeseries"] if p["complete"]} & {p["year"] for p in block_b["yearly_timeseries"] if p["complete"]})
                aa = {p["year"]:p["value"] for p in block_a["yearly_timeseries"]}
                bb = {p["year"]:p["value"] for p in block_b["yearly_timeseries"]}
                ts_a = [aa[y] for y in common]
                ts_b = [bb[y] for y in common]
                c = analyze_cross_coupling(
                    block_a["variable"], block_b["variable"],
                    ts_a, ts_b,
                    block_a["overall"], block_b["overall"]
                )
                c["description"]="Co-trend association. Possible mechanism: "+c.get("description","")
                c["evidence_type"]="co_trend_association"
                couplings.append(c)

    compare_data = None
    if compare_region and compare_region != region:
        reg_b = resolve_region(compare_region)
        if reg_b:
            compare_series = []
            contrasts = []
            for i, var in enumerate(vars_):
                grid_b = fetch_region(var["id"], reg_b, start, end, nx, ny)
                block_b = analyze_variable(var, grid_b, months, month_labels)
                compare_series.append(block_b)
                contrast = analyze_regional_contrast(
                    var, reg, reg_b,
                    series[i]["yearly_timeseries"],
                    block_b["yearly_timeseries"],
                    series[i]["overall"],
                    block_b["overall"]
                )
                contrasts.append(contrast)

            compare_data = {
                "region": region_metadata(reg_b),
                "series": compare_series,
                "contrasts": contrasts,
            }

    satellite_data = None
    try:
        satellite_data = gibs.get_satellite_evidence(reg, start, end) if data_sources.PROVIDER.get() == "legacy-live" else {"enabled": False, "reason": "Imagery route not enabled by the challenge source policy"}
    except Exception as e:  # noqa: BLE001
        satellite_data = {"error": str(e)}

    out = {
        "region": region_metadata(reg), "start": start, "end": end,
        "months": month_labels,
        "series": series,
        "grid": {"nx": nx, "ny": ny, "bbox": reg["bbox"]},
        "satellite": satellite_data,
        "couplings": couplings,
        "window": {
            "first_month": first_valid,
            "last_month": last_valid,
            "partial_years": [
                y["year"]
                for y in (series[0]["yearly_timeseries"] if series else [])
                if not y.get("complete", True)
            ],
        },
        "sources": list(dict.fromkeys([b.get("provenance", {}).get("source", "NASA POWER (legacy)") for b in series])),
        "provenance": [b.get("provenance", {}) for b in series],
    }
    if compare_data:
        out["compare"] = compare_data
    return out


def run_scan(variables, region, start, end, nx=5, ny=5):
    """Score every requested variable for one region and rank them.

    This is the "which variable is actually trending here?" question the
    challenge opens with. It deliberately uses the *same* grid resolution as a
    full analysis so the numbers agree when a user opens a row.
    POWER responses are cached, so opening any individual variable afterwards is instant.
    """
    if end - start < 8:
        raise ValueError("Need at least 9 years of data (end - start >= 8)")
    if end > MAX_YEAR:
        raise ValueError(f"Data available through {MAX_YEAR}")

    reg = resolve_region(region)
    if not reg:
        raise KeyError(f"Unknown region {region}")

    vars_ = []
    for vid in variables:
        v = next((x for x in catalog.CATALOG if x["id"] == vid), None)
        if v:
            vars_.append(v)
    if not vars_:
        raise ValueError("No known variables requested")

    months = None
    month_labels = None
    rows_by_id = {}

    pending = list(vars_)
    for attempt in (0, 1):
        if not pending:
            break
        still_failed = []
        for var in pending:
            jobs.progress(len(rows_by_id),len(vars_),"Testing "+var["name"])
            try:
                grid = fetch_region(var["id"], reg, start, end, nx, ny)
            except Exception as e:  # noqa: BLE001
                if data_sources.PROVIDER.get()=="legacy-live":still_failed.append(var)
                if attempt == 1 or data_sources.PROVIDER.get()!="legacy-live":
                    rows_by_id[var["id"]] = {
                        "id": var["id"], "name": var["name"],
                        "unit": var["unit"], "color": var["color"],
                        "group": var.get("group", "temperature"),
                        "sphere_code": var.get("sphere_code", "ATM"),
                        "ok": False,
                        "error": str(e)[:120], "significant": False,
                        "direction": "nodata", "tau": 0.0,
                    }
                continue

            if months is None:
                all_months = set()
                for lo in grid:
                    for la in grid[lo]:
                        all_months.update(grid[lo][la].keys())
                months = calendar_months(start,end)
                month_labels = _month_labels(months)

            block = analyze_variable(var, grid, months, month_labels)
            o = block["overall"]
            sm = block["summary"]
            rows_by_id[var["id"]] = {
                "id": var["id"], "name": var["name"], "unit": var["unit"],
                "color": var["color"],
                "group": var.get("group", "temperature"),
                "sphere_code": var.get("sphere_code", "ATM"),
                "ok": o.get("ok", False),
                "slope_decade": o.get("per_decade"),
                "p": o.get("p"),
                "z": o.get("z"),
                "tau": o.get("tau"),
                "significant": bool(o.get("significant")),
                "direction": o.get("direction", "nodata"),
                "n": o.get("n"),
                "change_pct": o.get("change_pct"),
                "stars": o.get("stars", ""),
                "cells_sig": sm["significant_cells"],
                "cells_total": sm["total_cells"],
                "provenance": block.get("provenance",{}),
            }
            if data_sources.PROVIDER.get()=="legacy-live":time.sleep(0.15)

        pending = still_failed
        if pending:
            time.sleep(8)

    rows = [rows_by_id[v["id"]] for v in vars_ if v["id"] in rows_by_id]

    # strongest first: significant before not, then by |tau| (trend coherence)
    rows.sort(key=lambda r: (
        0 if r.get("significant") else 1,
        -abs(r.get("tau") or 0.0),
    ))

    ok_rows = [r for r in rows if r.get("ok")]
    return {
        "region": region_metadata(reg), "start": start, "end": end,
        "grid": {"nx": nx, "ny": ny, "bbox": reg["bbox"]},
        "window": {"last_month": None, "partial_years": []},
        "scanned": rows,
        "summary": {
            "total": len(rows),
            "analysable": len(ok_rows),
            "significant": sum(1 for r in ok_rows if r["significant"]),
            "rising": sum(1 for r in ok_rows
                          if r["significant"] and r["direction"] == "rising"),
            "falling": sum(1 for r in ok_rows
                           if r["significant"] and r["direction"] == "falling"),
            "strongest": ok_rows[0]["name"] if ok_rows else None,
        },
        "sources": list(dict.fromkeys(r.get("provenance",{}).get("source","No source data") for r in rows)),
    }


def run_coupling_analysis(region_id, variables, start, end, target_variable=None):
    """Directed coupling diagnostics between all requested variables in one
    region.

    Detection is fully computed (see interconnect.analyze_local_couplings):
    seasonal decomposition, lagged cross-correlation for direction, partial
    correlation controlling for temperature, and two-way Granger F-tests.
    """
    if end - start < 5:
        raise ValueError("Need at least 6 years of data (end - start >= 5)")
    reg = resolve_region(region_id)
    if not reg:
        raise KeyError(f"Unknown region {region_id}")

    vars_ = []
    for vid in variables:
        v = next((x for x in catalog.CATALOG if x["id"] == vid), None)
        if v:
            vars_.append(v)
    if len(vars_) < 2:
        raise ValueError("Need at least two variables to diagnose coupling")

    grids = {}
    source_errors={}
    for var in vars_:
        jobs.check_cancelled()
        try:
            grids[var["id"]] = fetch_region(var["id"], reg, start, end, 5, 5)
        except Exception as e:
            grids[var["id"]] = None
            source_errors[var['id']]=str(e)[:250]

    all_months = set()
    for g in grids.values():
        if not g:
            continue
        for lo in g:
            for la in g[lo]:
                all_months.update(g[lo][la].keys())
    months = calendar_months(start,end)
    month_labels = _month_labels(months)

    series_by_var = {}
    for var in vars_:
        g = grids.get(var["id"])
        if g is None:
            continue
        series_by_var[var["id"]] = covered_region_series(g, months)

    pairs = interconnect.analyze_local_couplings(reg, series_by_var, month_labels)
    conditional = None
    if target_variable in series_by_var:
        candidates=[]
        for p in pairs:
            if p["response"]==target_variable and p["driver"] in series_by_var:
                try:
                    candidates.append({"id":p["driver"],"lag":max(1,abs(p["lag_months"])),
                        "values":interconnect.decompose_monthly(series_by_var[p["driver"]])["values"]})
                except ValueError:continue
        try:
            conditional=interconnect.conditional_driver_model(interconnect.decompose_monthly(series_by_var[target_variable])["values"],candidates)
        except ValueError:
            conditional={"ok":False,"reason":"Insufficient anomaly coverage"}

    var_meta = {v["id"]: v for v in vars_}
    out_pairs = []
    for p in pairs:
        a = var_meta.get(p["a"])
        b = var_meta.get(p["b"])
        if not a or not b:
            continue
        lexicon = PHYSICAL_COUPLINGS.get(frozenset({p["a"], p["b"]}), {})
        title = lexicon.get("title") or f"{a['name']} ↔ {b['name']}"
        mechanism = lexicon.get("description", "")
        if p["phase"] == "divergent" and "divergent" in lexicon:
            mechanism = lexicon["divergent"]
        elif p["phase"] == "in_phase" and "in_phase" in lexicon:
            mechanism = lexicon["in_phase"]
        has_mechanism=bool(mechanism)
        if not mechanism:
            mechanism = interconnect.describe_coupling(
                var_meta.get(p["a"], {}), var_meta.get(p["b"], {}), p)
        out_pairs.append({
            "source_a":getattr(grids.get(p['a']),'provenance',{}).get('source','Unknown source'),
            "source_b":getattr(grids.get(p['b']),'provenance',{}).get('source','Unknown source'),
            "overlapping_months":sum(a is not None and b is not None for a,b in zip(series_by_var[p['a']],series_by_var[p['b']])),
            "a": {"id": a["id"], "name": a["name"], "unit": a["unit"],
                  "color": a["color"], "sphere": a.get("sphere"),
                  "sphere_code": a.get("sphere_code")},
            "b": {"id": b["id"], "name": b["name"], "unit": b["unit"],
                  "color": b["color"], "sphere": b.get("sphere"),
                  "sphere_code": b.get("sphere_code")},
            "r": p["r"],
            "r_lagged": p["r_lagged"],
            "p": p["p"],
            "p_adjusted": p.get("p_adjusted"),
            "lag_months": p["lag_months"],
            "driver": p["driver"],
            "response": p["response"],
            "lag_note": p["lag_note"],
            "r_partial": p["r_partial"],
            "p_partial": p["p_partial"],
            "granger_a_b": p["granger_a_b"],
            "granger_b_a": p["granger_b_a"],
            "phase": p["phase"],
            "strength": p["strength"],
            "confidence": p["confidence"],
            "title": title,
            "mechanism": ("Possible mechanism: " if has_mechanism else "Computed relationship: ")+mechanism,
            "mechanism_status": "hypothesis" if has_mechanism else "statistical_description",
        })

    source_anomaly=None
    if target_variable in series_by_var:
        try:
            residual=interconnect.decompose_monthly(series_by_var[target_variable])['values']
            source_anomaly={'region':region_metadata(reg),'variable':var_meta[target_variable],
                'anomaly_report':interconnect.anomaly_report(residual,month_labels),
                'anomaly_yearly':_yearly_anomalies(residual,month_labels),'month_labels':month_labels}
        except ValueError:pass
    return {
        "region": region_metadata(reg),
        "start": start,
        "end": end,
        "variables": [{
            "id": v["id"], "name": v["name"], "unit": v["unit"],
            "color": v["color"], "sphere": v.get("sphere"),
            "sphere_code": v.get("sphere_code"),
        } for v in vars_],
        "pairs": out_pairs,
        "source_errors":source_errors,
        "analysable_variables":[vid for vid,values in series_by_var.items() if sum(v is not None for v in values)>=interconnect.MIN_MONTHS],
        "source_anomaly":source_anomaly,
        "conditional_drivers": conditional,
        "provenance": {vid:getattr(g,"provenance",{}) for vid,g in grids.items() if g is not None},
        "method": (
            "Seasonal decomposition (monthly climatology + linear trend removed) · "
            "lagged cross-correlation (±6 mo) for direction · first-order partial "
            "correlation (T2M confounder) · two-way Granger F-test (3 lags) · α=0.05"
        ),
        "sources": list(dict.fromkeys(getattr(g,"provenance",{}).get("source","NASA POWER (legacy)") for g in grids.values() if g is not None)),
    }


def run_teleconnections(source_region, source_var, target_regions=None, target_vars=None, start=2005, end=MAX_YEAR, min_r=0.15, min_effect=0.25):
    """Scan and discover cross-regional teleconnections and planetary ripple effects.

    Given an origin region and driver variable, cross-correlates its timeline
    against candidate Earth system variables across global regions to identify
    statistically significant teleconnections (|r| >= min_r, p < 0.05).
    """
    if end - start < 8:
        raise ValueError("Need at least 9 years of data (end - start >= 8)")
    if end > MAX_YEAR:
        raise ValueError(f"Data available through {MAX_YEAR}")

    reg_src = resolve_region(source_region)
    if not reg_src:
        raise KeyError(f"Unknown source region: {source_region}")
    var_src = next((v for v in catalog.CATALOG if v["id"] == source_var), None)
    if not var_src:
        raise KeyError(f"Unknown source variable: {source_var}")

    # Resolve target regions
    DEFAULT_TELECON_HUBS = [
        "ghana_north", "amazon", "california", "sahel",
        "madagascar", "europe", "sahara"
    ]
    if target_regions:
        candidate_regs = [r for r in (resolve_region(fid) for fid in target_regions) if r and r["id"] != source_region]
    else:
        # Default to planetary sentinel hubs spanning distinct climate zones
        candidate_regs = [r for r in catalog.REGIONS if r["id"] in DEFAULT_TELECON_HUBS and r["id"] != source_region]

    # Resolve target variables
    DEFAULT_TELECON_VARS = ["T2M", "PRECTOTCORR", "GWETROOT", "TS", "WS2M", "RH2M", "EVPTRNS", "ALLSKY_SFC_SW_DNI"]
    if target_vars:
        candidate_vars = [v for v in catalog.CATALOG if v["id"] in target_vars]
    else:
        candidate_vars = [v for v in catalog.CATALOG if v["id"] in DEFAULT_TELECON_VARS]

    if not candidate_vars:
        candidate_vars = [v for v in catalog.CATALOG if v["id"] in DEFAULT_TELECON_VARS]

    # Fetch and prepare source series
    grid_src = fetch_region(var_src["id"], reg_src, start, end, 5, 5)
    all_months = set()
    for lo in grid_src:
        for la in grid_src[lo]:
            all_months.update(grid_src[lo][la].keys())
    months = calendar_months(start,end)
    month_labels = _month_labels(months)

    src_region_ts = covered_region_series(grid_src, months)
    src_yearly = _annualize(month_labels, src_region_ts)
    ts_src = _complete_years(src_yearly)

    # Anomaly view of the driver: the seasonal cycle and the region's own
    # long-term trend are removed, so what remains is "when did this variable
    # run hotter/colder than its own history says it should have". Remote
    # responses are then measured against that, not against a shared trend
    # (two unrelated rising series correlate by coincidence).
    try:
        src_decomp = interconnect.decompose_monthly(src_region_ts)
        src_anom = src_decomp["values"]
        src_anomaly_report = interconnect.anomaly_report(src_anom, month_labels)
    except ValueError:
        src_decomp = None
        src_anom = None
        src_anomaly_report = None

    connections = []
    scanned_count = 0
    tested_p = []

    for reg_tgt in candidate_regs:
        for var_tgt in candidate_vars:
            jobs.progress(scanned_count,len(candidate_regs)*len(candidate_vars),"Screening "+reg_tgt["name"]+" / "+var_tgt["name"])
            scanned_count += 1
            try:
                if src_anom is None:
                    continue
                grid_tgt = fetch_region(var_tgt["id"], reg_tgt, start, end, 5, 5)
                tgt_region_ts = covered_region_series(grid_tgt, months)
                tgt_yearly = _annualize(month_labels, tgt_region_ts)
                try:
                    tgt_decomp = interconnect.decompose_monthly(tgt_region_ts)
                except ValueError:
                    continue
                diag = interconnect.impact_pair(
                    src_anom, tgt_decomp["values"], month_labels)
                if not diag:
                    continue

                r = diag["r"]
                p = diag["p"]
                tested_p.append(p)

                # Three gates, because with ~260 monthly samples a |r| of 0.2
                # is already "significant" — significance alone would report
                # most of the scan. A link must be (a) correlated after both
                # seasons and trend are removed, (b) unlikely to be chance, and
                # (c) large enough to matter: the target must sit measurably
                # off its own baseline during the driver's surges.
                eff = abs((diag.get("composite") or {}).get("effect_sigma") or 0)
                if abs(diag["r_lagged"]) >= min_r and p < 0.01 and eff >= min_effect:
                    strength = ("STRONG" if abs(diag["r_lagged"]) >= 0.45
                                else ("MODERATE" if abs(diag["r_lagged"]) >= 0.28
                                      else "NOTABLE"))
                    direction = "direct" if r > 0 else "inverse"
                    mechanism = interconnect.mechanism_sentence(
                        reg_src, var_src, reg_tgt, var_tgt, diag)

                    # Compute center coords for 3D arcs
                    src_lat = (reg_src["bbox"][1] + reg_src["bbox"][3]) / 2.0
                    src_lon = (reg_src["bbox"][0] + reg_src["bbox"][2]) / 2.0
                    tgt_lat = (reg_tgt["bbox"][1] + reg_tgt["bbox"][3]) / 2.0
                    tgt_lon = (reg_tgt["bbox"][0] + reg_tgt["bbox"][2]) / 2.0

                    connections.append({
                        "source_region": {
                            "id": reg_src["id"],
                            "name": reg_src["name"],
                            "lat": round(src_lat, 2),
                            "lon": round(src_lon, 2),
                        },
                        "source_variable": {
                            "id": var_src["id"],
                            "name": var_src["name"],
                            "unit": var_src["unit"],
                            "color": var_src["color"],
                        },
                        "target_region": {
                            "id": reg_tgt["id"],
                            "name": reg_tgt["name"],
                            "surface": reg_tgt.get("surface", "land"),
                            "lat": round(tgt_lat, 2),
                            "lon": round(tgt_lon, 2),
                        },
                        "target_variable": {
                            "id": var_tgt["id"],
                            "name": var_tgt["name"],
                            "unit": var_tgt["unit"],
                            "color": var_tgt["color"],
                            "sphere": var_tgt.get("sphere", "atmosphere"),
                            "sphere_code": var_tgt.get("sphere_code", "ATM"),
                        },
                        "r": round(r, 3),
                        "r_lagged": diag["r_lagged"],
                        "p": p,
                        "relationship": "response" if diag["lag_months"] > 0 else "driver" if diag["lag_months"] < 0 else "simultaneous",
                        "evidence_label": "Lagged association; physical causation not established",
                        "lag_months": diag["lag_months"],
                        "lead_note": diag["lead_note"],
                        "composite": diag["composite"],
                        "direction": direction,
                        "strength": strength,
                        "mechanism": mechanism,
                        "source_provenance": getattr(grid_src,"provenance",{}),
                        "target_provenance": getattr(grid_tgt,"provenance",{}),
                        "source_yearly": src_yearly,
                        "target_yearly": tgt_yearly,
                        "target_anomaly_yearly": _yearly_anomalies(
                            tgt_decomp["values"], month_labels),
                    })
            except Exception:
                continue

    # Family-wise false-discovery control. Scanning ~50 remote
    # region/variable pairs at alpha=0.05 guarantees a handful of coincidences;
    # only pairs that survive Benjamini-Hochberg across the whole scan are
    # reported, so a "discovery" is not just the luckiest test in the batch.
    n_survive = interconnect.benjamini_hochberg(tested_p, q=0.10)
    cutoff = sorted(tested_p)[n_survive-1] if n_survive else -1.0
    kept_ids = {id(c) for c in connections if c["p"] <= cutoff}
    for c in connections:
        c["p_adjusted"] = interconnect.bh_adjusted_p(c["p"], tested_p)
    rejected = len(connections) - len(kept_ids)
    connections = [c for c in connections if id(c) in kept_ids]

    connections.sort(key=lambda x: abs(x["r_lagged"]), reverse=True)

    strongest_direct = next((c for c in connections if c["direction"] == "direct"), None)
    strongest_inverse = next((c for c in connections if c["direction"] == "inverse"), None)

    return {
        "source": {
            "region": region_metadata(reg_src),
            "variable": var_src,
            "start": start,
            "end": end,
            "yearly_timeseries": src_yearly,
            "anomaly_report": src_anomaly_report,
            "anomaly_yearly": _yearly_anomalies(src_anom or [], month_labels),
            "month_labels": month_labels,
        },
        "summary": {
            "total_scanned": scanned_count,
            "valid_tests": len(tested_p),
            "geographic_coverage": [r["name"] for r in candidate_regs],
            "significant_count": len(connections),
            "fdr_rejected": rejected,
            "fdr_q": 0.10,
            "min_effect_sigma": min_effect,
            "strongest_direct": {
                "region": strongest_direct["target_region"]["name"],
                "variable": strongest_direct["target_variable"]["name"],
                "r": strongest_direct["r"],
            } if strongest_direct else None,
            "strongest_inverse": {
                "region": strongest_inverse["target_region"]["name"],
                "variable": strongest_inverse["target_variable"]["name"],
                "r": strongest_inverse["r"],
            } if strongest_inverse else None,
        },
        "teleconnections": connections,
        "method": (
            "Seasonal + trend decomposition of the driver · lagged "
            "cross-correlation of anomalies (±24 mo) · composite response of "
            "each target during driver +1σ months · α=0.05"
        ),
        "sources": list(dict.fromkeys([getattr(grid_src,"provenance",{}).get("source","NASA POWER (legacy)")]+[c.get("target_provenance",{}).get("source","NASA POWER (legacy)") for c in connections])),
    }


def execute_job(spec):
    if spec.get("provider")=="legacy-live":raise ValueError("Live legacy access is not enabled under the challenge resource policy")
    token=data_sources.PROVIDER.set(spec.get("provider","project-cache"))
    try:
        operation=spec.get("operation","analyze")
        variables=spec.get("variables",[])
        start,end=int(spec.get("start",2005)),int(spec.get("end",MAX_YEAR))
        if not isinstance(variables,list) or not variables or not all(isinstance(v,str) for v in variables):
            raise ValueError("Select at least one variable")
        known={v["id"] for v in catalog.CATALOG}
        if any(v not in known for v in variables):raise ValueError("Unknown variable")
        if data_sources.PROVIDER.get() in {"nasa-merra2","nasa-giovanni"} and not data_sources.nasa_data.token():
            raise data_sources.nasa_data.EarthdataRequired("Connect Earthdata in Data & Methods once. NASA downloads require your account; TerraTrend fetches the observations automatically after connecting.")
        available=data_sources.supported(data_sources.PROVIDER.get())
        if data_sources.PROVIDER.get()=="nasa-giovanni":
            if operation not in {"analyze","scan","overview","interconnections"}:raise ValueError('Unsupported Giovanni operation')
            if operation=='interconnections' and spec.get('relationship_scope','local')!='local':raise ValueError('Giovanni relationship screening is local to the selected rectangle; remote country boundaries need native mode.')
            available=list(data_sources.giovanni_data.FIELDS)
            ids=spec.get('features',[]) if operation=='overview' else [spec.get('region'),spec.get('compare_region')]
            if operation=='overview' and (not isinstance(ids,list) or not ids):raise ValueError('Choose rectangle preset areas for the Giovanni layer request')
            for fid in ids:
                if fid:data_sources.giovanni_data.rectangle(resolve_region(fid) or {})
        if start<MIN_YEAR or end>MAX_YEAR or end-start<8:
            raise ValueError(f"Choose at least nine years within {MIN_YEAR}–{MAX_YEAR}")
        region=spec.get("region","")
        if operation=="analyze":
            return run_analysis(variables[:MAX_VARS],region,start,end,compare_region=spec.get("compare_region"))
        if operation=="scan":
            return run_scan(available,region,start,end)
        if operation=="interconnections":
            scope=spec.get('relationship_scope','local')
            if scope not in {'local','remote'}:raise ValueError('Choose local or remote relationship screening')
            fields=spec.get('relationship_variables') or available
            if not isinstance(fields,list) or len(fields)<2 or len(fields)>20 or variables[0] not in fields or any(v not in available for v in fields):
                raise ValueError('Choose at least two supported measurements for relationship screening')
            if data_sources.PROVIDER.get()=='multi-source' and not spec.get('relationship_variables'):
                raise ValueError('Select 2–3 measurements to link across sources; all sources are not downloaded automatically')
            jobs.progress(0,2,"Testing local variable relationships")
            local=run_coupling_analysis(region,fields,start,end,target_variable=variables[0])
            global_links=None
            if scope=='remote':
                if not spec.get('target_regions'):raise ValueError('Choose explicit target areas for the remote search')
                jobs.progress(1,2,"Screening remote relationships and lead direction")
                global_links=run_teleconnections(region,variables[0],spec['target_regions'],target_vars=fields,start=start,end=end)
            return {"local":local,"global":global_links,"scope":scope}
        if operation=="overview":
            if data_sources.PROVIDER.get()=='noaa-cdo' or (data_sources.PROVIDER.get()=='multi-source' and variables[0].startswith('STATION_')):
                raise ValueError('Station summaries cannot color whole-country area trends. Use Analysis or Compare for the station evidence.')
            ids=spec.get("features",[])
            if not isinstance(ids,list) or len(ids)>260:raise ValueError("Too many geographic units")
            rows=[]
            for i,fid in enumerate(ids):
                jobs.progress(i,len(ids),f"Analyzing area {i+1} of {len(ids)}")
                try:
                    result=run_analysis(variables[:1],fid,start,end)
                    block=result["series"][0]
                    rows.append({"id":fid,"overall":block["overall"],"summary":block["summary"],"provenance":block.get("provenance",{})})
                except (ValueError,KeyError) as e:
                    rows.append({"id":fid,"overall":{"ok":False,"reason":str(e)}})
            return {"rows":rows,"variable":variables[0],"start":start,"end":end}
        raise ValueError("Unknown analysis operation")
    finally:
        data_sources.PROVIDER.reset(token)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _same_origin(self):
        origin=self.headers.get("Origin")
        if not origin:return True
        parsed=urlparse(origin)
        return parsed.scheme in {"http","https"} and parsed.netloc==self.headers.get("Host")

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code, body, ctype="application/json; charset=utf-8",
              cache="no-store"):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if self.headers.get("Origin") and self._same_origin():self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin"))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj))

    def do_OPTIONS(self):
        if not self._same_origin():return self._json(403,{"error":"Cross-origin access is not allowed"})
        self.send_response(204)
        if self.headers.get("Origin"):self.send_header("Access-Control-Allow-Origin",self.headers.get("Origin"))
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_POST(self):
        try:
            if not self._same_origin():return self._json(403,{"error":"Cross-origin writes are not allowed"})
            length=int(self.headers.get("Content-Length",0))
            if length<=0 or length>32_000_000:raise ValueError("Request body must be between 1 byte and 32 MB")
            spec=json.loads(self.rfile.read(length))
            if not isinstance(spec,dict):raise ValueError("Expected a JSON object")
            path=urlparse(self.path).path
            if path=="/api/geography/custom":
                return self._json(201,geography.register_custom(spec))
            if path=="/api/data-sources/import":
                return self._json(201,data_sources.import_csv(spec))
            if path=="/api/data-sources/earthdata":
                if spec.get("disconnect"):return self._json(200,data_sources.nasa_data.disconnect())
                return self._json(200,data_sources.nasa_data.connect(spec.get("token",""),remember=spec.get('remember',True) is True))
            if path=='/api/data-sources/appeears':
                if spec.get('disconnect'):return self._json(200,data_sources.appeears_data.disconnect())
                return self._json(200,data_sources.appeears_data.connect(spec.get('username'),spec.get('password'),remember=spec.get('remember',True) is True))
            if path=="/api/jobs":
                custom=spec.get('custom_areas',[])
                if not isinstance(custom,list) or len(custom)>2:raise ValueError('At most two custom selection boundaries are supported')
                for area in custom:
                    feature=geography.register_custom(area)
                    if area.get('id') and area['id']!=feature['id']:raise ValueError('Custom selection identity does not match its geometry')
                # The immutable request identity includes geometry and method versions.
                spec["method_version"]="polygon-sen-calendar-fdr-v1"
                ids=[spec.get("region"),spec.get("compare_region")]+spec.get("features",[])
                spec["geometry_versions"]={fid:(resolve_region(fid) or {}).get("geometry_version","focus-v1") for fid in ids if fid}
                return self._json(202,jobs.submit(spec,lambda:execute_job(spec)))
            if path.startswith("/api/jobs/") and path.endswith("/cancel"):
                return self._json(200,jobs.cancel(path.split("/")[3]))
            return self._json(404,{"error":"Unknown operation"})
        except (ValueError,TypeError,json.JSONDecodeError) as e:
            return self._json(400,{"error":str(e)})
        except KeyError as e:
            return self._json(404,{"error":str(e)})

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        q = parse_qs(parsed.query)

        token=data_sources.PROVIDER.set(q.get("provider",["project-cache"])[0])
        try:
            if data_sources.PROVIDER.get()=="legacy-live":
                raise ValueError("Live legacy access is not enabled under the challenge resource policy")
            if path=="/api/geography":
                return self._json(200,geography.collection(q.get("level",["continent"])[0],q.get("parent",[None])[0]))
            if path=="/api/data-sources":
                return self._json(200,{"providers":data_sources.providers(),"resources":data_sources.ALLOWED,"earthdata":data_sources.nasa_data.status(),"appeears":data_sources.appeears_data.status()})
            if path.startswith("/api/jobs/"):
                return self._json(200,jobs.get(path.split("/")[3]))
            if path == "/api/health":
                return self._json(200, {"ok": True,
                                        "uptime_s": round(time.time() - BOOT, 1)})
            if path == "/api/availability":
                return self._json(200, {"ok":False,"mode":"Automatic NASA / project cache","message":"Published granules and actual observed dates are reported with each analysis"})
            if path == "/api/catalog":
                return self._json(200, {
                    "variables": catalog.CATALOG,
                    "spheres": catalog.SPHERES,
                    "regions": catalog.REGIONS + geography.catalog(),
                    "years": {"min": MIN_YEAR, "max": MAX_YEAR},
                    "max_variables": MAX_VARS,
                    "custom_selections": True,
                    "automatic_data": True,
                    "availability": {"ok":False,"mode":"Automatic NASA / project cache"},
                })
            if path.startswith("/api/event-image/"):
                # Curated event imagery, served from the local cache so the tab
                # never depends on a remote CDN while someone is presenting.
                parts = path[len("/api/event-image/"):].strip("/").split("/")
                if len(parts) != 2:
                    return self._json(400, {"error": "event id and image index required"})
                try:
                    index = int(parts[1])
                except ValueError:
                    return self._json(400, {"error": "image index must be a number"})
                try:
                    raw, ctype = event_images.image_bytes(parts[0], index)
                except KeyError:
                    return self._json(404, {"error": "no such event image"})
                except Exception as exc:  # noqa: BLE001
                    return self._json(
                        502, {"error": f"Event image could not be fetched: {exc}"})
                return self._send(200, raw, ctype, cache="public, max-age=604800")
            if path == "/api/events":
                return self._json(200, event_network.index())
            if path.startswith("/api/events/"):
                event_id = path[len("/api/events/"):].strip("/")
                if not event_id:
                    return self._json(400, {"error": "event id required"})
                # The generic GET default is the legacy project cache; the
                # catalogue describes live events and must read the automatic
                # NASA source unless the caller explicitly asks otherwise.
                event_provider = data_sources.PROVIDER.set(
                    q.get("provider", ["nasa-merra2"])[0])
                try:
                    return self._json(200, event_network.build(
                        event_id, MAX_YEAR, event_series))
                except KeyError as exc:
                    return self._json(404, {"error": str(exc)})
                except ValueError as exc:
                    return self._json(400, {"error": str(exc)})
                finally:
                    data_sources.PROVIDER.reset(event_provider)
            if path == "/api/satellite-imagery":
                if data_sources.PROVIDER.get()!="legacy-live":
                    return self._json(400,{"error":"This imagery route has not been enabled under the challenge resource policy. See Data & Methods."})
                region_id = q.get("region", [""])[0]
                reg = resolve_region(region_id)
                custom_bbox = None
                bbox_raw = q.get("bbox", [""])[0]
                if bbox_raw:
                    try:
                        coords = [float(x.strip()) for x in bbox_raw.split(",")]
                        if len(coords) == 4:
                            custom_bbox = coords
                    except Exception:  # noqa: BLE001
                        pass

                if not reg and not custom_bbox:
                    return self._json(400, {"error": f"Unknown region {region_id} and no valid bbox"})

                region_obj = reg if reg else {"id": "custom", "name": "Selected Area", "bbox": custom_bbox}
                start_yr = _int(q, "start", 2005)
                end_yr = _int(q, "end", MAX_YEAR)
                layer = q.get("layer", ["true_color"])[0]
                date_md = q.get("date", [""])[0]
                ev = gibs.get_satellite_evidence(region_obj, start_yr, end_yr, bbox=custom_bbox, layer_key=layer, custom_date=date_md)
                return self._json(200, ev)
            if path == "/api/teleconnections":
                source_reg = q.get("region", [""])[0]
                source_var = q.get("variable", [""])[0]
                if not source_reg or not source_var:
                    return self._json(400, {"error": "region and variable required"})
                target_regions_raw = q.get("target_regions", [""])[0]
                target_regions = [r.strip() for r in target_regions_raw.split(",") if r.strip()] if target_regions_raw else None
                target_vars_raw = q.get("target_vars", [""])[0]
                target_vars = [v.strip() for v in target_vars_raw.split(",") if v.strip()] if target_vars_raw else None
                min_r = float(q.get("min_r", [0.15])[0])
                min_effect = float(q.get("min_effect", [0.25])[0])
                res = run_teleconnections(
                    source_reg, source_var,
                    target_regions=target_regions,
                    target_vars=target_vars,
                    start=_int(q, "start", 2005),
                    end=_int(q, "end", MAX_YEAR),
                    min_r=min_r,
                    min_effect=min_effect,
                )
                return self._json(200, res)
            if path == "/api/coupling":
                region = q.get("region", [""])[0]
                if not region:
                    return self._json(400, {"error": "region required"})
                raw = q.get("variables", [""])[0]
                if raw.strip():
                    variables = [v.strip() for v in raw.split(",") if v.strip()]
                else:
                    variables = [v["id"] for v in catalog.CATALOG]
                res = run_coupling_analysis(
                    region, variables,
                    _int(q, "start", 2005), _int(q, "end", MAX_YEAR),
                )
                return self._json(200, res)
            if path == "/api/scan":
                region = q.get("region", [""])[0]
                if not region:
                    return self._json(400, {"error": "region required"})
                raw = q.get("variables", [""])[0]
                if raw.strip():
                    variables = [v.strip() for v in raw.split(",") if v.strip()]
                else:
                    variables = [v["id"] for v in catalog.CATALOG]
                result = run_scan(
                    variables, region,
                    _int(q, "start", 2000), _int(q, "end", MAX_YEAR),
                    max(3, min(6, _int(q, "nx", 5))),
                    max(3, min(6, _int(q, "ny", 5))),
                )
                return self._json(200, result)
            if path == "/api/analyze":
                raw = q.get("variables", q.get("variable", [""]))[0]
                variables = [v.strip() for v in raw.split(",") if v.strip()]
                region = q.get("region", [""])[0]
                compare_region = q.get("compare_region", [""])[0] or None
                if not variables or not region:
                    return self._json(
                        400, {"error": "variables and region required"})
                variables = list(dict.fromkeys(variables))[:MAX_VARS]

                # A globe click can supply a real bbox instead of a preset
                # region id. Without this, "tap anywhere" silently snapped to
                # the nearest of 23 boxes and analysed somewhere the user did
                # not pick.
                bbox = None
                raw_bbox = q.get("bbox", [""])[0]
                if raw_bbox:
                    try:
                        vals = [float(x) for x in raw_bbox.split(",")]
                    except ValueError:
                        return self._json(400, {"error": "bbox must be 4 numbers"})
                    if len(vals) != 4:
                        return self._json(400, {"error": "bbox must be lon0,lat0,lon1,lat1"})
                    lon0, lat0, lon1, lat1 = vals
                    if not (-180 <= lon0 < lon1 <= 180 and -90 <= lat0 < lat1 <= 90):
                        return self._json(400, {"error": "bbox out of range or inverted"})
                    if (lon1 - lon0) < 0.5 or (lat1 - lat0) < 0.5:
                        return self._json(400, {"error": "bbox too small (min 0.5 deg)"})
                    bbox = vals

                result = run_analysis(
                    variables, region,
                    _int(q, "start", 2000), _int(q, "end", MAX_YEAR),
                    max(3, min(7, _int(q, "nx", 5))),
                    max(3, min(7, _int(q, "ny", 5))),
                    compare_region=compare_region,
                    bbox=bbox,
                )
                return self._json(200, result)
            return self._static(path)
        except KeyError as e:
            return self._json(404, {"error": str(e)})
        except ValueError as e:
            return self._json(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            return self._json(500, {"error": str(e)})
        finally:
            data_sources.PROVIDER.reset(token)

    def _static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        root = FRONTEND_DIR.resolve()
        target = (root / path.lstrip("/")).resolve()
        # `startswith(str(root))` also accepts sibling dirs such as
        # `frontend-evil`, so compare resolved parents instead.
        if target != root and root not in target.parents:
            return self._json(403, {"error": "forbidden"})
        if not target.is_file():
            return self._json(404, {"error": "not found"})
        ext = target.suffix.lower()
        ctype = MIME.get(ext, "application/octet-stream")
        with open(target, "rb") as f:
            data = f.read()
        return self._send(200, data, ctype)


def _int(q, key, default):
    try:
        return int(q.get(key, [default])[0])
    except (ValueError, TypeError):
        return default


def main():
    port = 8517
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"TerraTrend running on http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down")
        server.server_close()


if __name__ == "__main__":
    main()
