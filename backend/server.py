"""TerraTrend backend HTTP server.

Serves the JSON API under /api/* and the static frontend at /.
Run:  python server.py  [port]
"""
import datetime
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import catalog
import gibs
import interconnect
import literature
import power_client
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

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}


def _month_labels(months):
    out = []
    for m in months:
        s = str(m)
        out.append(f"{s[:4]}-{s[4:]}")
    return out


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
    """Area-average of the grid for each month."""
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
    # trend uses complete years only (see _annualize)
    annual_values = _complete_years(yearly_ts)

    cells = []
    for lo in sorted(grid):
        for la in sorted(grid[lo]):
            raw = [grid[lo][la].get(m) for m in months]
            ann = _complete_years(_annualize(month_labels, raw))
            a = analyze_series(ann)
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
                cell.update({"slope": 0.0, "direction": "nodata",
                            "significant": False, "p": 1.0,
                            "per_decade": 0.0, "stars": ""})
            cells.append(cell)

    overall = analyze_series(annual_values)
    seasonal = seasonal_mk(region_ts, period=12)
    # The observatory modal reads these three straight off `overall`; keep them
    # there as well as in the `seasonal` tuple so the seasonal MK cross-check is
    # actually visible instead of rendering "N/A".
    sz, sp, _stau, ssig = seasonal[0], seasonal[1], seasonal[2], seasonal[3]
    overall["seasonal_z"] = sz
    overall["seasonal_p"] = sp
    overall["seasonal_significant"] = ssig

    return {
        "variable": var,
        "monthly_timeseries": [
            {"month": m, "value": v} for m, v in zip(month_labels, region_ts)
        ],
        "yearly_timeseries": yearly_ts,
        "cells": cells,
        "overall": overall,
        "seasonal": seasonal,
        "summary": _summarize(cells),
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


def run_analysis(variables, region, start, end, nx=5, ny=5, compare_region=None):
    """Core analysis pipeline across one or more variables."""
    if end - start < 8:
        raise ValueError("Need at least 9 years of data (end - start >= 8)")
    if end > MAX_YEAR:
        raise ValueError(f"Data available through {MAX_YEAR}")

    reg = next((r for r in catalog.REGIONS if r["id"] == region), None)
    if not reg:
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
        grid = power_client.fetch_grid(var["id"], reg["bbox"], start, end, nx, ny)

        if months is None:
            all_months = set()
            for lo in grid:
                for la in grid[lo]:
                    all_months.update(grid[lo][la].keys())
            months = sorted(m for m in all_months
                            if len(str(m)) == 6 and str(m)[4:] != "13")
            month_labels = _month_labels(months)
            if month_labels:
                first_valid = month_labels[0]
                last_valid = month_labels[-1]

        block = analyze_variable(var, grid, months, month_labels)
        try:
            block["literature"] = literature.search_papers(
                var["id"], reg["name"])
        except Exception as e:  # noqa: BLE001
            block["literature"] = {"ok": False, "error": str(e), "papers": []}
        series.append(block)

    couplings = []
    if len(series) >= 2:
        for i in range(len(series)):
            for j in range(i + 1, len(series)):
                block_a = series[i]
                block_b = series[j]
                ts_a = [p["value"] for p in block_a["yearly_timeseries"]]
                ts_b = [p["value"] for p in block_b["yearly_timeseries"]]
                c = analyze_cross_coupling(
                    block_a["variable"], block_b["variable"],
                    ts_a, ts_b,
                    block_a["overall"], block_b["overall"]
                )
                couplings.append(c)

    compare_data = None
    if compare_region and compare_region != region:
        reg_b = next((r for r in catalog.REGIONS if r["id"] == compare_region), None)
        if reg_b:
            compare_series = []
            contrasts = []
            for i, var in enumerate(vars_):
                grid_b = power_client.fetch_grid(var["id"], reg_b["bbox"], start, end, nx, ny)
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
                "region": reg_b,
                "series": compare_series,
                "contrasts": contrasts,
            }

    satellite_data = None
    try:
        satellite_data = gibs.get_satellite_evidence(reg, start, end)
    except Exception as e:  # noqa: BLE001
        satellite_data = {"error": str(e)}

    out = {
        "region": reg, "start": start, "end": end,
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
        "sources": ["NASA POWER (MERRA-2 / GPCP / CERES)", "NASA GIBS (MODIS / VIIRS)", "OpenAlex"],
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

    reg = next((r for r in catalog.REGIONS if r["id"] == region), None)
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
            try:
                grid = power_client.fetch_grid(var["id"], reg["bbox"],
                                               start, end, nx, ny)
            except Exception as e:  # noqa: BLE001
                still_failed.append(var)
                if attempt == 1:
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
                months = sorted(m for m in all_months
                                if len(str(m)) == 6 and str(m)[4:] != "13")
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
            }
            time.sleep(0.15)  # stay inside POWER's limiter

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
        "region": reg, "start": start, "end": end,
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
        "sources": ["NASA POWER (MERRA-2 / GPCP / CERES)"],
    }


def run_coupling_analysis(region_id, variables, start, end):
    """Directed coupling diagnostics between all requested variables in one
    region.

    Detection is fully computed (see interconnect.analyze_local_couplings):
    seasonal decomposition, lagged cross-correlation for direction, partial
    correlation controlling for temperature, and two-way Granger F-tests.
    """
    if end - start < 5:
        raise ValueError("Need at least 6 years of data (end - start >= 5)")
    reg = next((r for r in catalog.REGIONS if r["id"] == region_id), None)
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
    for var in vars_:
        try:
            grids[var["id"]] = power_client.fetch_grid(
                var["id"], reg["bbox"], start, end, 5, 5)
        except Exception:
            grids[var["id"]] = None

    all_months = set()
    for g in grids.values():
        if not g:
            continue
        for lo in g:
            for la in g[lo]:
                all_months.update(g[lo][la].keys())
    months = sorted(m for m in all_months
                    if len(str(m)) == 6 and str(m)[4:] != "13")
    month_labels = _month_labels(months)

    series_by_var = {}
    for var in vars_:
        g = grids.get(var["id"])
        if not g:
            continue
        series_by_var[var["id"]] = _region_series(g, months)

    pairs = interconnect.analyze_local_couplings(reg, series_by_var, month_labels)

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
        if not mechanism:
            mechanism = interconnect.describe_coupling(
                var_meta.get(p["a"], {}), var_meta.get(p["b"], {}), p)
        out_pairs.append({
            "a": {"id": a["id"], "name": a["name"], "unit": a["unit"],
                  "color": a["color"], "sphere": a.get("sphere"),
                  "sphere_code": a.get("sphere_code")},
            "b": {"id": b["id"], "name": b["name"], "unit": b["unit"],
                  "color": b["color"], "sphere": b.get("sphere"),
                  "sphere_code": b.get("sphere_code")},
            "r": p["r"],
            "r_lagged": p["r_lagged"],
            "p": p["p"],
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
            "mechanism": mechanism,
        })

    return {
        "region": reg,
        "start": start,
        "end": end,
        "variables": [{
            "id": v["id"], "name": v["name"], "unit": v["unit"],
            "color": v["color"], "sphere": v.get("sphere"),
            "sphere_code": v.get("sphere_code"),
        } for v in vars_],
        "pairs": out_pairs,
        "method": (
            "Seasonal decomposition (monthly climatology + linear trend removed) · "
            "lagged cross-correlation (±6 mo) for direction · first-order partial "
            "correlation (T2M confounder) · two-way Granger F-test (3 lags) · α=0.05"
        ),
        "sources": ["NASA POWER (MERRA-2 / GPCP / CERES)"],
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

    reg_src = next((r for r in catalog.REGIONS if r["id"] == source_region), None)
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
        candidate_regs = [r for r in catalog.REGIONS if r["id"] in target_regions and r["id"] != source_region]
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
    grid_src = power_client.fetch_grid(var_src["id"], reg_src["bbox"], start, end, 5, 5)
    all_months = set()
    for lo in grid_src:
        for la in grid_src[lo]:
            all_months.update(grid_src[lo][la].keys())
    months = sorted(m for m in all_months if len(str(m)) == 6 and str(m)[4:] != "13")
    month_labels = _month_labels(months)

    src_region_ts = _region_series(grid_src, months)
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

    for reg_tgt in candidate_regs:
        for var_tgt in candidate_vars:
            scanned_count += 1
            try:
                if src_anom is None:
                    continue
                grid_tgt = power_client.fetch_grid(var_tgt["id"], reg_tgt["bbox"], start, end, 5, 5)
                tgt_region_ts = _region_series(grid_tgt, months)
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
                        "p": round(p, 4),
                        "lag_months": diag["lag_months"],
                        "lead_note": diag["lead_note"],
                        "composite": diag["composite"],
                        "direction": direction,
                        "strength": strength,
                        "mechanism": mechanism,
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
    scanned_p = [c["p"] for c in connections]
    n_survive = interconnect.benjamini_hochberg(scanned_p, q=0.10)
    ranked = sorted(connections, key=lambda c: c["p"])
    kept_ids = {id(c) for c in ranked[:n_survive]}
    rejected = len(connections) - len(kept_ids)
    connections = [c for c in connections if id(c) in kept_ids]

    connections.sort(key=lambda x: abs(x["r_lagged"]), reverse=True)

    strongest_direct = next((c for c in connections if c["direction"] == "direct"), None)
    strongest_inverse = next((c for c in connections if c["direction"] == "inverse"), None)

    return {
        "source": {
            "region": reg_src,
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
        "sources": ["NASA POWER (MERRA-2 / GPCP / CERES)"],
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
            if path == "/api/availability":
                return self._json(200, power_client.probe_availability())
            if path == "/api/catalog":
                return self._json(200, {
                    "variables": catalog.CATALOG,
                    "spheres": catalog.SPHERES,
                    "regions": catalog.REGIONS,
                    "years": {"min": 1985, "max": MAX_YEAR},
                    "max_variables": MAX_VARS,
                    "availability": power_client.probe_availability(),
                })
            if path == "/api/satellite-imagery":
                region_id = q.get("region", [""])[0]
                reg = next((r for r in catalog.REGIONS if r["id"] == region_id), None)
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
                result = run_analysis(
                    variables, region,
                    _int(q, "start", 2000), _int(q, "end", MAX_YEAR),
                    max(3, min(7, _int(q, "nx", 5))),
                    max(3, min(7, _int(q, "ny", 5))),
                    compare_region=compare_region,
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

    def _static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        target = (FRONTEND_DIR / path.lstrip("/")).resolve()
        if not str(target).startswith(str(FRONTEND_DIR.resolve())):
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
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"TerraTrend running on http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down")
        server.server_close()


if __name__ == "__main__":
    main()
