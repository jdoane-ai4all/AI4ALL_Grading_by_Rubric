from rubric_scoring import calibration as cal


def test_shift_and_table():
    pairs = {c: [] for c in cal.CRITERIA}
    pairs["next_steps"] = [(4, 5), (4, 5), (4, 4), (3, 4), (2, 4), (5, 5)]
    sh = cal.fit_shift(pairs)
    assert sh["next_steps"] > 0
    t = cal.fit_table(pairs)["next_steps"]
    assert t[4] == 5 and t[3] == 4 and t[5] == 5
    assert all(t[k] <= t[k + 1] for k in range(1, 5))  # monotone
    assert cal.apply("B2_table", cal.fit_table(pairs), "next_steps", None) is None  # abstain stays abstain


def test_pava_monotone():
    assert cal._pava([3, 2, 4], [1, 1, 1]) == [2.5, 2.5, 4]
