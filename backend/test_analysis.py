"""Unit test for the trend analysis core."""
from analysis import (
    mk_test, theil_sen, analyze_series, seasonal_mk,
    theil_sen_ci, t_test_trend, t_cdf,
    calculate_pearson, analyze_cross_coupling, analyze_regional_contrast
)


def approx(a, b, tol=0.01):
    return abs(a - b) <= tol


def test_mk_strong_up():
    ys = [float(x) for x in range(20)]
    z, p, tau, h = mk_test(ys)
    assert h, "should be significant"
    assert z > 3.0, f"z should be large positive, got {z}"
    assert approx(tau, 1.0)
    assert p < 0.001


def test_mk_strong_down():
    ys = [float(20 - x) for x in range(20)]
    z, p, tau, h = mk_test(ys)
    assert h
    assert z < -3.0
    assert approx(tau, -1.0)


def test_mk_flat_noise():
    import random
    random.seed(42)
    ys = [random.gauss(0, 1) for _ in range(30)]
    z, p, tau, h = mk_test(ys)
    assert not h, f"noise should not be significant at 0.05, got p={p}"


def test_theil_sen_perfect():
    ys = [2.0 * x + 5.0 for x in range(15)]
    slope, intercept = theil_sen(ys)
    assert approx(slope, 2.0)
    assert approx(intercept, 5.0)


def test_theil_sen_outlier_robust():
    ys = [2.0 * x + 5.0 for x in range(15)]
    ys[5] = 999.0  # massive outlier
    slope, intercept = theil_sen(ys)
    assert approx(slope, 2.0, tol=0.05), f"slope should resist outlier, got {slope}"


def test_analyze_series_steady_rise():
    ys = [10.0 + 0.5 * x for x in range(20)]
    res = analyze_series(ys)
    assert res["ok"]
    assert res["direction"] == "rising"
    assert res["significant"]
    assert approx(res["per_decade"], 5.0)


def test_analyze_series_short():
    res = analyze_series([1.0, 2.0, 3.0])
    assert not res["ok"]
    assert "insufficient" in res["reason"]


def test_analyze_series_none_gaps():
    ys = [float(x) if x % 3 != 0 else None for x in range(25)]
    res = analyze_series(ys)
    assert res["ok"]
    assert res["n"] < 25
    assert res["direction"] == "rising"


def test_seasonal_mk_removes_seasonal_cycle():
    # pure 12-month sine wave — no secular trend
    import math
    months = [10.0 + 5.0 * math.sin(2 * math.pi * (m % 12) / 12) for m in range(240)]
    z, p, tau, h = seasonal_mk(months, 12)
    assert not h, f"pure seasonal cycle should show no secular trend, got p={p}, z={z}"


def test_seasonal_mk_detects_real_trend():
    import math
    months = [10.0 + 0.05 * m + 5.0 * math.sin(2 * math.pi * (m % 12) / 12) for m in range(240)]
    z, p, tau, h = seasonal_mk(months, 12)
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


def test_calculate_pearson():
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [2.0, 4.0, 6.0, 8.0, 10.0]
    r = calculate_pearson(xs, ys)
    assert approx(r, 1.0), f"Expected r=1.0, got {r}"

    inv_ys = [10.0, 8.0, 6.0, 4.0, 2.0]
    r_inv = calculate_pearson(xs, inv_ys)
    assert approx(r_inv, -1.0), f"Expected r=-1.0, got {r_inv}"


def test_analyze_cross_coupling_vpd_divergence():
    # Temperature rising, relative humidity falling
    t2m = {"id": "T2M", "name": "Air Temperature", "sphere_code": "ATM", "sphere_name": "Atmosphere"}
    rh2m = {"id": "RH2M", "name": "Relative Humidity", "sphere_code": "HYD", "sphere_name": "Hydrosphere"}
    ts_temp = [20.0 + 0.1 * i for i in range(20)]
    ts_rh = [70.0 - 0.4 * i for i in range(20)]

    c = analyze_cross_coupling(t2m, rh2m, ts_temp, ts_rh)
    assert c["phase"] == "divergent"
    assert "Vapor Pressure Deficit" in c["title"]
    assert c["r"] < -0.9
    assert c["sphere_a_code"] == "ATM" and c["sphere_b_code"] == "HYD"
    assert not c["same_sphere"]


def test_analyze_cross_coupling_greenhouse():
    # Temperature rising, longwave flux rising
    t2m = {"id": "T2M", "name": "Air Temperature", "sphere_code": "ATM", "sphere_name": "Atmosphere"}
    lw = {"id": "ALLSKY_SFC_LW_DWN", "name": "Longwave Flux", "sphere_code": "ENG", "sphere_name": "Energy & Radiation"}
    ts_temp = [20.0 + 0.1 * i for i in range(20)]
    ts_lw = [380.0 + 1.2 * i for i in range(20)]

    c = analyze_cross_coupling(t2m, lw, ts_temp, ts_lw)
    assert c["phase"] == "in_phase"
    assert "Greenhouse" in c["title"]
    assert c["r"] > 0.9


def test_analyze_regional_contrast():
    var = {"id": "T2M", "name": "Air Temperature", "unit": "°C"}
    reg_a = {"id": "arctic", "name": "Arctic (Svalbard)"}
    reg_b = {"id": "sahel", "name": "Sahel (Niamey)"}

    # Region A rapidly warming (+0.8°C/dec)
    series_a = [{"year": 2000 + i, "value": -5.0 + 0.08 * i} for i in range(20)]
    stats_a = {"slope": 0.08, "direction": "rising", "significant": True, "p": 0.001}

    # Region B stable / flat
    series_b = [{"year": 2000 + i, "value": 29.0 + 0.001 * i} for i in range(20)]
    stats_b = {"slope": 0.001, "direction": "flat", "significant": False, "p": 0.45}

    contrast = analyze_regional_contrast(var, reg_a, reg_b, series_a, series_b, stats_a, stats_b)
    assert contrast["var_id"] == "T2M"
    assert approx(contrast["slope_a_decade"], 0.8)
    assert approx(contrast["slope_b_decade"], 0.01)
    assert contrast["verdict"] == "LOCALIZED SIGNAL"


def test_pearson_significance():
    from analysis import pearson_significance
    # r = 0.60 with n = 20 should be highly significant (p < 0.01)
    p = pearson_significance(0.60, 20)
    assert p < 0.01, f"Expected p < 0.01, got {p}"

    # r = 0.05 with n = 20 should not be significant (p > 0.5)
    p_null = pearson_significance(0.05, 20)
    assert p_null > 0.5, f"Expected p > 0.5, got {p_null}"


def test_explain_teleconnection():
    from analysis import explain_teleconnection
    src_reg = {"id": "tropical_pacific", "name": "Tropical Pacific"}
    src_var = {"id": "WS2M", "name": "Wind Speed"}
    dst_reg = {"id": "ghana_north", "name": "Ghana North"}
    dst_var = {"id": "T2M", "name": "Air Temperature"}

    exp = explain_teleconnection(src_reg, src_var, dst_reg, dst_var, -0.62, 0.003)
    assert "teleconnection" in exp.lower() or "circulation" in exp.lower()
    assert len(exp) > 20


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"ALL PASS ({len(fns)} tests)")
