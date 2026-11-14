"""Unit test for the trend analysis core."""
from analysis import (mk_test, theil_sen, analyze_series, seasonal_mk,
                      theil_sen_ci, t_test_trend, t_cdf)


def approx(a, b, tol=0.01):
    return abs(a - b) < tol


def test_mk_strong_up():
    z, p, tau, h = mk_test(list(range(30)))
    assert h and z > 3 and p < 0.01 and tau > 0.9


def test_mk_strong_down():
    z, p, tau, h = mk_test([float(x) for x in range(30, 0, -1)])
    assert h and z < -3 and p < 0.01 and tau < -0.9


def test_mk_flat_noise():
    vals = [5, 4.9, 5.1, 5.0, 4.8, 5.2, 5.05, 4.95, 5.0, 5.1,
            4.9, 5.0, 5.15, 4.85, 5.0, 4.95, 5.05, 5.1, 4.9, 5.0]
    z, p, tau, h = mk_test(vals)
    assert not h, f"flat noise should not be significant, got z={z}, p={p}"


def test_theil_sen_perfect():
    m, b = theil_sen([2.0 * x + 1.0 for x in range(20)])
    assert approx(m, 2.0) and approx(b, 1.0)


def test_theil_sen_outlier_robust():
    ys = [1.0 * x for x in range(20)] + [999.0]
    ys = ys[:21]
    m, b = theil_sen(ys)
    assert approx(m, 1.0, 0.2), f"outlier robustness failed: {m}"


def test_analyze_series_steady_rise():
    ys = [0.5 * x for x in range(24)]  # 0.5 C per month-ish
    r = analyze_series(ys)
    assert r["ok"] and r["significant"] and r["direction"] == "rising"
    assert approx(r["slope"], 0.5)


def test_analyze_series_short():
    r = analyze_series([1, 2, 3, 4])
    assert not r["ok"] and "insufficient" in r["reason"]


def test_analyze_series_none_gaps():
    ys = [None] + [float(x) for x in range(12)] + [None, 12.0, 13.0]
    r = analyze_series(ys)
    assert r["ok"] and r["direction"] == "rising"


def test_seasonal_mk_removes_seasonal_cycle():
    """A flat series with a big seasonal cycle must NOT look significant."""
    import math
    vals = []
    for year in range(20):
        for m in range(12):
            vals.append(10 + 8 * math.sin(2 * math.pi * m / 12))
    z, p, tau, h = seasonal_mk(vals)
    assert not h, f"seasonal cycle should not be significant, got z={z}, p={p}"


def test_seasonal_mk_detects_real_trend():
    """Seasonal cycle + real upward trend should be significant."""
    import math
    vals = []
    for year in range(20):
        for m in range(12):
            vals.append(10 + 8 * math.sin(2 * math.pi * m / 12) + 0.5 * year)
    z, p, tau, h = seasonal_mk(vals)
    assert h and z > 2, f"should detect rising trend, got z={z}, p={p}"


def test_ci_brackets_the_slope():
    """A clean trend's CI must be tight and contain the true slope."""
    ys = [0.5 * x for x in range(24)]
    lo, hi = theil_sen_ci(ys)
    assert lo is not None and hi is not None
    assert lo <= 0.5 <= hi, f"CI [{lo}, {hi}] must contain 0.5"
    assert (hi - lo) < 0.05, f"clean series should give a tight CI, got {hi-lo}"


def test_ci_widens_with_noise():
    import random
    random.seed(7)
    clean = [0.5 * x for x in range(24)]
    noisy = [v + random.uniform(-8, 8) for v in clean]
    lo_c, hi_c = theil_sen_ci(clean)
    lo_n, hi_n = theil_sen_ci(noisy)
    assert (hi_n - lo_n) > (hi_c - lo_c), "noise should widen the interval"


def test_ci_none_for_short_series():
    lo, hi = theil_sen_ci([1, 2, 3])
    assert lo is None and hi is None


def test_analysis_exposes_ci_per_decade():
    ys = [0.5 * x for x in range(24)]
    r = analyze_series(ys)
    assert r["ci_low_per_decade"] is not None
    assert r["ci_low_per_decade"] <= r["per_decade"] <= r["ci_high_per_decade"]


def test_t_cdf_known_values():
    # two-sided 5% critical value for df=20 is 2.086
    assert approx(t_cdf(-2.086, 20), 0.025, 0.002)
    assert approx(t_cdf(2.086, 20), 0.975, 0.002)
    # symmetric around zero
    assert approx(t_cdf(0.0, 10), 0.5, 1e-9)


def test_t_test_detects_clean_trend():
    ys = [0.5 * x for x in range(24)]
    tt = t_test_trend(ys)
    assert tt is not None
    assert approx(tt["slope"], 0.5, 1e-9)
    assert tt["p"] < 1e-6, f"clean linear trend should be significant, p={tt['p']}"
    assert tt["df"] == 22


def test_t_test_rejects_noise():
    import random
    random.seed(11)
    ys = [random.uniform(-1, 1) for _ in range(24)]
    tt = t_test_trend(ys)
    assert tt is not None
    assert tt["p"] > 0.05, f"pure noise should not be significant, p={tt['p']}"


def test_t_test_ci_contains_slope():
    ys = [0.5 * x for x in range(24)]
    tt = t_test_trend(ys)
    assert tt["ci_low"] <= tt["slope"] <= tt["ci_high"]


def test_analyze_series_reports_both_tests():
    ys = [0.5 * x for x in range(24)]
    r = analyze_series(ys)
    assert r["t_p"] is not None and r["p"] is not None
    assert r["t_significant"] and r["significant"]
    assert r["methods_agree"] is True


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print("ALL PASS")
