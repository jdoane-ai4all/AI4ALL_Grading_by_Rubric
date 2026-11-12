"""Pre-registered test-set analysis (Protocol §7 and §18).

Conditions reported: C0 always-5 baseline, B0 literal, B1 shift, B2 table.
Calibration is fitted on DEVELOPMENT only (config/calibration_fit_dev.json).
Requires data/TEST_UNLOCKED. Writes outputs/results_test.{json,md}.
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, "src")
from rubric_scoring import analysis, calibration as cal, data, metrics as M  # noqa: E402
from rubric_scoring.rubric import CRITERIA  # noqa: E402

COND = "F1_evidence_joint_text"
REPS = 5000


def load():
    labels = data.read_label_table("data/private/labels.csv")
    reg = json.load(open("registry/split_registry.json"))
    preds = []
    for r in csv.DictReader(open("runs/predictions.csv")):
        r["replicate"] = int(r["replicate"])
        r["score"] = int(r["score"]) if r["score"] not in ("", "None") else None
        preds.append(r)
    return labels, reg, preds


def baseline_preds(preds):
    out = []
    for p in preds:
        if p["condition"] == COND:
            q = dict(p, condition="C0_always5", score=5, status="scored")
            out.append(q)
    return out


def main():
    if not analysis.UNLOCK_FILE.exists():
        raise SystemExit("test split locked")
    labels, reg, preds = load()
    fit = json.load(open("config/calibration_fit_dev.json"))
    b2 = {c: {int(k): v for k, v in t.items()} for c, t in fit["B2_table"].items()}
    allp = (preds + baseline_preds(preds)
            + cal.calibrated_preds(preds, "B1_shift", fit["B1_shift"], COND)
            + cal.calibrated_preds(preds, "B2_table", b2, COND))
    cfg = data.load_config("config/study_config.json")
    conds = ["C0_always5", COND, f"{COND}+B1_shift", f"{COND}+B2_table"]
    cfg["scoring"]["conditions"] = {c: {} for c in conds}
    cfg["scoring"]["primary_contrast"] = [f"{COND}+B2_table", COND]
    cfg["scoring"]["secondary_contrasts"] = [[f"{COND}+B2_table", "C0_always5"], [COND, "C0_always5"]]
    cfg["metrics"]["bootstrap_reps"] = REPS
    res = analysis.analyse(allp, labels, reg, cfg, "test")
    res["stability"] = {}

    # Learning curve: refit B2 on random subsets of development groups.
    split = reg["project_split"]
    dev_groups = sorted({labels[p]["group_id"] for p, s in split.items() if s == "development" and p in labels})
    lc = defaultdict(list)
    for k, _, gs in cal.learning_curve_groups(dev_groups, sizes=(5, 10, 20, 30), draws=200):
        t = cal.fit_table(cal.dev_pairs(preds, labels, split, COND, gs))
        errs = []
        for p in cal.calibrated_preds(preds, "B2_table", t, COND):
            lab = labels.get(p["project_id"])
            if p["status"] == "scored" and lab and lab["eligible"] and split.get(p["project_id"]) == "test":
                errs.append(abs(p["score"] - lab[p["criterion"]]))
        lc[k].append(float(np.mean(errs)))
    res["learning_curve_pooled_criterion_mae"] = {
        k: {"median": float(np.median(v)), "p2_5": float(np.percentile(v, 2.5)), "p97_5": float(np.percentile(v, 97.5))}
        for k, v in lc.items()}
    Path("outputs").mkdir(exist_ok=True)
    json.dump(res, open("outputs/results_test.json", "w"), indent=2)
    analysis.write_markdown(res, "outputs/results_test.md")
    with open("outputs/results_test.md", "a") as f:
        f.write("\n## Paired contrasts (pooled criterion MAE, A minus B, 95% CI)\n")
        for k, v in res["paired_contrasts"].items():
            d = v["pooled_mae_diff_A_minus_B"]
            f.write(f"- {k}: {d['point']:+.3f} [{d['ci95'][0]:+.3f}, {d['ci95'][1]:+.3f}] (n pairs {v['n_pairs_both_scored']})\n")
        f.write("\n## Learning curve (B2 refit on k development groups; pooled test MAE)\n")
        for k, v in sorted(res["learning_curve_pooled_criterion_mae"].items()):
            f.write(f"- k={k}: median {v['median']:.3f} [{v['p2_5']:.3f}, {v['p97_5']:.3f}]\n")
    print(open("outputs/results_test.md").read())


if __name__ == "__main__":
    main()
