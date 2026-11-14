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
