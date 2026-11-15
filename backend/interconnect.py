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
def decompose_monthly(values):
    """Split a monthly series into trend + seasonal cycle + anomaly.

    Trend and climatology are estimated jointly by alternating projection:
    the linear trend is subtracted, the per-calendar-month mean is taken from
    what is left, the seasonal cycle is subtracted, and any slope still in the
    residual is folded back in. Estimating the climatology on the raw series
    instead would let a rising trend leak into the monthly means, so a series
    with a trend would leave a spurious curved residual behind.
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

    sigma = _std(anomalies) or 1.0
    return {
        "values": anomalies,
        "climatology": [round(c, 4) if c is not None else None
                        for c in climatology],
        "trend_slope_per_month": slope,
        "sigma": sigma,
    }


# --------------------------------------------------------------------------
# correlation toolkit
# --------------------------------------------------------------------------
def cross_corr_best(xs, ys, max_lag=DEFAULT_MAX_LAG):
    _, ax, ay = _mask_pairs(xs, ys)
    if len(ax) < 8:
        return {"r": 0.0, "p": 1.0, "lag": 0, "r0": 0.0, "n": len(ax)}
    r0 = calculate_pearson(ax, ay)
    best = {"r": abs(r0), "p": pearson_significance(r0, len(ax)),
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
        p = pearson_significance(r, len(bx))
        if abs(r) > best["r"]:
            best = {"r": abs(r), "p": p, "lag": tau, "r0": r, "n": len(bx)}
    best["r"] = round(best["r"], 4)
    best["p"] = round(best["p"], 5)
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
    _, ax, ay = _mask_pairs(xs, ys)
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
    for i in range(len(var_ids)):
        for j in range(i + 1, len(var_ids)):
            a, b = var_ids[i], var_ids[j]
            ax = decomps[a]["values"]
            by = decomps[b]["values"]

            ccf = cross_corr_best(ax, by)
            if ccf["n"] < 8:
                continue
            part = partial_corr(ax, by, confound) if confound is not None \
                else {"r": None, "p": None, "n": ccf["n"]}
            g_ab, g_ba = granger_f_test(ax, by)

            lag = ccf["lag"]
            if lag > 1:
                driver, response, lag_note = a, b, f"{a} leads {b} by {lag} months"
            elif lag < -1:
                driver, response, lag_note = b, a, f"{b} leads {a} by {-lag} months"
            else:
                if g_ab is not None and g_ba is not None:
                    if g_ab < g_ba and g_ab < ALPHA:
                        driver, response, lag_note = a, b, \
                            f"{a} predicts {b} (Granger p={g_ab:.3f})"
                    elif g_ba < g_ab and g_ba < ALPHA:
                        driver, response, lag_note = b, a, \
                            f"{b} predicts {a} (Granger p={g_ba:.3f})"
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
                "lag_months": lag,
                "driver": driver,
                "response": response,
                "lag_note": lag_note,
                "r_partial": part["r"],
                "p_partial": part["p"],
                "granger_a_b": round(g_ab, 5) if g_ab is not None else None,
                "granger_b_a": round(g_ba, 5) if g_ba is not None else None,
                "phase": "in_phase" if ccf["r0"] > 0 else "divergent",
                "strength": _strength_label(ccf["r"]),
                "confidence": confidence,
            })

    pairs.sort(key=lambda p: (
        0 if p["p"] < ALPHA else 1,
        -(abs(p["r_lagged"]) if p["p"] < ALPHA else abs(p["r_partial"] or 0)),
    ))
    return pairs


# --------------------------------------------------------------------------
# anomaly narrative: when did a variable run above / below its own trend
# --------------------------------------------------------------------------
def anomaly_episodes(values, months, sigma=1.0):
    eps = []
    cur = None
    for i, v in enumerate(values):
        if v is None:
            cur = None
            continue
        if v > sigma:
            if cur is None:
                cur = {"start": months[i], "end": months[i], "peak": v,
                       "n": 1, "peak_month": months[i]}
            else:
                cur["end"] = months[i]
                cur["n"] += 1
                if v > cur["peak"]:
                    cur["peak"] = v
                    cur["peak_month"] = months[i]
        else:
            if cur is not None:
                eps.append(cur)
                cur = None
    if cur is not None:
        eps.append(cur)
    return eps


def anomaly_report(values, months):
    usable = [(i, v) for i, v in enumerate(values) if v is not None]
    if not usable:
        return None
    sigma = _std([v for _, v in usable]) or 1.0
    above = [v for _, v in usable if v > sigma]
    below = [v for _, v in usable if v < -sigma]
    eps = anomaly_episodes(values, months, sigma)
    peak = max((v for _, v in usable), key=lambda v: abs(v))
    peak_i = next(i for i, v in usable if abs(v - peak) < 1e-9)
    return {
        "sigma": round(sigma, 4),
        "months_above": len(above),
        "months_below": len(below),
        "total_months": len(usable),
        "peak_sigma": round(peak / sigma, 2),
        "peak_month": months[peak_i],
        "episodes": [{
            "start": e["start"], "end": e["end"], "months": e["n"],
            "peak_sigma": round(e["peak"] / sigma, 2),
            "peak_month": e["peak_month"],
        } for e in eps],
        "narrative": _anomaly_narrative(len(usable), len(above), len(below),
                                        peak / sigma, months[peak_i], len(eps)),
    }


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
    for i in range(min(len(src_anom), len(tgt_anom))):
        if src_anom[i] is None or tgt_anom[i] is None:
            continue
        (during if src_anom[i] > src_sigma else outside).append(tgt_anom[i])
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
    """A specific, computed sentence for an uncatalogued variable pair.

    Everything in the wording comes from the diagnostics: the direction of the
    lead, the phase relationship, whether the link survived the confounder
    screen, and the Granger evidence. Nothing is asserted that was not tested.
    """
    name_a, name_b = a.get("name", "variable A"), b.get("name", "variable B")
    lag = pair.get("lag_months") or 0
    r = pair.get("r_lagged") or 0.0
    p = pair.get("p", 1.0)
    partial = pair.get("r_partial")
    ga, gb = pair.get("granger_a_b"), pair.get("granger_b_a")
    driver, response = pair.get("driver"), pair.get("response")
    sphere_a, sphere_b = a.get("sphere_code", "?"), b.get("sphere_code", "?")

    parts = []
    if driver == pair.get("a") and response == pair.get("b"):
        lead = f"{name_a} leads {name_b}"
    elif driver == pair.get("b") and response == pair.get("a"):
        lead = f"{name_b} leads {name_a}"
    elif lag > 0:
        lead = f"changes in {name_a} precede {name_b} by {lag} month{'s' if abs(lag) != 1 else ''}"
    elif lag < 0:
        lead = f"changes in {name_b} precede {name_a} by {-lag} month{'s' if abs(lag) != 1 else ''}"
    else:
        lead = f"{name_a} and {name_b} move simultaneously"
    parts.append(lead.capitalize() + ".")

    phase = ("in the same direction" if r > 0 else "in opposite directions")
    parts.append(f"After the seasonal cycle and shared trend are removed they stay correlated "
                 f"{phase} at r={r:+.2f} (p={p:.3f}), so about {abs(r) * 100:.0f}% of the "
                 f"month-to-month variation is shared.")

    if partial is not None:
        if abs(partial) < 0.15:
            parts.append("The link disappears once air temperature is controlled, so this is "
                         "largely a shared thermal response rather than a direct coupling.")
        elif abs(partial) < abs(r) * 0.7:
            parts.append(f"Controlling for air temperature weakens it to r={partial:+.2f}, so "
                         f"temperature explains part of the relationship.")
        else:
            parts.append(f"It survives the temperature control at r={partial:+.2f}, which is "
                         f"evidence of a direct {sphere_a}–{sphere_b} link.")

    if ga is not None and gb is not None:
        if ga < 0.05 and (gb is None or ga < gb):
            parts.append(f"{name_a}'s own past improves the prediction of {name_b} "
                         f"(Granger p={ga:.3f}).")
        elif gb is not None and gb < 0.05 and gb < ga:
            parts.append(f"{name_b}'s own past improves the prediction of {name_a} "
                         f"(Granger p={gb:.3f}).")
        else:
            parts.append("Neither history predicts the other beyond their shared variance, "
                         "so the ordering between them is unresolved.")

    return " ".join(parts)

