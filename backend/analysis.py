"""Trend analysis core: Mann-Kendall + Theil-Sen.

Two entry points:
  * analyze_series()  - MK + Theil-Sen on an ordered series (annual means recommended)
  * seasonal_mk()     - Hirsch-Slack seasonal MK for raw monthly data

Trends on raw monthly values are dominated by the seasonal cycle, so
annual aggregation is the defensible default for trend detection.
"""
import math

ALPHA = 0.05


def _norm_cdf(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _s_stat(ys):
    """Mann-Kendall S statistic."""
    n = len(ys)
    s = 0
    for i in range(n - 1):
        yi = ys[i]
        for j in range(i + 1, n):
            d = ys[j] - yi
            s += (d > 0) - (d < 0)
    return s


def _var_s(ys):
    """Variance of S with tie correction."""
    n = len(ys)
    var = n * (n - 1) * (2 * n + 5) / 18.0
    ties = {}
    for v in ys:
        ties[v] = ties.get(v, 0) + 1
    for t in ties.values():
        if t > 1:
            var -= t * (t - 1) * (2 * t + 5) / 18.0
    return max(var, 1e-12)


def _z_from_s(s, var):
    if s > 0:
        return (s - 1) / math.sqrt(var)
    if s < 0:
        return (s + 1) / math.sqrt(var)
    return 0.0


def mk_test(ys):
    """Mann-Kendall trend test. Returns (z, p, tau, h)."""
    n = len(ys)
    if n < 8:
        return 0.0, 1.0, 0.0, False
    s = _s_stat(ys)
    var = _var_s(ys)
    z = _z_from_s(s, var)
    p = 2.0 * (1.0 - _norm_cdf(abs(z)))
    tau = s / (0.5 * n * (n - 1))
    return z, p, tau, p < ALPHA


def seasonal_mk(monthly_values, n_months=12):
    """Hirsch-Slack seasonal Mann-Kendall on monthly data.

    Splits the series into calendar-month blocks, computes S per block,
    sums S and the variances, then tests the combined statistic. This
    removes the seasonal cycle's influence on significance.
    """
    blocks = [[] for _ in range(n_months)]
    for i, v in enumerate(monthly_values):
        if v is not None:
            blocks[i % n_months].append(v)

    s_total = 0
    var_total = 0.0
    used = 0
    for b in blocks:
        if len(b) >= 3:
            s_total += _s_stat(b)
            var_total += _var_s(b)
            used += len(b)
    if used < 24 or var_total <= 0:
        return 0.0, 1.0, 0.0, False
    z = _z_from_s(s_total, var_total)
    p = 2.0 * (1.0 - _norm_cdf(abs(z)))
    return z, p, 0.0, p < ALPHA


def theil_sen(ys, xs=None):
    """Theil-Sen slope (median of pairwise slopes). Returns (slope, intercept)."""
    n = len(ys)
    if n < 2:
        return 0.0, (ys[0] if ys else 0.0)
    if xs is None:
        xs = list(range(n))
    slopes = []
    for i in range(n - 1):
        for j in range(i + 1, n):
            dx = xs[j] - xs[i]
            if dx != 0:
                slopes.append((ys[j] - ys[i]) / dx)
    if not slopes:
        return 0.0, ys[0]
    slopes.sort()
    m = len(slopes)
    med_slope = slopes[m // 2] if m % 2 else 0.5 * (slopes[m // 2 - 1] + slopes[m // 2])
    intercepts = sorted(ys[i] - med_slope * xs[i] for i in range(n))
    k = len(intercepts)
    med_int = intercepts[k // 2] if k % 2 else 0.5 * (intercepts[k // 2 - 1] + intercepts[k // 2])
    return med_slope, med_int


def stars_for(p):
    if p < 0.01:
        return "***"
    if p < 0.05:
        return "**"
    if p < 0.1:
        return "*"
    return ""


def analyze_series(values, dt_per_step=1.0, dt_label="year"):
    """Full trend analysis of one ordered series.

    dt_per_step: time between samples in years (1.0 for annual, 1/12 for monthly).
    """
    pts = [(i, v) for i, v in enumerate(values) if v is not None]
    if len(pts) < 8:
        return {"ok": False, "reason": "insufficient data (<8 points)"}
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]

    z, p, tau, h = mk_test(ys)
    slope, intercept = theil_sen(ys, xs)

    first, last = ys[0], ys[-1]
    total = last - first
    pct = (total / abs(first) * 100.0) if first != 0 else None
    stars = stars_for(p)

    direction = "flat"
    if h and slope > 0:
        direction = "rising"
    elif h and slope < 0:
        direction = "falling"
    elif p < 0.1:
        direction = "rising" if slope > 0 else "falling"

    return {
        "ok": True,
        "n": len(ys),
        "slope": slope,
        "intercept": intercept,
        "z": z,
        "p": p,
        "tau": tau,
        "significant": h,
        "stars": stars,
        "direction": direction,
        "change_total": total,
        "change_pct": pct,
        "per_decade": slope * 10.0 / dt_per_step,
        "dt_label": dt_label,
        "first": first,
        "last": last,
    }


def calculate_pearson(xs, ys):
    """Compute Pearson correlation coefficient r between two numerical series."""
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None and not math.isnan(x) and not math.isnan(y)]
    if len(pairs) < 4:
        return 0.0
    n = len(pairs)
    mean_x = sum(p[0] for p in pairs) / n
    mean_y = sum(p[1] for p in pairs) / n

    cov = sum((p[0] - mean_x) * (p[1] - mean_y) for p in pairs)
    var_x = sum((p[0] - mean_x) ** 2 for p in pairs)
    var_y = sum((p[1] - mean_y) ** 2 for p in pairs)

    denom = math.sqrt(var_x * var_y)
    if denom <= 1e-12:
        return 0.0
    r = cov / denom
    return max(-1.0, min(1.0, r))


PHYSICAL_COUPLINGS = {
    frozenset({"T2M", "RH2M"}): {
        "title": "Vapor Pressure Deficit (VPD) Expansion",
        "description": "As air temperature warms, Clausius-Clapeyron thermodynamics dictate an exponential increase in saturation vapor pressure (~7%/°C). A negative correlation with relative humidity indicates atmospheric drying demand is outstripping moisture replenishment, accelerating surface evapotranspiration and wildfire vulnerability.",
    },
    frozenset({"T2M", "ALLSKY_SFC_LW_DWN"}): {
        "title": "Greenhouse Radiative Trapping Feedback",
        "description": "Rising near-surface temperature coupled with increasing downward longwave flux reflects surface thermal re-radiation and greenhouse heat trapping by column water vapor and trace gases.",
    },
    frozenset({"T2M", "PRECTOTCORR"}): {
        "title": "Hydrological Sensitivity Coupling",
        "divergent": "Aridification regime shift: warming surface temperatures paired with reduced precipitation exacerbate soil moisture deficits and suppress local convective storm initiation.",
        "in_phase": "Convective intensification: elevated thermal energy accelerates the atmospheric hydrological engine, driving higher precipitation volume and intense rainfall events.",
        "description": "Coupling between thermal energy and precipitation characterizes regional hydrological sensitivity to climate shifts.",
    },
    frozenset({"T2M", "ALLSKY_SFC_SW_DNI"}): {
        "title": "Surface Solar Forcing vs Cloud Albedo",
        "description": "Co-trending solar irradiance and air temperature suggests reduced low-cloud optical thickness or aerosol clearing allowing greater direct shortwave penetration to heat the land surface.",
    },
    frozenset({"WS2M", "PS"}): {
        "title": "Synoptic Baroclinic Dynamic Coupling",
        "description": "Interconnection between surface pressure and wind velocities reflects regional baroclinic pressure gradient changes and synoptic storm-track migrations.",
    },
    frozenset({"QV2M", "RH2M"}): {
        "title": "Thermodynamic Saturation Contrast",
        "description": "Specific humidity measures absolute water mass in the air, while relative humidity measures saturation percentage. A divergence reveals air warming fast enough that humidity percentage drops even as absolute moisture rises.",
    },
    frozenset({"QV2M", "PRECTOTCORR"}): {
        "title": "Moisture Transport Convergence",
        "description": "Correlated specific humidity and precipitation rates diagnose regional atmospheric moisture advection and convective convergence efficiency.",
    },
}


def analyze_cross_coupling(var_a, var_b, series_a, series_b, stats_a=None, stats_b=None):
    """Diagnose cross-variable / cross-sphere physical interaction."""
    r = calculate_pearson(series_a, series_b)

    if r >= 0.50:
        phase = "in_phase"
        phase_label = "COUPLED IN-PHASE (AMPLIFYING)"
    elif r <= -0.50:
        phase = "divergent"
        phase_label = "COUPLED DIVERGENCE (OPPOSING)"
    elif abs(r) >= 0.30:
        phase = "moderate"
        phase_label = "MODERATE COUPLING"
    else:
        phase = "decoupled"
        phase_label = "DECOUPLED / INDEPENDENT"

    pair_key = frozenset({var_a.get("id"), var_b.get("id")})
    coupling_info = PHYSICAL_COUPLINGS.get(pair_key, {})
    title = coupling_info.get("title", f"{var_a.get('name')} <-> {var_b.get('name')} Coupling")

    desc = coupling_info.get("description", "")
    if phase == "divergent" and "divergent" in coupling_info:
        desc = coupling_info["divergent"]
    elif phase == "in_phase" and "in_phase" in coupling_info:
        desc = coupling_info["in_phase"]

    if not desc:
        desc = f"Observed correlation of r = {r:.2f} between {var_a.get('name')} and {var_b.get('name')} across the analyzed timeline."

    sph_a = var_a.get("sphere_code", "ATM")
    sph_b = var_b.get("sphere_code", "HYD")
    same_sphere = sph_a == sph_b

    return {
        "var_a": var_a.get("id"),
        "var_b": var_b.get("id"),
        "var_a_name": var_a.get("name"),
        "var_b_name": var_b.get("name"),
        "sphere_a": var_a.get("sphere_name", "Atmosphere"),
        "sphere_b": var_b.get("sphere_name", "Hydrosphere"),
        "sphere_a_code": sph_a,
        "sphere_b_code": sph_b,
        "same_sphere": same_sphere,
        "r": round(r, 3),
        "phase": phase,
        "phase_label": phase_label,
        "title": title,
        "description": desc,
    }


def analyze_regional_contrast(var, reg_a, reg_b, series_a, series_b, stats_a, stats_b):
    """Compare how the same variable trends between two distinct geographical regions."""
    ts_a = [p["value"] for p in series_a if p.get("value") is not None]
    ts_b = [p["value"] for p in series_b if p.get("value") is not None]
    r = calculate_pearson(ts_a, ts_b)

    slope_a = (stats_a.get("slope") or 0.0) * 10.0
    slope_b = (stats_b.get("slope") or 0.0) * 10.0
    diff = slope_a - slope_b

    dir_a = stats_a.get("direction", "flat")
    dir_b = stats_b.get("direction", "flat")

    if dir_a == dir_b and dir_a != "flat":
        verdict = f"PARALLEL TREND ({dir_a.upper()})"
        explanation = f"Both {reg_a.get('name')} and {reg_b.get('name')} exhibit {dir_a} {var.get('name')}. Regional co-trend r = {r:.2f}."
    elif (dir_a == "rising" and dir_b == "falling") or (dir_a == "falling" and dir_b == "rising"):
        verdict = "DIVERGENT / OPPOSING"
        explanation = f"Contrasting Earth system response: {reg_a.get('name')} trends {dir_a} ({slope_a:+.2f} {var.get('unit')}/dec) while {reg_b.get('name')} trends {dir_b} ({slope_b:+.2f} {var.get('unit')}/dec)."
    else:
        verdict = "LOCALIZED SIGNAL"
        explanation = f"Localized change: one region exhibits significant trend while the other remains climatologically stable."

    return {
        "var_id": var.get("id"),
        "var_name": var.get("name"),
        "unit": var.get("unit"),
        "region_a": reg_a.get("name"),
        "region_b": reg_b.get("name"),
        "slope_a_decade": round(slope_a, 3),
        "slope_b_decade": round(slope_b, 3),
        "diff_decade": round(diff, 3),
        "r": round(r, 3),
        "p_a": round(stats_a.get("p", 1.0), 3),
        "p_b": round(stats_b.get("p", 1.0), 3),
        "sig_a": stats_a.get("significant", False),
        "sig_b": stats_b.get("significant", False),
        "verdict": verdict,
        "explanation": explanation,
    }
