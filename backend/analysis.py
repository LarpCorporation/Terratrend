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


def _lag1_autocorr(ys):
    """Lag-1 autocorrelation of a series, clamped to a stable range.

    Estimated on detrended residuals. If it were estimated on the raw series,
    any strong monotonic trend would itself look like autocorrelation
    (r1 -> 1) and the variance correction would erase a real trend.
    """
    n = len(ys)
    if n < 4:
        return 0.0
    xs = list(range(n))
    slope, intercept = theil_sen(ys, xs)
    resid = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    m = sum(resid) / n
    num = sum((resid[i] - m) * (resid[i + 1] - m) for i in range(n - 1))
    den = sum((v - m) ** 2 for v in resid)
    if den <= 1e-12:
        return 0.0
    r1 = num / den
    # Clamp so the variance inflation factor stays finite and positive.
    return max(-0.99, min(0.99, r1))


def _ar1_variance_factor(ys):
    """Variance inflation for MK under AR(1) serial correlation.

    Mann-Kendall assumes independent samples. Annual climate series are
    autocorrelated (one warm year tends to follow another), which makes the
    variance of S too small and the p-value too optimistic. This factor
    rescales Var(S) by (1+r1)/(1-r1) -- the standard first-order correction.

    The factor is floored at 1.0 on purpose. When the residuals happen to look
    negatively autocorrelated the formula would *shrink* the variance and buy
    extra confidence from what is usually small-sample noise (with n=20 the
    standard error of r1 is ~0.22). A trend test should never be made more
    certain by a correction it did not need, so the correction can only widen
    the interval, never narrow it.
    """
    r1 = _lag1_autocorr(ys)
    return max(1.0, (1.0 + r1) / (1.0 - r1)), r1


def mk_test(ys, autocorr=False):
    """Mann-Kendall trend test. Returns (z, p, tau, h).

    autocorr=True applies the AR(1) variance correction, which is the honest
    choice for annual means. The uncorrected test is kept as the default so
    existing callers and tests keep their meaning.
    """
    n = len(ys)
    if n < 8:
        return 0.0, 1.0, 0.0, False
    s = _s_stat(ys)
    var = _var_s(ys)
    if autocorr:
        factor, _r1 = _ar1_variance_factor(ys)
        var *= factor
    z = _z_from_s(s, var)
    p = 2.0 * (1.0 - _norm_cdf(abs(z)))
    tau = s / (0.5 * n * (n - 1))
    return z, p, tau, p < ALPHA


def seasonal_mk(monthly_values, n_months=12, period=None):
    """Hirsch-Slack seasonal Mann-Kendall on monthly data.

    Splits the series into calendar-month blocks, computes S per block,
    sums S and the variances, then tests the combined statistic. This
    removes the seasonal cycle's influence on significance.
    """
    if period is not None:
        n_months = period
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


def theil_sen_ci(ys, xs=None, alpha=0.05):
    """Confidence interval for the Theil-Sen slope.

    Gilbert (1987) normal approximation: rank the pairwise slopes and take the
    ranks bracketing the middle (N -/+ C)/2, where C = z * sqrt(Var(S)).
    Returns (low, high) on the same scale as the slope, or (None, None).
    """
    n = len(ys)
    if n < 8:
        return None, None
    if xs is None:
        xs = list(range(n))

    slopes = []
    for i in range(n - 1):
        for j in range(i + 1, n):
            dx = xs[j] - xs[i]
            if dx:
                slopes.append((ys[j] - ys[i]) / dx)
    if not slopes:
        return None, None
    slopes.sort()
    m = len(slopes)

    # z for the two-sided interval
    z_alpha = 1.959963984540054 if abs(alpha - 0.05) < 1e-9 else _z_for(alpha)
    c = z_alpha * math.sqrt(_var_s(ys))
    total_pairs = n * (n - 1) / 2.0

    lo_rank = math.ceil((total_pairs - c) / 2.0)
    hi_rank = math.ceil((total_pairs + c) / 2.0)
    lo_rank = max(1, min(m, lo_rank))
    hi_rank = max(1, min(m, hi_rank))

    return slopes[lo_rank - 1], slopes[hi_rank - 1]


def _z_for(alpha):
    """Two-sided critical z via bisection on the normal CDF."""
    target = 1.0 - alpha / 2.0
    lo, hi = 0.0, 10.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if _norm_cdf(mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


# ---------------------------------------------------------------------------
# Ordinary least squares + t-test
#
# The challenge brief names three acceptable approaches: "a t-test, the
# Mann-Kendall test, or confidence intervals". We lead with Mann-Kendall
# because climate series are rarely normal, but running the classic t-test
# alongside it lets a user see the two agree — and see exactly where the
# normality assumption starts to matter.
# ---------------------------------------------------------------------------
def _betacf(a, b, x):
    """Continued fraction for the incomplete beta function (Lentz)."""
    maxit, eps, fpmin = 200, 3e-16, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < fpmin:
        d = fpmin
    d = 1.0 / d
    h = d
    for m in range(1, maxit + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def _betai(a, b, x):
    """Regularized incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
             + a * math.log(x) + b * math.log(1.0 - x))
    bt = math.exp(lbeta)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def t_cdf(t, df):
    """Student's t cumulative distribution function."""
    x = df / (df + t * t)
    p = 0.5 * _betai(df / 2.0, 0.5, x)
    return 1.0 - p if t > 0 else p


def t_test_trend(ys, xs=None):
    """OLS slope with a two-sided t-test on the slope.

    Returns dict(slope, intercept, se, t, df, p, ci_low, ci_high) or None.
    """
    n = len(ys)
    if n < 4:
        return None
    if xs is None:
        xs = list(range(n))
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = my - slope * mx
    sse = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    df = n - 2
    mse = sse / df
    if mse <= 0:
        se = 0.0
    else:
        se = math.sqrt(mse / sxx)

    if se == 0.0:
        t = 0.0 if slope == 0 else float("inf")
        p = 1.0 if slope == 0 else 0.0
        lo = hi = slope
    else:
        t = slope / se
        p = 2.0 * (1.0 - t_cdf(abs(t), df))
        # 95% CI via critical t
        target = 0.975
        lo_t, hi_t = 0.0, 20.0
        for _ in range(100):
            mid_t = (lo_t + hi_t) / 2.0
            if t_cdf(mid_t, df) < target:
                lo_t = mid_t
            else:
                hi_t = mid_t
        crit_t = (lo_t + hi_t) / 2.0
        lo = slope - crit_t * se
        hi = slope + crit_t * se

    return {
        "slope": slope,
        "intercept": intercept,
        "se": se,
        "t": t,
        "df": df,
        "p": max(0.0, min(1.0, p)),
        "ci_low": lo,
        "ci_high": hi,
    }


def analyze_series(values, dt_per_step=1.0, dt_label="year", percent_ok=True, xs=None):
    """Full trend analysis of one ordered series.

    dt_per_step: time between samples in years (1.0 for annual, 1/12 for monthly).
    percent_ok: whether percent change is meaningful for this variable's scale.
    """
    if xs is not None and len(xs) != len(values):
        raise ValueError("Time coordinates must match the values")
    pts = [(xs[i] if xs is not None else i, v) for i, v in enumerate(values) if v is not None]
    if len(pts) < 8:
        return {"ok": False, "reason": "insufficient data (<8 points)"}
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]

    # Mann-Kendall with the AR(1) correction: annual means are serially
    # correlated, and the uncorrected test overstates significance.
    z, p, tau, h = mk_test(ys, autocorr=True)
    z_raw, p_raw, _tau_raw, _h_raw = mk_test(ys, autocorr=False)
    ac_factor, ac_r1 = _ar1_variance_factor(ys)
    slope, intercept = theil_sen(ys, xs)
    ci_lo, ci_hi = theil_sen_ci(ys, xs)
    tt = t_test_trend(ys, xs)

    first, last = ys[0], ys[-1]
    total = last - first
    # Percent change is only meaningful for ratio-scale variables. For Celsius
    # or kPa it is an artefact of an arbitrary zero point, so callers decide by
    # passing percent_ok; the default stays permissive for backwards compat.
    pct = (total / abs(first) * 100.0) if (first != 0 and percent_ok) else None
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
        # serial-correlation diagnostics: what the correction did, so a reader
        # can see whether the p-value was materially adjusted
        "autocorr_r1": ac_r1,
        "autocorr_factor": ac_factor,
        "p_uncorrected": p_raw,
        "z_uncorrected": z_raw,
        "per_decade": slope * 10.0 / dt_per_step,
        # classic OLS + t-test, reported alongside Mann-Kendall
        "t_slope": tt["slope"] if tt else None,
        "t_se": tt["se"] if tt else None,
        "t_per_decade": (tt["slope"] * 10.0 / dt_per_step) if tt else None,
        "t_p": tt["p"] if tt else None,
        "t_df": tt["df"] if tt else None,
        "t_significant": (tt["p"] < ALPHA) if tt else False,
        "t_ci_low_per_decade": ((tt["ci_low"] * 10.0 / dt_per_step)
                                if tt else None),
        "t_ci_high_per_decade": ((tt["ci_high"] * 10.0 / dt_per_step)
                                 if tt else None),
        "methods_agree": (tt is not None) and ((tt["p"] < ALPHA) == h),
        "ci_low": ci_lo,
        "ci_high": ci_hi,
        "ci_low_per_decade": (ci_lo * 10.0 / dt_per_step
                              if ci_lo is not None else None),
        "ci_high_per_decade": (ci_hi * 10.0 / dt_per_step
                               if ci_hi is not None else None),
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
    frozenset({"TS", "T2M"}): {
        "title": "Radiometric Skin vs Air Thermal Coupling",
        "description": "Direct coupling between satellite-observed surface skin temperature and 2m ambient air temperature. A widening divergence highlights amplified ground surface heating and sensible heat exchange.",
    },
    frozenset({"GWETROOT", "EVPTRNS"}): {
        "title": "Root-Zone Transpiration Feedback",
        "description": "Coupling between root-zone soil moisture and total evapotranspiration tracks vegetation water stress. Depleted root moisture suppresses plant transpiration, signaling agricultural drought.",
    },
    frozenset({"GWETTOP", "PRECTOTCORR"}): {
        "title": "Surface Hydrological Recharge",
        "description": "Topsoil wetness directly responds to precipitation events. Divergence indicates rapid runoff or high evaporative loss preventing rainfall infiltration into the soil layer.",
    },
    frozenset({"TS", "GWETTOP"}): {
        "title": "Soil Moisture-Skin Temperature Evaporative Cooling",
        "description": "Strong negative correlation between surface wetness and skin temperature confirms soil moisture evaporative cooling. When soil dries out, evaporative cooling ceases and radiant skin temperature spikes.",
    },
    frozenset({"GWETROOT", "T2M"}): {
        "title": "Soil Moisture Deficit Heat Amplification",
        "description": "Persistent root-zone drying partitions incoming radiant energy into sensible rather than latent heat, causing extreme afternoon air temperature spikes.",
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
    """Compare rates and test the calendar-aligned A-minus-B time series.

    The paired test retains covariance between regions. Individual Sen rates
    and their arithmetic difference remain separate from the Sen trend of the
    paired difference. The OLS fallback supports older summary-only callers.
    """
    a_years = {p["year"]:p["value"] for p in series_a if p.get("value") is not None and p.get("complete",True)}
    b_years = {p["year"]:p["value"] for p in series_b if p.get("value") is not None and p.get("complete",True)}
    common = sorted(a_years.keys() & b_years.keys())
    ts_a = [a_years[y] for y in common]
    ts_b = [b_years[y] for y in common]
    r = calculate_pearson(ts_a, ts_b)

    slope_a = (stats_a.get("slope") or 0.0) * 10.0
    slope_b = (stats_b.get("slope") or 0.0) * 10.0
    diff = slope_a - slope_b

    # Standard error of the difference between two independent OLS slopes.
    se_a = (stats_a.get("t_se") or 0.0) * 10.0
    se_b = (stats_b.get("t_se") or 0.0) * 10.0
    se_diff = math.sqrt(se_a ** 2 + se_b ** 2) if (se_a or se_b) else None

    p_diff = None
    diff_z = None
    paired = None
    if se_diff and se_diff > 0:
        diff_z = diff / se_diff
        p_diff = max(0.0, min(1.0, 2.0 * (1.0 - _norm_cdf(abs(diff_z)))))
    # Paired difference series keeps calendar alignment and the covariance
    # between regions, and uses the same Sen/MK machinery as each headline.
    if len(common) >= 8:
        paired = analyze_series([a_years[y]-b_years[y] for y in common], xs=common, percent_ok=False)
        p_diff = paired.get("p")
        diff_z = None
    diff_significant = bool(p_diff is not None and p_diff < ALPHA)

    dir_a = stats_a.get("direction", "flat")
    dir_b = stats_b.get("direction", "flat")
    sig_a = bool(stats_a.get("significant"))
    sig_b = bool(stats_b.get("significant"))

    if diff_significant:
        if sig_a != sig_b:
            verdict = "LOCALIZED SIGNAL"
            explanation = (
                f"The trend is significant in {reg_a.get('name') if sig_a else reg_b.get('name')} "
                f"and not significant in {reg_b.get('name') if sig_a else reg_a.get('name')}. "
                f"The paired difference also changes over time (p = {p_diff:.3f})."
            )
        elif (dir_a == "rising" and dir_b == "falling") or \
           (dir_a == "falling" and dir_b == "rising"):
            verdict = "DIVERGENT / OPPOSING"
            explanation = (
                f"Statistically divergent: {reg_a.get('name')} trends {dir_a} "
                f"({slope_a:+.2f} {var.get('unit')}/dec) while "
                f"{reg_b.get('name')} trends {dir_b} "
                f"({slope_b:+.2f} {var.get('unit')}/dec); the difference is "
                f"significant (p = {p_diff:.3f})."
            )
        else:
            verdict = "SIGNIFICANTLY DIFFERENT RATES"
            explanation = (
                f"Both regions trend the same way, but at different rates: "
                f"{reg_a.get('name')} {slope_a:+.2f} vs {reg_b.get('name')} "
                f"{slope_b:+.2f} {var.get('unit')}/dec (difference p = "
                f"{p_diff:.3f})."
            )
    elif sig_a and not sig_b:
        verdict = "LOCALIZED SIGNAL"
        explanation = (
            f"{reg_a.get('name')} shows a significant {dir_a} trend "
            f"({slope_a:+.2f} {var.get('unit')}/dec); {reg_b.get('name')} does "
            f"not. The difference between them is not itself significant "
            f"(p = {p_diff:.3f})." if p_diff is not None else
            f"{reg_a.get('name')} shows a significant {dir_a} trend; "
            f"{reg_b.get('name')} does not."
        )
    elif sig_b and not sig_a:
        verdict = "LOCALIZED SIGNAL"
        explanation = (
            f"{reg_b.get('name')} shows a significant {dir_b} trend "
            f"({slope_b:+.2f} {var.get('unit')}/dec); {reg_a.get('name')} does "
            f"not. The difference between them is not itself significant "
            f"(p = {p_diff:.3f})." if p_diff is not None else
            f"{reg_b.get('name')} shows a significant {dir_b} trend; "
            f"{reg_a.get('name')} does not."
        )
    else:
        verdict = "NO SIGNIFICANT DIFFERENCE"
        explanation = (
            f"The paired contrast does not show a statistically significant "
            f"change over time"
            + (f" (p = {p_diff:.3f})." if p_diff is not None else ".")
        )

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
        # the actual test the verdict is based on
        "p_diff": round(p_diff, 4) if p_diff is not None else None,
        "diff_z": round(diff_z, 3) if diff_z is not None else None,
        "diff_significant": diff_significant,
        "paired_difference_per_decade": paired.get("per_decade") if paired else None,
        "difference_method": "Calendar-aligned paired Sen/Mann-Kendall" if paired else "Independent OLS standard-error approximation",
        "common_years": common,
        "verdict": verdict,
        "explanation": explanation,
    }


def pearson_significance(r, n):
    """Compute Student's t-test p-value for Pearson correlation r."""
    if n < 4 or abs(r) >= 1.0 - 1e-9:
        return 0.0 if abs(r) >= 0.5 else 1.0
    denom = math.sqrt(max(1e-12, 1.0 - r * r))
    df = n - 2
    t = abs(r) * math.sqrt(df) / denom
    p = 2.0 * (1.0 - t_cdf(t, df))
    return max(0.0, min(1.0, p))


def explain_teleconnection(src_reg, src_var, dst_reg, dst_var, r, p):
    """Plain-English description of a discovered teleconnection.

    This is a *presentation* helper only: the relationship itself was found by
    the statistical pipeline in interconnect.py (lagged cross-correlation,
    partial correlation, Granger F-tests, FDR control). The wording here is
    derived purely from the computed sign and strength, so it can never assert
    a mechanism the data did not support.

    ``r`` is a unitless Pearson correlation on the -1..+1 scale, not a change
    in physical units, and ``p`` is evidence against a no-association model --
    not a measure of importance, danger or proof of causation. The returned
    text says both things explicitly so a reader cannot mistake the effect
    size, the significance and the interpretation for one another.
    """
    src = f"{src_var.get('name', 'the driver')} over {src_reg.get('name', 'the source region')}"
    dst = f"{dst_var.get('name', 'the response')} over {dst_reg.get('name', 'the target region')}"
    if r >= 0.65:
        head = (f"Strong in-phase association (r = {r:+.2f}, p = {p:.3f}): "
                f"{src} and {dst} tended to move together in the tested "
                f"series.")
    elif r <= -0.65:
        head = (f"Strong inverse association (r = {r:+.2f}, p = {p:.3f}): "
                f"{src} and {dst} tended to move in opposite directions in "
                f"the tested series.")
    elif r > 0:
        head = (f"Positive association (r = {r:+.2f}, p = {p:.3f}): {src} "
                f"tended to move with {dst}.")
    else:
        head = (f"Inverse association (r = {r:+.2f}, p = {p:.3f}): {src} "
                f"tended to move opposite to {dst}.")
    return head + (
        " The score is dimensionless on a -1 to +1 scale, not a change in "
        "measurement units. The p-value is evidence against a no-association "
        "model; it does not measure practical importance, danger or causation, "
        "and judging importance would need physical units plus exposure and "
        "context."
    )
