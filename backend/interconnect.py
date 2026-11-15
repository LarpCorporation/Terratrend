"""Earth-system interconnectivity engine.

Everything in here is computed from the data — nothing is looked up from a
table of expected results:

  * decompose_monthly()   removes the seasonal cycle and the long-term trend,
                          leaving the "surprise" (anomaly) component of a series
  * cross_corr_best()     finds the lag that best aligns two series, which is
                          what turns a correlation into a direction
  * partial_corr()        screens out a shared confounder (e.g. temperature)
                          so a correlation survives only if it is direct
  * granger_f_test()      two-way lagged-regression F-test: does knowing X's
                          past help predict Y beyond Y's own past?
  * analyze_local_couplings()     pairs every variable against every other in
                                  ONE region and ranks who drives whom
  * anomaly_episodes()            finds when a region's variable ran above /
                                  below its own trend and by how much
  * impact_pair()                 lagged correlation + event compositing of a
                                  source anomaly against a remote variable

The human-readable mechanism sentences are generated from the computed
numbers (sign, lag, magnitude) plus a small physics vocabulary; the
detection itself is fully statistical.
"""
import math

from analysis import calculate_pearson, pearson_significance, _betai

ALPHA = 0.05
MIN_MONTHS = 36
DEFAULT_MAX_LAG = 6
GLOBAL_MAX_LAG = 24
MIN_LOCAL_R = 0.30       # effect-size gate for within-region couplings


def _mean(vs):
    vs = [v for v in vs if v is not None]
    return sum(vs) / len(vs) if vs else None


def _std(vs):
    vs = [v for v in vs if v is not None]
    if len(vs) < 2:
        return 0.0
    m = sum(vs) / len(vs)
    return math.sqrt(sum((v - m) ** 2 for v in vs) / (len(vs) - 1))


def _mask_pairs(xs, ys):
    idx = [i for i in range(min(len(xs), len(ys)))
           if xs[i] is not None and ys[i] is not None]
    return idx, [xs[i] for i in idx], [ys[i] for i in idx]


def _linear_fit(ys, xs=None):
    if xs is None:
        xs = list(range(len(ys)))
    n = len(ys)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx if sxx > 1e-12 else 0.0
    return slope, my - slope * mx


def _f_cdf(f, df1, df2):
    if f <= 0:
        return 0.0
    x = (df1 * f) / (df1 * f + df2)
    return _betai(df1 / 2.0, df2 / 2.0, x)


def _ols(Y, X):
    rows = [[1.0] + list(r) for r in X]
    n = len(rows)
    k = len(rows[0]) if rows else 0
    if n < k + 2 or k == 0:
        return None, None
    xtx = [[0.0] * k for _ in range(k)]
    xty = [0.0] * k
    for r, y in zip(rows, Y):
        for i in range(k):
            xty[i] += r[i] * y
            for j in range(k):
                xtx[i][j] += r[i] * r[j]
    a = [row[:] for row in xtx]
    b = xty[:]
    for col in range(k):
        piv = max(range(col, k), key=lambda i: abs(a[i][col]))
        if abs(a[piv][col]) < 1e-12:
            return None, None
        a[col], a[piv] = a[piv], a[col]
        b[col], b[piv] = b[piv], b[col]
        d = a[col][col]
        for j in range(col, k):
            a[col][j] /= d
        b[col] /= d
        for i in range(k):
            if i == col:
                continue
            f = a[i][col]
            if f == 0:
                continue
            for j in range(col, k):
                a[i][j] -= f * a[col][j]
            b[i] -= f * b[col]
    rss = 0.0
    for r, y in zip(rows, Y):
        pred = sum(r[i] * b[i] for i in range(k))
        rss += (y - pred) ** 2
    return b, rss


# --------------------------------------------------------------------------
# decomposition: seasonal cycle + trend + anomaly
# --------------------------------------------------------------------------
def _fit_decomposition(values):
    """Converged trend + seasonal climatology + residual series.

    This is the estimator behind decompose_monthly(), split out so callers
    that must reconstruct the fitted baseline exactly (anomaly_detail) can use
    the unrounded climatology. The numbers are identical to the public
    function: only the returned climatology is unrounded here.
    """
    n = len(values)
    if n < MIN_MONTHS:
        raise ValueError(f"need >= {MIN_MONTHS} months, got {n}")
    idx = [i for i, v in enumerate(values) if v is not None]
    if len(idx) < MIN_MONTHS:
        raise ValueError(f"need >= {MIN_MONTHS} valid months, got {len(idx)}")

    def step(slope, intercept):
        detr = [values[i] - (slope * i + intercept) if values[i] is not None
                else None for i in range(n)]
        clim = []
        for m in range(12):
            vs = [detr[i] for i in idx if i % 12 == m]
            clim.append(_mean(vs) if vs else 0.0)
        anom = [detr[i] - clim[i % 12] if detr[i] is not None else None
                for i in range(n)]
        return anom, clim

    slope, intercept = _linear_fit([values[i] for i in idx], idx)
    climatology = [0.0] * 12
    anomalies = [None] * n

    for _ in range(4):
        anomalies, climatology = step(slope, intercept)
        valid = [i for i in range(n) if anomalies[i] is not None]
        s2, i2 = _linear_fit([anomalies[i] for i in valid], valid)
        if abs(s2) < 1e-9:
            break
        slope += s2
        intercept += i2

    # final projection onto the converged trend
    anomalies, climatology = step(slope, intercept)

    return {
        "values": anomalies,
        "climatology": climatology,
        "trend_slope_per_month": slope,
        "trend_intercept": intercept,
        "residual_scale": _std(anomalies),
    }


def decompose_monthly(values):
    """Split a monthly series into trend + seasonal cycle + anomaly.

    Trend and climatology are estimated jointly by alternating projection:
    the linear trend is subtracted, the per-calendar-month mean is taken from
    what is left, the seasonal cycle is subtracted, and any slope still in the
    residual is folded back in. Estimating the climatology on the raw series
    instead would let a rising trend leak into the monthly means, so a series
    with a trend would leave a spurious curved residual behind.

    The fitted baseline for month ``i`` (calendar month ``m = i % 12``) is
    ``trend_slope_per_month * i + trend_intercept + climatology[m]``; the
    returned residuals are the observed values minus that baseline.
    ``trend_intercept`` is returned alongside the existing keys so callers can
    reconstruct the baseline without refitting anything.
    """
    fit = _fit_decomposition(values)
    return {
        "values": fit["values"],
        "climatology": [round(c, 4) if c is not None else None
                        for c in fit["climatology"]],
        "trend_slope_per_month": fit["trend_slope_per_month"],
        "trend_intercept": fit["trend_intercept"],
        "sigma": fit["residual_scale"] or 1.0,
    }


# --------------------------------------------------------------------------
# correlation toolkit
# --------------------------------------------------------------------------
def effective_sample_size(xs,ys):
    _,ax,ay=_mask_pairs(xs,ys)
    n=len(ax)
    if n<8:return float(n)
    rx=calculate_pearson(xs[:-1],xs[1:])
    ry=calculate_pearson(ys[:-1],ys[1:])
    product=max(0.,min(.99,rx*ry))
    return max(4.,min(float(n),n*(1-product)/(1+product)))


def cross_corr_best(xs, ys, max_lag=DEFAULT_MAX_LAG):
    _, ax, ay = _mask_pairs(xs, ys)
    if len(ax) < 8:
        return {"r": 0.0, "p": 1.0, "lag": 0, "r0": 0.0, "n": len(ax)}
    r0 = calculate_pearson(ax, ay)
    best = {"r": abs(r0), "p": pearson_significance(r0, effective_sample_size(xs,ys)),
            "lag": 0, "r0": r0, "n": len(ax)}
    for tau in range(-max_lag, max_lag + 1):
        if tau == 0:
            continue
        if tau > 0:
            xw = xs[:-tau]
            yw = ys[tau:]
        else:
            xw = xs[-tau:]
            yw = ys[:tau]
        _, bx, by = _mask_pairs(xw, yw)
        if len(bx) < 8:
            continue
        r = calculate_pearson(bx, by)
        p = pearson_significance(r, effective_sample_size(xw,yw))
        if abs(r) > best["r"]:
            best = {"r": abs(r), "p": p, "lag": tau, "r0": r, "n": len(bx)}
    best["r"] = round(best["r"], 4)
    # The maximum was selected from a family of lag tests. Bonferroni is
    # conservative but avoids treating the winning lag as prespecified.
    best["p_raw"] = best["p"]
    best["p"] = min(1.0, best["p"] * (2*max_lag+1))
    best["r0"] = round(best["r0"], 4)
    return best


def partial_corr(xs, ys, zs):
    idx, ax, ay = _mask_pairs(xs, ys)
    az = [zs[i] for i in idx if zs[i] is not None]
    ax = [ax[j] for j in range(len(ax)) if zs[idx[j]] is not None]
    ay = [ay[j] for j in range(len(ay)) if zs[idx[j]] is not None]
    if len(ax) < 8:
        return {"r": None, "p": None, "n": len(ax)}
    r_xy = calculate_pearson(ax, ay)
    r_xz = calculate_pearson(ax, az)
    r_yz = calculate_pearson(ay, az)
    denom = math.sqrt(max(1e-12, (1 - r_xz * r_xz) * (1 - r_yz * r_yz)))
    r = max(-1.0, min(1.0, (r_xy - r_xz * r_yz) / denom))
    return {
        "r": round(r, 4),
        "p": round(pearson_significance(r, len(ax)), 5),
        "n": len(ax),
    }


def granger_f_test(xs, ys, lag=3):
    # Keep calendar lags intact: use the longest complete contiguous block.
    blocks, block = [], []
    for x,y in zip(xs,ys):
        if x is None or y is None:
            if block:blocks.append(block)
            block=[]
        else:block.append((x,y))
    if block:blocks.append(block)
    longest=max(blocks,key=len,default=[])
    ax=[p[0] for p in longest];ay=[p[1] for p in longest]
    n = len(ax)
    if n < lag * 3 + 4:
        return None, None

    def test(driver, target):
        y = target[lag:]
        xr = [[target[t - 1 - i] for i in range(lag)] for t in range(lag, n)]
        xu = [row + [driver[t - 1 - i] for i in range(lag)] for t, row in
              zip(range(lag, n), xr)]
        _, rss_r = _ols(y, xr)
        _, rss_u = _ols(y, xu)
        if rss_r is None or rss_u is None or rss_u <= 1e-12:
            return None
        df1 = lag
        df2 = n - 2 * lag - 1
        if df2 <= 0:
            return None
        f = ((rss_r - rss_u) / df1) / (rss_u / df2)
        if f <= 0:
            return 1.0
        return 1.0 - _f_cdf(f, df1, df2)

    return test(ax, ay), test(ay, ax)


# --------------------------------------------------------------------------
# local coupling: every variable pair inside ONE region
# --------------------------------------------------------------------------
def _strength_label(abs_r):
    """Band label for the magnitude of a unitless correlation score.

    ``abs_r`` is |r| on the -1..+1 correlation scale (the engine passes the
    absolute lagged Pearson correlation). The label describes how strong the
    linear association is in that dimensionless score; it is not a physical
    effect size and does not mean the variables changed by that many units.
    The thresholds and returned words are unchanged for existing callers.
    """
    if abs_r >= 0.65:
        return "STRONG"
    if abs_r >= 0.45:
        return "MODERATE"
    return "WEAK"


def analyze_local_couplings(region, series_by_var, months, confounder="T2M"):
    decomps = {}
    for vid, values in series_by_var.items():
        usable = [v for v in values if v is not None]
        if len(usable) < MIN_MONTHS:
            continue
        try:
            decomps[vid] = decompose_monthly(values)
        except ValueError:
            continue

    confound = decomps.get(confounder, {}).get("values") if confounder else None

    var_ids = list(decomps.keys())
    pairs = []
    family=[]
    for i in range(len(var_ids)):
        for j in range(i + 1, len(var_ids)):
            a, b = var_ids[i], var_ids[j]
            ax = decomps[a]["values"]
            by = decomps[b]["values"]

            ccf = cross_corr_best(ax, by)
            if ccf["n"] < 8:
                continue
            part = partial_corr(ax, by, confound) if confound is not None and confounder not in {a,b} \
                else {"r": None, "p": None, "n": ccf["n"]}
            g_ab, g_ba = granger_f_test(ax, by)
            discovery_p=min(1.,2*min(ccf["p"],part["p"] if part["p"] is not None else 1.))
            family.append(discovery_p)

            lag = ccf["lag"]
            if lag > 1:
                driver, response, lag_note = a, b, f"{a} leads {b} by {lag} months"
            elif lag < -1:
                driver, response, lag_note = b, a, f"{b} leads {a} by {-lag} months"
            else:
                if g_ab is not None and g_ba is not None:
                    if g_ab < g_ba and g_ab < ALPHA:
                        driver, response, lag_note = a, b, \
                            (f"No resolved lag; in-sample Granger screen: {a} "
                             f"predicts {b} (p={g_ab:.3f})")
                    elif g_ba < g_ab and g_ba < ALPHA:
                        driver, response, lag_note = b, a, \
                            (f"No resolved lag; in-sample Granger screen: {b} "
                             f"predicts {a} (p={g_ba:.3f})")
                    else:
                        driver, response, lag_note = None, None, \
                            "Simultaneous — no clear lead"
                else:
                    driver, response, lag_note = None, None, \
                        "Simultaneous — no clear lead"

            # Effect size is a hard gate, not a nicety. With ~260 monthly
            # samples a |r| of 0.18 is already "significant", so a p-value
            # alone would report almost every pair as a discovery. A coupling
            # must also explain a meaningful share of variance.
            if abs(ccf["r"]) < MIN_LOCAL_R:
                continue
            if ccf["p"]>=ALPHA:
                driver,response,lag_note=None,None,"Association without a supported temporal lead"
            if ccf["p"] >= ALPHA and (part["p"] is None or part["p"] >= ALPHA):
                continue

            conf = 0
            if ccf["p"] < ALPHA:
                conf += 1
            if part["p"] is not None and part["p"] < ALPHA:
                conf += 1
            if (g_ab is not None and g_ab < ALPHA) or (g_ba is not None and g_ba < ALPHA):
                conf += 1
            # a coupling that disappears once temperature is controlled is
            # reported, but never with high confidence
            if part["r"] is not None and abs(part["r"]) < 0.15:
                conf = min(conf, 1)
            confidence = "HIGH" if conf >= 3 else ("MEDIUM" if conf == 2 else "LOW")

            pairs.append({
                "a": a,
                "b": b,
                "r": round(ccf["r0"], 3),
                "r_lagged": round(ccf["r"], 3),
                "p": round(ccf["p"], 5),
                "p_discovery": discovery_p,
                "lag_months": lag,
                "driver": driver,
                "response": response,
                "lag_note": lag_note,
                "r_partial": part["r"],
                "p_partial": part["p"],
                # named so describe_coupling can say what the partial
                # correlation actually controlled for
                "control": (confounder if part["r"] is not None else None),
                "granger_a_b": round(g_ab, 5) if g_ab is not None else None,
                "granger_b_a": round(g_ba, 5) if g_ba is not None else None,
                "phase": "in_phase" if ccf["r0"] > 0 else "divergent",
                "strength": _strength_label(ccf["r"]),
                "confidence": confidence,
            })

    for pair in pairs:
        pair["p_adjusted"]=bh_adjusted_p(pair["p_discovery"],family)
    pairs=[p for p in pairs if p["p_adjusted"]<=.10]
    pairs.sort(key=lambda p: (
        0 if p["p"] < ALPHA else 1,
        -(abs(p["r_lagged"]) if p["p"] < ALPHA else abs(p["r_partial"] or 0)),
    ))
    return pairs


# --------------------------------------------------------------------------
# anomaly narrative: when did a variable run above / below its own trend
# --------------------------------------------------------------------------
ZERO_VARIANCE_EPS = 1e-12


def _month_label(value):
    """Canonical YYYY-MM label for the app's month indexing.

    The application stores months either as YYYYMM integers (e.g. 200501) or
    as already-formatted YYYY-MM strings; both normalise to one sortable form.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        year, month = divmod(value, 100)
        if 1 <= month <= 12:
            return f"{year:04d}-{month:02d}"
    return str(value)


def _window_indices(months, start, end):
    """Indices of months inside the inclusive [start, end] label window."""
    lo = _month_label(start) if start is not None else None
    hi = _month_label(end) if end is not None else None
    out = []
    for i, label in enumerate(months):
        text = _month_label(label)
        if lo is not None and text < lo:
            continue
        if hi is not None and text > hi:
            continue
        out.append(i)
    return out


def _baseline_period(values, months):
    """The span actually passed in, with valid/missing month counts."""
    valid = sum(1 for v in values if v is not None)
    labels = months[:len(values)]
    return {
        "first_month": labels[0] if labels else None,
        "last_month": labels[-1] if labels else None,
        "valid_months": valid,
        "missing_months": len(values) - valid,
    }


def _zero_residual_scale(scale, values):
    """True when the residual scale is numerically degenerate, not float noise.

    A tiny absolute scale is still allowed for series measured in tiny units;
    the test is relative to the magnitude of the series and falls back to a
    small absolute epsilon for series near zero.
    """
    if scale is None or scale <= 0.0:
        return True
    peak = max((abs(v) for v in values if v is not None), default=0.0)
    return scale <= ZERO_VARIANCE_EPS * max(1.0, peak)


def anomaly_episodes(values, months, sigma=1.0):
    """Contiguous runs of months that sit beyond a threshold on one side.

    ``sigma`` is the threshold expressed in the same units as ``values``. The
    usual call passes residual departures already divided by their own residual
    standard deviation, so ``sigma=1.0`` means one standard deviation and every
    returned figure is in sigma units.

    An episode is closed by a month that does not qualify, by a change of side,
    and by a missing month (a gap). The completed episode is always returned;
    observations are never joined across a gap. An episode still open on the
    last available observation is marked ``truncated``.

    Each episode:
        side: "above" | "below"
        start, end: first and last month labels of the episode
        months: number of qualifying consecutive observations
        peak_sigma: signed extreme departure (largest for above, deepest for
            below)
        peak_month: month of that extreme
        mean_sigma: signed mean departure across the episode
        threshold_sigma: the threshold used, in the units of ``values``
        truncated: True only when the run is still open at the end of the
            series (a trailing gap closes the run instead)
    """
    if len(months) < len(values):
        raise ValueError("months must label every value")
    threshold = float(sigma)
    episodes = []

    def close(current, truncated):
        count = current.get("n")
        total = current.pop("_sum")
        current["months"] = count
        current["n"] = count  # retained: earlier callers read the run length as `n`
        current["mean_sigma"] = total / count
        current["threshold_sigma"] = threshold
        current["truncated"] = truncated
        episodes.append(current)

    current = None
    for i, v in enumerate(values):
        if v is None:
            if current is not None:
                close(current, False)
                current = None
            continue
        side = "above" if v > threshold else ("below" if v < -threshold else None)
        if side is None:
            if current is not None:
                close(current, False)
                current = None
            continue
        if current is None or current["side"] != side:
            if current is not None:
                close(current, False)
            current = {
                "side": side,
                "start": months[i],
                "end": months[i],
                "n": 1,
                "peak_sigma": v,
                "peak_month": months[i],
                "_sum": v,
            }
            continue
        current["end"] = months[i]
        current["n"] += 1
        current["_sum"] += v
        if ((side == "above" and v > current["peak_sigma"]) or
                (side == "below" and v < current["peak_sigma"])):
            current["peak_sigma"] = v
            current["peak_month"] = months[i]

    if current is not None:
        # Only reachable when the final observation itself qualifies: any
        # trailing gap or neutral month would already have closed the run.
        close(current, True)
    return episodes


def _episodes_in_sigma(eps):
    """Copy an episode list with display-rounded numbers (no raw values left)."""
    out = []
    for e in eps:
        out.append({
            "side": e["side"],
            "start": e["start"],
            "end": e["end"],
            "months": e["months"],
            "peak_sigma": round(e["peak_sigma"], 2),
            "peak_month": e["peak_month"],
            "mean_sigma": round(e["mean_sigma"], 2),
            "threshold_sigma": e["threshold_sigma"],
            "truncated": e["truncated"],
        })
    return out


def _anomaly_narrative(total, above, below, peak_sigma, peak_month, n_eps):
    if total == 0:
        return "Not enough data."
    pct = 100.0 * above / total
    bits = [
        f"ran above its own trend in {above} of {total} months ({pct:.0f}%)",
    ]
    if below:
        bits.append(f"below it in {below}")
    if abs(peak_sigma) > 0:
        sign = "+" if peak_sigma > 0 else ""
        bits.append(f"peak {sign}{peak_sigma:.1f}\u03c3 in {peak_month}")
    if n_eps:
        bits.append(f"across {n_eps} distinct episodes")
    return "; ".join(bits) + "."


def _side_narrative(above, below, total, eps_above, eps_below):
    """Plain sentences for the two sides of the baseline (never a hazard claim)."""
    parts = []
    if above:
        peak = max(e["peak_sigma"] for e in eps_above) if eps_above else None
        text = (f"Above-baseline: {above} of {total} valid months sat more than "
                f"one standard deviation above the fitted baseline")
        if peak is not None:
            text += f", peaking at {peak:+.1f}\u03c3"
        text += f", in {len(eps_above)} episode{'s' if len(eps_above) != 1 else ''}."
        parts.append(text)
    else:
        parts.append("Above-baseline: no month sat more than one standard "
                     "deviation above the fitted baseline.")
    if below:
        peak = min(e["peak_sigma"] for e in eps_below) if eps_below else None
        text = (f"Below-baseline: {below} of {total} valid months sat more than "
                f"one standard deviation below the fitted baseline")
        if peak is not None:
            text += f", reaching {peak:+.1f}\u03c3"
        text += f", in {len(eps_below)} episode{'s' if len(eps_below) != 1 else ''}."
        parts.append(text)
    else:
        parts.append("Below-baseline: no month sat more than one standard "
                     "deviation below the fitted baseline.")
    parts.append("These are departures from this series' own fitted baseline; "
                 "they are not an extreme-event or hazard assessment and they do "
                 "not attribute a cause.")
    return " ".join(parts)


def anomaly_report(values, months):
    """Summary of one residual series against its own fitted baseline.

    The scale is the sample standard deviation of the residual series itself
    and the threshold is one residual standard deviation, matching the
    decomposition the application already uses. ``status`` is one of
    ``ok``, ``insufficient_data`` or ``zero_variance``; the latter two report
    no threshold counts instead of inventing a zero.
    """
    usable = [(i, v) for i, v in enumerate(values) if v is not None]
    if not usable:
        return None
    if len(months) < len(values):
        raise ValueError("months must label every value")
    labels = list(months[:len(values)])
    period = _baseline_period(values, labels)
    threshold_sigma = 1.0

    if len(usable) < MIN_MONTHS:
        narrative = (f"Only {len(usable)} valid months are available; at least "
                     f"{MIN_MONTHS} are needed before anomalies can be assessed.")
        return {
            "status": "insufficient_data",
            "sigma": None,
            "threshold_sigma": threshold_sigma,
            "months_above": None,
            "months_below": None,
            "total_months": len(usable),
            "peak_sigma": None,
            "peak_month": None,
            "episodes": [],
            "episodes_above": 0,
            "episodes_below": 0,
            "baseline_period": period,
            "narrative": narrative,
            "side_narrative": narrative,
        }

    sigma = _std([v for _, v in usable])
    if _zero_residual_scale(sigma, values):
        narrative = ("The residual series has effectively zero variance after "
                     "the seasonal cycle and fitted trend are removed, so a "
                     "threshold in standard-deviation units is undefined; no "
                     "episodes are reported. This is not a claim that no "
                     "anomalies occurred, only that this diagnostic has no "
                     "scale to measure them against.")
        return {
            "status": "zero_variance",
            "sigma": 0.0,
            "threshold_sigma": threshold_sigma,
            "months_above": None,
            "months_below": None,
            "total_months": len(usable),
            "peak_sigma": None,
            "peak_month": None,
            "episodes": [],
            "episodes_above": 0,
            "episodes_below": 0,
            "baseline_period": period,
            "narrative": narrative,
            "side_narrative": narrative,
        }

    above = [v for _, v in usable if v > sigma]
    below = [v for _, v in usable if v < -sigma]
    z = [None if v is None else v / sigma for v in values]
    eps = anomaly_episodes(z, labels, threshold_sigma)
    eps_above = [e for e in eps if e["side"] == "above"]
    eps_below = [e for e in eps if e["side"] == "below"]
    peak = max((v for _, v in usable), key=lambda v: abs(v))
    peak_i = next(i for i, v in usable if abs(v - peak) < 1e-9)

    return {
        "status": "ok",
        "sigma": round(sigma, 4),
        "threshold_sigma": threshold_sigma,
        "months_above": len(above),
        "months_below": len(below),
        "total_months": len(usable),
        "peak_sigma": round(peak / sigma, 2),
        "peak_month": labels[peak_i],
        "episodes": _episodes_in_sigma(eps),
        "episodes_above": len(eps_above),
        "episodes_below": len(eps_below),
        "baseline_period": period,
        "narrative": _anomaly_narrative(len(usable), len(above), len(below),
                                        peak / sigma, labels[peak_i], len(eps)),
        "side_narrative": _side_narrative(len(above), len(below), len(usable),
                                          eps_above, eps_below),
    }


def anomaly_detail(values, months, *, sigma=1.0, start=None, end=None):
    """Per-month drill-down for one raw monthly series.

    ``values`` is the observed monthly series (not a pre-computed residual
    list): its seasonal climatology and linear trend are fitted once, on the
    whole supplied series, by the same decomposition ``decompose_monthly``
    exposes. ``expected`` is the fitted baseline reconstructed for each month
    as ``slope * i + intercept + climatology[i % 12]``, and ``departure`` is the
    observed value minus that baseline. ``start``/``end`` (inclusive YYYY-MM
    labels, or YYYYMM integers) only restrict which months are reported and
    which episodes are listed; the baseline is therefore the same one used for
    the whole series and a window never silently re-fits a different baseline.

    ``sigma`` is the episode threshold in residual standard deviations
    (``1.0`` = one standard deviation). Nothing is imputed for a missing month
    except the fitted baseline value itself; observed/departure/sigma_units are
    null there.

    Statuses:
        ``ok``: a baseline and residual scale exist.
        ``insufficient_data``: fewer than ``MIN_MONTHS`` valid months, so no
            baseline is fitted and expected/departure fields are null.
        ``zero_variance``: the residuals are numerically constant, so a
            threshold in sigma units is undefined; no episodes are reported.
    """
    n = len(values)
    if len(months) < n:
        raise ValueError("months must label every value")
    labels = list(months[:n])
    threshold_sigma = float(sigma)
    period = _baseline_period(values, labels)
    window = _window_indices(labels, start, end)
    window_rows = [{"month": labels[i],
                    "observed": values[i],
                    "expected": None,
                    "departure": None,
                    "sigma_units": None} for i in window]
    valid_in_window = sum(1 for r in window_rows if r["observed"] is not None)

    def summary(above, below, eps, peak_sigma=None, peak_month=None):
        return {
            "period_start": window_rows[0]["month"] if window_rows else None,
            "period_end": window_rows[-1]["month"] if window_rows else None,
            "total_months": len(window_rows),
            "valid_months": valid_in_window,
            "missing_months": len(window_rows) - valid_in_window,
            "months_above": above,
            "months_below": below,
            "episodes_above": sum(1 for e in eps if e["side"] == "above"),
            "episodes_below": sum(1 for e in eps if e["side"] == "below"),
            "peak_sigma": peak_sigma,
            "peak_month": peak_month,
        }

    if n < MIN_MONTHS or period["valid_months"] < MIN_MONTHS:
        return {
            "status": "insufficient_data",
            "baseline": None,
            "months": window_rows,
            "episodes": [],
            "summary": summary(None, None, []),
            "baseline_period": period,
            "threshold_sigma": threshold_sigma,
            "message": (f"At least {MIN_MONTHS} valid months are needed to fit "
                        f"the baseline; {period['valid_months']} are available."),
        }

    try:
        fit = _fit_decomposition(values)
    except ValueError as exc:
        return {
            "status": "insufficient_data",
            "baseline": None,
            "months": window_rows,
            "episodes": [],
            "summary": summary(None, None, []),
            "baseline_period": period,
            "threshold_sigma": threshold_sigma,
            "message": str(exc),
        }

    slope = fit["trend_slope_per_month"]
    intercept = fit["trend_intercept"]
    climatology = fit["climatology"]
    scale = fit["residual_scale"]
    zero = _zero_residual_scale(scale, values)
    threshold_value = None if zero else threshold_sigma * scale

    expected = [slope * i + intercept + climatology[i % 12]
                for i in range(n)]
    z = [None] * n
    for i, observed in enumerate(values):
        if observed is None:
            continue
        z[i] = None if zero else fit["values"][i] / scale

    rows = []
    for i in window:
        observed = values[i]
        departure = observed - expected[i] if observed is not None else None
        rows.append({
            "month": labels[i],
            "observed": observed,
            "expected": expected[i],
            "departure": departure,
            "sigma_units": (departure / scale
                            if departure is not None and not zero else None),
        })

    in_window = set(window)
    windowed_z = [z[i] if i in in_window else None for i in range(n)]
    eps = [] if zero else anomaly_episodes(windowed_z, labels, threshold_sigma)

    valid_rows = [r for r in rows if r["observed"] is not None]
    if zero or not valid_rows:
        months_above = months_below = None
        peak_sigma = peak_month = None
    else:
        months_above = sum(1 for r in valid_rows
                           if r["sigma_units"] > threshold_sigma)
        months_below = sum(1 for r in valid_rows
                           if r["sigma_units"] < -threshold_sigma)
        peak_row = max(valid_rows, key=lambda r: abs(r["sigma_units"]))
        peak_sigma = round(peak_row["sigma_units"], 2)
        peak_month = peak_row["month"]

    if start is not None or end is not None:
        # A window clips episodes to the visible months; truncation is still
        # reported only for a run that reaches the end of the supplied series.
        if not window:
            eps = []

    scale_text = ("effectively zero" if zero else f"{scale:.6g} in the series' "
                  "own units")
    description = (
        f"Baseline from {period['first_month']} to {period['last_month']}: "
        f"each calendar month's own climatology plus a linear trend fitted "
        f"jointly to the whole series by alternating projection "
        f"({period['valid_months']} valid of {len(values)} months). The "
        f"residual scale is the sample standard deviation of the residuals "
        f"(sigma = {scale_text}); an episode is a run of months more than "
        f"{threshold_sigma:g} sigma from this baseline. This baseline is "
        f"internal to this series: it is not an external reference "
        f"climatology and it does not identify a cause."
    )
    baseline = {
        "description": description,
        "period_start": period["first_month"],
        "period_end": period["last_month"],
        "valid_months": period["valid_months"],
        "missing_months": period["missing_months"],
        "method": ("Monthly climatology + linear trend fitted jointly by "
                   "alternating projection; residual scale = sample standard "
                   "deviation of the residuals."),
        "trend_slope_per_month": slope,
        "trend_intercept": intercept,
        "climatology": [round(c, 4) for c in climatology],
        "residual_sigma": scale,
        "threshold_sigma": threshold_sigma,
        "threshold_value": threshold_value,
        "units_note": ("Numbers are in the units of the supplied residual "
                       "series; sigma_units are unitless multiples of the "
                       "residual scale."),
    }

    return {
        "status": "zero_variance" if zero else "ok",
        "baseline": baseline,
        "months": rows,
        "episodes": _episodes_in_sigma(eps),
        "summary": summary(months_above, months_below, eps,
                           peak_sigma, peak_month),
        "baseline_period": period,
        "threshold_sigma": threshold_sigma,
    }


# --------------------------------------------------------------------------
# global impacts: lagged + composite response of remote regions
# --------------------------------------------------------------------------
def impact_pair(src_anom, tgt_anom, months, max_lag=GLOBAL_MAX_LAG):
    _, ax, ay = _mask_pairs(src_anom, tgt_anom)
    if len(ax) < MIN_MONTHS:
        return None
    ccf = cross_corr_best(src_anom, tgt_anom, max_lag=max_lag)
    if ccf["n"] < 24:
        return None

    src_sigma = _std(src_anom) or 1.0
    tgt_sigma = _std(tgt_anom) or 1.0

    during, outside = [], []
    lag = ccf["lag"]
    for i in range(len(src_anom)):
        j=i+lag
        if j<0 or j>=len(tgt_anom) or src_anom[i] is None or tgt_anom[j] is None:
            continue
        (during if src_anom[i] > src_sigma else outside).append(tgt_anom[j])
    if not during or not outside:
        return None

    mean_during = sum(during) / len(during)
    mean_outside = sum(outside) / len(outside)
    delta = mean_during - mean_outside
    effect_sigma = delta / tgt_sigma

    lag = ccf["lag"]
    if lag > 0:
        lead_note = f"source leads by {lag} months"
    elif lag < 0:
        lead_note = f"target leads by {-lag} months"
    else:
        lead_note = "simultaneous"

    return {
        "r": round(ccf["r0"], 3),
        "r_lagged": round(ccf["r"], 3),
        "p": round(ccf["p"], 5),
        "lag_months": lag,
        "lead_note": lead_note,
        "n": ccf["n"],
        "composite": {
            "n_surge_months": len(during),
            "mean_during_sigma": round(mean_during / tgt_sigma, 2),
            "mean_outside_sigma": round(mean_outside / tgt_sigma, 2),
            "effect_sigma": round(effect_sigma, 2),
        },
    }


def mechanism_sentence(src_reg, src_var, tgt_reg, tgt_var, diag):
    comp = diag["composite"]
    r = diag["r_lagged"]
    sign = "in step with" if r > 0 else "opposite to"
    lag_txt = diag["lead_note"] if diag["lag_months"] != 0 else "at the same time as"
    eff = comp["effect_sigma"]
    eff_txt = (f"{eff:+.1f}\u03c3" if eff != 0 else "no net change")
    pieces = [
        f"{src_var['name']} over {src_reg['name']} moves {sign} "
        f"{tgt_var['name']} over {tgt_reg['name']} ({lag_txt}, r={r:+.2f}, "
        f"p={diag['p']:.3f}).",
        f"During {src_var['name']} surges above trend "
        f"({comp['n_surge_months']} months), {tgt_var['name']} there sat "
        f"{eff_txt} against its own baseline \u2014 ",
    ]
    if abs(eff) >= 0.5:
        pieces.append("a measurable remote response.")
    else:
        pieces.append("a weak remote response.")
    return " ".join(pieces)


def bh_adjusted_p(p, family):
    ordered=sorted(family)
    if not ordered:return 1.0
    return min(1.0,min(value*len(ordered)/(i+1) for i,value in enumerate(ordered) if value>=p))


def conditional_driver_model(target, candidates, max_drivers=4):
    """Exploratory joint lagged model; conditional prediction, not attribution.

    Includes three target-history terms. Complete regression rows retain their
    original monthly coordinates. Each candidate is tested by removing its
    term from the joint model, with BH correction across retained candidates.
    No independent validation is claimed for this in-sample diagnostic.
    """
    unique=[]
    for c in candidates:
        if c["id"] not in [p["id"] for p in unique]:unique.append(c)
    chosen=unique[:max_drivers]
    if not chosen:return {"ok":False,"reason":"No directional candidates with joint coverage"}
    lags=[max(1,min(24,int(c["lag"]))) for c in chosen]
    Y,X=[],[]
    for t in range(max(3,max(lags)),len(target)):
        if target[t] is None:continue
        row=[target[t-i] for i in (1,2,3)]
        row += [c["values"][t-lag] if t-lag<len(c["values"]) else None for c,lag in zip(chosen,lags)]
        if any(v is None for v in row):continue
        Y.append(target[t]);X.append(row)
    if len(Y)<max(36,8*(len(chosen)+4)):
        return {"ok":False,"reason":"Not enough overlapping months for a joint model"}
    beta,rss=_ols(Y,X)
    if beta is None or rss is None or rss<=1e-12:
        return {"ok":False,"reason":"Predictors are collinear or the fit is degenerate"}
    df=len(Y)-len(X[0])-1
    rows=[]
    target_sd=_std(Y) or 1.
    for i,c in enumerate(chosen):
        col=3+i
        _,reduced=_ols(Y,[r[:col]+r[col+1:] for r in X])
        if reduced is None:continue
        f=max(0.,(reduced-rss)/(rss/df))
        p=max(0.,min(1.,1-_f_cdf(f,1,df)))
        rows.append({"id":c["id"],"lag_months":lags[i],"p":p,
            "standardized_coefficient":beta[col+1]*(_std([r[col] for r in X]) or 1.)/target_sd})
    family=[r["p"] for r in rows]
    for row in rows:
        row["p_adjusted"]=bh_adjusted_p(row["p"],family)
        row["significant"]=row["p_adjusted"]<.05
    total=sum((y-_mean(Y))**2 for y in Y)
    return {"ok":True,"n":len(Y),"drivers":rows,"r_squared":max(0.,1-rss/total) if total else 0.,
        "evidence":"Exploratory conditional prediction; in-sample, candidate-selected, physical causation not established",
        "method":"Joint lagged regression with 3 target-history terms; conditional F tests; BH across candidates"}


def benjamini_hochberg(pvals, q=0.10):
    """Benjamini-Hochberg FDR control.

    Returns the largest k such that p_(k) <= k/m*q, i.e. how many of the
    sorted-by-p candidates survive. Scanning dozens of region/variable pairs
    at p<0.05 will always surface a few coincidences, so a discovery is only
    reported if it survives the expected false-discovery rate across the
    whole family of tests that produced it.
    """
    m = len(pvals)
    if m == 0:
        return 0
    order = sorted(range(m), key=lambda i: pvals[i])
    survive = 0
    for rank, i in enumerate(order, start=1):
        if pvals[i] <= (rank / m) * q:
            survive = rank
    return survive



def describe_coupling(a, b, pair):
    """A specific, computed description for an uncatalogued variable pair.

    This is a presentation helper for the diagnostics in
    analyze_local_couplings(), whose method it states explicitly:

    * both series have their monthly seasonal cycle and their jointly fitted
      linear trend removed by decompose_monthly() before anything is compared;
    * the score is the Pearson correlation of those monthly residual series,
      taken at the best lag of the lag search (cross_corr_best);
    * its p-value uses an autocorrelation-adjusted effective sample size and
      is widened for the family of lag positions that were searched;
    * when a confounder series is available and is not one of the pair, a
      first-order partial correlation of the residuals also controls for it;
    * p_adjusted, when present, is the false-discovery correction across the
      tested pair family; a two-way Granger screen is reported separately.

    The correlation is dimensionless: r = -1..+1 on the residual scale, not a
    change in the variables' physical units. Nothing is asserted that was not
    tested, and no mechanism is invented from the sign alone.
    """
    name_a = a.get("name", "variable A")
    name_b = b.get("name", "variable B")
    lag = int(pair.get("lag_months") or 0)
    signed = pair.get("r")
    if signed is None:
        signed = pair.get("r_lagged")
    signed = float(signed or 0.0)
    lagged = pair.get("r_lagged")
    magnitude = abs(float(lagged if lagged is not None else signed))
    p = pair.get("p")
    p = 1.0 if p is None else max(0.0, min(1.0, float(p)))
    p_adj = pair.get("p_adjusted")
    partial = pair.get("r_partial")
    partial_p = pair.get("p_partial")
    control = pair.get("control")
    ga, gb = pair.get("granger_a_b"), pair.get("granger_b_a")

    def p_text(value):
        return "p<0.001" if value < .001 else f"p={value:.3f}"

    parts = []

    # Temporal order: only the lag search can support a lead. A lag that the
    # test did not resolve is reported as simultaneous, never as an arrow.
    lag_resolved = abs(lag) > 1 and p < ALPHA
    if lag_resolved:
        leader, follower = (name_a, name_b) if lag > 0 else (name_b, name_a)
        parts.append(f"{leader} leads {follower} by {abs(lag)} "
                     f"month{'s' if abs(lag) != 1 else ''} in the lagged "
                     f"residual comparison.")
    elif lag:
        parts.append(f"The lag search placed the best overlap {lag:+d} months "
                     f"apart, but that lag does not pass the significance "
                     f"threshold, so no temporal lead is claimed; treat the "
                     f"pair as simultaneous.")
    else:
        parts.append(f"{name_a} and {name_b} line up in the same month: no "
                     f"temporal lead was resolved by the lag test "
                     f"(simultaneous).")

    if signed > 0:
        direction = ("positive, so the two residual series tended to move "
                     "together")
    elif signed < 0:
        direction = ("negative, so the two residual series tended to move in "
                     "opposite directions")
    else:
        direction = "near zero, so a linear relationship was not detected"
    method = (
        f"The relationship is a unitless score on a scale from -1 to +1: "
        f"r={signed:+.2f} ({direction}). It is the Pearson correlation of the "
        f"monthly residuals after each series' monthly seasonal cycle and "
        f"jointly fitted linear trend were removed, evaluated at the selected "
        f"lag. It is not a change of {abs(signed):.2f} measurement units in "
        f"either variable, and the sign of a correlation is not a mechanism."
    )
    parts.append(method)

    # Method transparency: effective sample size and the two multiple-test
    # corrections actually applied by analyze_local_couplings().
    parts.append(
        "Its significance is tested with an autocorrelation-adjusted "
        "effective sample size rather than the raw month count; the lag-test "
        "p-value is widened for the family of lag positions searched"
        + (", and p_adjusted applies false-discovery control across the "
           "tested pair family." if p_adj is not None else ".")
    )

    if partial is not None:
        control_text = (f"the {control} residual series" if control
                        else "a supplied confounder residual series")
        extra = f" ({p_text(float(partial_p))})" if partial_p is not None else ""
        if abs(partial) < 0.15:
            parts.append(
                f"The reported score is the unadjusted residual correlation; "
                f"a first-order partial correlation controlling for "
                f"{control_text} leaves r={partial:+.2f}{extra}, so most of "
                f"the association is shared with that control. That is a "
                f"statistical screen, not an identified mechanism.")
        elif abs(partial) < magnitude * 0.7:
            parts.append(
                f"The reported score is the unadjusted residual correlation; "
                f"a first-order partial correlation controlling for "
                f"{control_text} leaves r={partial:+.2f}{extra}, so part of "
                f"the association is shared with that control.")
        else:
            parts.append(
                f"The reported score is the unadjusted residual correlation; "
                f"a first-order partial correlation controlling for "
                f"{control_text} leaves r={partial:+.2f}{extra}, so the "
                f"association is not explained by that control; other shared "
                f"influences may still be present.")
    else:
        parts.append("No confounder-controlled partial correlation was "
                     "available for this pair, so no partial-correlation "
                     "claim is made.")

    adjusted = ""
    if p_adj is not None:
        adjusted = (f", and the across-pair false-discovery-adjusted "
                    f"{p_text(float(p_adj))}")
    parts.append(
        f"The reported {p_text(p)} (after the lag-family adjustment)"
        f"{adjusted} describe evidence against a no-association model for "
        f"these residual series. They are not measures of importance, danger "
        f"or causation; judging practical importance would also need the "
        f"relationship expressed in the variables' physical units plus "
        f"exposure and context."
    )

    parts.append(
        f"The squared score (r\u00b2\u2248{magnitude * magnitude:.2f}, about "
        f"{magnitude * magnitude * 100:.0f}%) is the share of shared linear "
        f"variation between the tested residual series only; it is not the "
        f"fraction physically caused by one variable of the other."
    )

    if not lag_resolved and (ga is not None or gb is not None):
        if ga is not None and ga < ALPHA and (gb is None or ga < gb):
            parts.append(
                f"A separate in-sample lagged-regression (Granger) screen "
                f"found that {name_a}'s past adds predictive information "
                f"about {name_b} (p={ga:.3f}); that is predictive ordering "
                f"from one in-sample test, not evidence of a causal chain.")
        elif gb is not None and gb < ALPHA:
            parts.append(
                f"A separate in-sample lagged-regression (Granger) screen "
                f"found that {name_b}'s past adds predictive information "
                f"about {name_a} (p={gb:.3f}); that is predictive ordering "
                f"from one in-sample test, not evidence of a causal chain.")
        else:
            parts.append("Neither lagged-regression direction test passed its "
                         "threshold, so the temporal ordering is unresolved.")

    parts.append("This exploratory association does not establish physical "
                 "causation or attribute the long-term trend.")

    return " ".join(parts)

