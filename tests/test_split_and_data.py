from collections import defaultdict

import pytest

from rubric_scoring import data, split


def test_column_letters():
    assert data.col_index("A") == 0 and data.col_index("Z") == 25 and data.col_index("AA") == 26


def test_forbidden_columns_never_loaded(synthetic_labels_csv, config):
    rows = data.load_labels(synthetic_labels_csv, config)
    assert all("SHOULD-NEVER" not in repr(r) for r in rows)


def test_gates_exclude_unlabeled(synthetic_labels_csv, config):
    rows = data.load_labels(synthetic_labels_csv, config)
    flow = data.eligibility_flow(rows)
    assert flow["exclusion_reasons"]["no_located_label"] == 14


def test_partial_and_mismatch_gates():
    r = data.LabelRow("p", "g", "SU25", {c: 5 for c in data.CRITERIA}, 29)
    data.apply_label_gates(r)
    assert r.exclusion_reasons == ["total_mismatch"]
    r2 = data.LabelRow("p", "g", "SU25", {**{c: 5 for c in data.CRITERIA}, "citations": None}, None)
    data.apply_label_gates(r2)
    assert "partial_vector" in r2.exclusion_reasons


def test_groups_never_straddle_split(synthetic_labels_csv, config):
    rows = data.load_labels(synthetic_labels_csv, config)
    reg = split.build_registry(rows, config)
    by_group = defaultdict(set)
    for r in rows:
        by_group[r.group_id].add(reg["project_split"][r.project_id])
    assert all(len(s) == 1 for s in by_group.values())


def test_split_is_deterministic_and_proportional(synthetic_labels_csv, config):
    rows = data.load_labels(synthetic_labels_csv, config)
    a, b = split.build_registry(rows, config), split.build_registry(rows, config)
    assert a["assignment_sha256"] == b["assignment_sha256"]
    n = len(a["group_assignment"])
    n_dev = sum(v == "development" for v in a["group_assignment"].values())
    assert n_dev == round(config["split"]["development_fraction"] * n)
    for s, c in a["stratum_counts"].items():  # every stratum with >=3 groups is in both splits
        if c["development"] + c["test"] >= 3:
            assert c["test"] >= 1 and c["development"] >= 1, s


def test_registry_locked(tmp_path, synthetic_labels_csv, config):
    reg = split.build_registry(data.load_labels(synthetic_labels_csv, config), config)
    p = split.write_registry(reg, tmp_path / "r.json")
    assert split.verify_registry(p)
    with pytest.raises(FileExistsError):
        split.write_registry(reg, p)
