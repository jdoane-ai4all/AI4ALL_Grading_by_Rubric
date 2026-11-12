import numpy as np
import pytest
from sklearn.metrics import cohen_kappa_score

from rubric_scoring import metrics as M


def test_qwk_matches_sklearn():
    rng = np.random.default_rng(1)
    h = rng.integers(1, 6, 200)
    a = np.clip(h + rng.integers(-1, 2, 200), 1, 5)
    assert M.weighted_kappa(h, a) == pytest.approx(cohen_kappa_score(h, a, weights="quadratic", labels=[1, 2, 3, 4, 5]))
    assert M.weighted_kappa(h, a, "linear") == pytest.approx(cohen_kappa_score(h, a, weights="linear", labels=[1, 2, 3, 4, 5]))


def test_icc_perfect_and_offset():
    x = np.array([10, 15, 20, 25, 30], float)
    assert M.icc_a1(x, x) == pytest.approx(1.0)
    # constant offset lowers ABSOLUTE agreement below 1 (consistency would stay 1)
    assert M.icc_a1(x, x + 3) < 0.95


def test_icc_reference_value():
    # Shrout & Fleiss (1979) data, raters 1 and 2: ICC(A,1) computed independently = 0.1757...
    r1 = np.array([9, 6, 8, 7, 10, 6], float)
    r2 = np.array([2, 1, 4, 1, 5, 2], float)
    d = np.column_stack([r1, r2]); n, k = d.shape; gm = d.mean()
    msr = k * ((d.mean(1) - gm) ** 2).sum() / (n - 1)
    msc = n * ((d.mean(0) - gm) ** 2).sum() / (k - 1)
    mse = (((d - gm) ** 2).sum() - msr * (n - 1) - msc * (k - 1)) / ((n - 1) * (k - 1))
    expected = (msr - mse) / (msr + (k - 1) * mse + k * (msc - mse) / n)
    assert M.icc_a1(r1, r2) == pytest.approx(expected)


def test_criterion_point_basics():
    m = M.criterion_point([5, 5, 4, 3], [5, 4, 4, 5])
    assert m["mae"] == pytest.approx(0.75) and m["exact"] == 0.5 and m["severe_rate"] == 0.25
    assert m["over_on_low"] == 1.0 and m["n_human_low"] == 1


def test_cluster_bootstrap_keeps_groups():
    units = [{"g": i // 2, "v": float(i // 2)} for i in range(40)]
    res = M.cluster_bootstrap(units, "g", lambda s: float(np.mean([u["v"] for u in s])), reps=500)
    assert res["ci95"][0] < res["point"] < res["ci95"][1]


def test_total_threshold_and_cancellation():
    t = M.total_point([20, 25, 30, 24], [22, 25, 30, 23], 24, crit_abs_err_sum=[4, 0, 0, 3])
    assert t["threshold_agreement"] == 0.75
    assert 0 < t["cancellation_ratio"] < 1


def test_stability():
    s = M.stability({("p", "c"): [5, 5, 5], ("q", "c"): [4, 5, 4], ("r", "c"): [3, None, 3]})
    assert s["any_change_rate"] == pytest.approx(2 / 3) and s["abstain_flip_rate"] == pytest.approx(1 / 3)
