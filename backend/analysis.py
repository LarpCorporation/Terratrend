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
        p = min(1.0, max(0.0, p))
        tcrit = _t_critical(0.975, df)
        lo = slope - tcrit * se
        hi = slope + tcrit * se

    return {
        "slope": slope, "intercept": intercept, "se": se,
        "t": t, "df": df, "p": p, "ci_low": lo, "ci_high": hi,
    }


def _t_critical(q, df):
    """Inverse Student's t CDF by bisection (q in (0,1))."""
    lo, hi = 0.0, 100.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if t_cdf(mid, df) < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


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
    ci_lo, ci_hi = theil_sen_ci(ys, xs)
    tt = t_test_trend(ys, xs)

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
        # classic OLS + t-test, reported alongside Mann-Kendall
        "t_slope": tt["slope"] if tt else None,
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
