"""End-to-end on SYNTHETIC labels and SYNTHETIC predictions: checks plumbing, not performance."""
import random

from rubric_scoring import analysis, data, split
from rubric_scoring.review_policy import Policy, evaluate
from rubric_scoring.rubric import CRITERIA


def test_pipeline(tmp_path, synthetic_labels_csv, config, monkeypatch):
    rows = data.load_labels(synthetic_labels_csv, config)
    reg = split.build_registry(rows, config)
    data.write_label_table(rows, tmp_path / "labels.csv")
    labels = data.read_label_table(tmp_path / "labels.csv")
    rng = random.Random(3)
    preds = []
    for cond in ["C1_basic_separate", "C2_evidence_separate"]:
        for rep in (1, 2):
            for pid, lab in labels.items():
                if not lab["eligible"]:
                    continue
                for c in CRITERIA:
                    s = max(1, min(5, lab[c] + rng.choice([0, 0, 0, -1, 1])))
                    st = "abstain" if rng.random() < 0.02 else "scored"
                    preds.append({"condition": cond, "replicate": rep, "project_id": pid, "criterion": c,
                                  "score": None if st == "abstain" else s, "status": st})
    config["metrics"]["bootstrap_reps"] = 200
    res = analysis.analyse(preds, labels, reg, config, "development")
    m = res["conditions"]["C2_evidence_separate"]["criteria"]["citations"]
    assert 0 < m["coverage"] <= 1 and m["n_calls"] >= m["n"]
    assert "C2_evidence_separate__vs__C1_basic_separate" in res["paired_contrasts"]
    assert "C2_evidence_separate" in res["stability"]
    monkeypatch.chdir(tmp_path)
    try:
        analysis.analyse(preds, labels, reg, config, "test")
        raise AssertionError("test split should be locked")
    except PermissionError:
        pass
    analysis.write_markdown(res, tmp_path / "r.md")
    proj = {pid: {"scores": {c: lab[c] for c in CRITERIA}} for pid, lab in labels.items() if lab["eligible"]}
    ev = evaluate(proj, {pid: labels[pid] for pid in proj}, Policy())
    assert ev["accepted_with_any_severe_error"] == 0
