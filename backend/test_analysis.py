"""Unit test for the trend analysis core."""
from analysis import mk_test, theil_sen, analyze_series, seasonal_mk


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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print("ALL PASS")
