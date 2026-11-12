"""Independent verification of the Phase 2 results, and reconciliation with Phase 1.

Reads the private joined table (per-project titles and instructor grades, so it is git-ignored):
    data/private/phase2/grading_four_methods_joined_by_project.csv
and, for cross-checks, Phase 1's private files (data/private/labels.csv, runs/run_log.jsonl) and the
committed split registry and calibration fit. Writes only aggregate numbers:
    research/phase2_prompt_x_calibration/metrics/verification.json

    python3 research/phase2_prompt_x_calibration/scripts/verify_phase2.py
"""
from __future__ import annotations

import csv
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
JOINED = ROOT / "data/private/phase2/grading_four_methods_joined_by_project.csv"
OUT = ROOT / "research/phase2_prompt_x_calibration/metrics/verification.json"
REPORTED = ROOT / "research/phase2_prompt_x_calibration/metrics/evaluation_metrics.csv"

ARMS = {"A": ("rubric", "Strict rubric"), "B": ("rubric_cal", "Strict rubric + calibration"),
        "C": ("human", "Human-like"), "D": ("human_cal", "Human-like + calibration")}
CRITS = ["Project Description", "Algorithm", "Essential Question", "Next Steps", "Citations"]
KEY = {"Project Description": "project_description", "Algorithm": "algorithm",
       "Essential Question": "essential_question", "Next Steps": "next_steps", "Citations": "citations"}
# Calibration tables as stated in the Phase 2 handoff (outputs for raw 1..5)
TABLES = {
    "rubric": {"Project Description": [1, 2, 4, 4, 5], "Algorithm": [2, 4, 4, 5, 5], "Essential Question": [2, 4, 4, 5, 5],
               "Next Steps": [4, 4, 4, 4, 5], "Citations": [3, 3, 3, 4, 5]},
    "human": {"Project Description": [1, 2, 4, 5, 5], "Algorithm": [1, 3, 4, 5, 5], "Essential Question": [1, 3, 4, 4, 5],
              "Next Steps": [1, 2, 4, 4, 5], "Citations": [1, 3, 3, 5, 5]},
}


def runs(s: str) -> list[int]:
    return [int(x) for x in s.split(",")]


def qwk(a: list[int], b: list[int], k: int = 5) -> float:
    n = len(a)
    O = [[0] * k for _ in range(k)]
    for x, y in zip(a, b):
        O[x - 1][y - 1] += 1
    ra = [sum(r) for r in O]
    cb = [sum(O[i][j] for i in range(k)) for j in range(k)]
    num = den = 0.0
    for i in range(k):
        for j in range(k):
            w = (i - j) ** 2 / (k - 1) ** 2
            num += w * O[i][j]
            den += w * ra[i] * cb[j] / n
    return 1 - num / den if den else float("nan")


def agree(pred: list[int], ref: list[int]) -> dict:
    d = [p - r for p, r in zip(pred, ref)]
    n = len(d)
    return {"n": n, "exact": sum(x == 0 for x in d) / n, "mae": sum(abs(x) for x in d) / n,
            "within1": sum(abs(x) <= 1 for x in d) / n, "mean_diff": sum(d) / n,
            "over_rate": sum(x > 0 for x in d) / n, "under_rate": sum(x < 0 for x in d) / n, "qwk": qwk(pred, ref)}


def pearson(x, y):
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)


def main() -> None:
    rows = list(csv.DictReader(open(JOINED, newline="", encoding="utf-8-sig")))
    for r in rows:
        r["human_grade"] = int(float(r["Historical human grade"])) if r["Historical human grade"] else None
        for col, _ in ARMS.values():
            r[col + "_runs"] = runs(r[f"{col} 10 runs"])
            r[col + "_mode"] = int(r[f"{col} mode"])
    out: dict = {"source_rows": len(rows), "projects": len({r["Project ID"] for r in rows})}

    # 1. internal consistency: modes, ties, calibrated runs = table(raw runs)
    ties = mode_mismatch = 0
    cal_mismatch = Counter()
    for r in rows:
        for col, _ in ARMS.values():
            c = Counter(r[col + "_runs"]).most_common()
            if len(c) > 1 and c[0][1] == c[1][1]:
                ties += 1
            if c[0][0] != r[col + "_mode"]:
                mode_mismatch += 1
        for raw in ("rubric", "human"):
            t = TABLES[raw][r["Criterion"]]
            if [t[x - 1] for x in r[raw + "_runs"]] != r[raw + "_cal_runs"]:
                cal_mismatch[raw] += 1
    fit = json.loads((ROOT / "config/calibration_fit_dev.json").read_text())["B2_table"]
    strict_same_as_phase1 = all([fit[KEY[c]][str(s)] for s in range(1, 6)] == TABLES["rubric"][c] for c in CRITS)
    out["internal_checks"] = {"mode_ties": ties, "mode_mismatches": mode_mismatch,
                              "calibrated_runs_not_matching_table": dict(cal_mismatch),
                              "strict_table_equals_phase1_B2_fit": strict_same_as_phase1}

    # 2. headline agreement on the locked test set and development set
    def subset(s):
        return [r for r in rows if r["Set"] == s and r["human_grade"] is not None]
    out["agreement"] = {}
    for s in ("development", "test"):
        sub = subset(s)
        ref = [r["human_grade"] for r in sub]
        res = {name: agree([r[col + "_mode"] for r in sub], ref) for col, name in ARMS.values()}
        res["Always 5 (baseline)"] = agree([5] * len(ref), ref)
        out["agreement"][s] = res
    test = subset("test")
    out["test_label_distribution"] = dict(sorted(Counter(r["human_grade"] for r in test).items()))
    out["test_by_criterion_exact"] = {c: {name: agree([r[col + "_mode"] for r in test if r["Criterion"] == c],
                                                      [r["human_grade"] for r in test if r["Criterion"] == c])["exact"]
                                          for col, name in ARMS.values()} for c in CRITS}

    # 3. low instructor grades (1-3) and grade-5 subgroups on test
    for label, cond in (("instructor_1_to_3", lambda g: g <= 3), ("instructor_5", lambda g: g == 5)):
        sub = [r for r in test if cond(r["human_grade"])]
        out[label] = {name: {"n": len(sub), "exact": agree([r[col + "_mode"] for r in sub], [r["human_grade"] for r in sub])["exact"],
                             "mean_diff": agree([r[col + "_mode"] for r in sub], [r["human_grade"] for r in sub])["mean_diff"]}
                      for col, name in ARMS.values()}

    # 4. project totals (5-25) on test projects with all five labels
    byp = defaultdict(list)
    for r in test:
        byp[r["Project ID"]].append(r)
    complete = {p: rs for p, rs in byp.items() if len(rs) == 5}
    out["totals"] = {"projects": len(complete)}
    hum = [sum(r["human_grade"] for r in rs) for rs in complete.values()]
    out["totals"]["human_mean"] = sum(hum) / len(hum)
    out["totals"]["human_perfect_25"] = sum(h == 25 for h in hum)
    for col, name in ARMS.values():
        pred = [sum(r[col + "_mode"] for r in rs) for rs in complete.values()]
        d = [p - h for p, h in zip(pred, hum)]
        out["totals"][name] = {"mean_pred": sum(pred) / len(pred), "mae": sum(map(abs, d)) / len(d),
                               "rmse": math.sqrt(sum(x * x for x in d) / len(d)), "exact": sum(x == 0 for x in d),
                               "pearson": pearson(pred, hum), "mean_diff": sum(d) / len(d)}
    always5 = [25] * len(hum)
    out["totals"]["Always 5 (baseline)"] = {"mae": sum(abs(a - h) for a, h in zip(always5, hum)) / len(hum),
                                            "exact": sum(h == 25 for h in hum)}

    # 5. repeatability across all 990 project-criterion groups
    out["repeatability_all_990"] = {}
    for col, name in ARMS.values():
        un = sum(len(set(r[col + "_runs"])) == 1 for r in rows)
        pw = sum(sum(a == b for i, a in enumerate(r[col + "_runs"]) for b in r[col + "_runs"][i + 1:]) / 45 for r in rows) / len(rows)
        ms = sum(Counter(r[col + "_runs"]).most_common(1)[0][1] / 10 for r in rows) / len(rows)
        out["repeatability_all_990"][name] = {"unanimous": un, "unanimous_rate": un / len(rows), "pairwise": pw,
                                              "modal_share": ms}
    # stopping rule: first score repeated 3 times in a row equals the 10-run mode?
    hits, calls = 0, []
    for r in rows:
        seq, stop = r["rubric_runs"], None
        for i in range(2, len(seq)):
            if seq[i] == seq[i - 1] == seq[i - 2]:
                stop = (seq[i], i + 1)
                break
        if stop is None:
            stop = (r["rubric_mode"], 10)
        hits += stop[0] == r["rubric_mode"]
        calls.append(stop[1])
    out["three_in_a_row_stopping_rule_strict"] = {"matches_10_run_mode": hits, "of": len(rows),
                                                  "mean_calls": sum(calls) / len(calls)}

    # 6. cluster bootstrap (projects) for the B vs A, D vs C and D vs B contrasts on test
    rng = random.Random(20261104)
    pids = sorted(byp)
    reps = {k: [] for k in ("B-A exact", "B-A mae", "D-C exact", "D-C mae", "D-B exact", "D-B mae")}
    for _ in range(2000):
        samp = [rng.choice(pids) for _ in pids]
        rs = [r for p in samp for r in byp[p]]
        ref = [r["human_grade"] for r in rs]
        m = {k: agree([r[col + "_mode"] for r in rs], ref) for k, (col, _) in ARMS.items()}
        for a, b in (("B", "A"), ("D", "C"), ("D", "B")):
            reps[f"{a}-{b} exact"].append(m[a]["exact"] - m[b]["exact"])
            reps[f"{a}-{b} mae"].append(m[b]["mae"] - m[a]["mae"])   # positive = a has lower error
    out["bootstrap_95ci_test"] = {k: [sorted(v)[49], sorted(v)[1949]] for k, v in reps.items()}

    # 7. reconciliation with Phase 1 (private files; skipped if absent)
    rec: dict = {}
    lab_path = ROOT / "data/private/labels.csv"
    if lab_path.exists():
        labels = {d["project_id"]: d for d in csv.DictReader(open(lab_path, newline="", encoding="utf-8-sig"))}
        diff, compared, diff_projects = 0, 0, set()
        for r in rows:
            d = labels.get(r["Project ID"])
            if not d or r["human_grade"] is None or not d.get(KEY[r["Criterion"]]):
                continue
            compared += 1
            if str(r["human_grade"]) != str(d[KEY[r["Criterion"]]]).strip():
                diff += 1
                diff_projects.add(r["Project ID"])
        p199 = labels.get("project-199", {})
        rec["labels_vs_phase1"] = {"compared": compared, "different": diff, "projects_with_differences": len(diff_projects),
                                   "phase1_has_valid_project_199_project_description": bool(p199.get("project_description")),
                                   "phase2_project_199_project_description": next(
                                       (r["Historical human grade"] for r in rows if r["Project ID"] == "project-199"
                                        and r["Criterion"] == "Project Description"), None) or "missing"}
    reg = json.loads((ROOT / "registry/split_registry.json").read_text())["project_split"]
    rec["split_matches_registry"] = all(reg.get(r["Project ID"]) == r["Set"] for r in rows)
    log = ROOT / "runs/run_log.jsonl"
    if log.exists():
        p1 = {}
        for line in log.read_text().splitlines():
            e = json.loads(line)
            if e.get("status") == "valid" and e.get("call_criterion") == "ALL":
                p1[e["project_id"]] = {i["criterion"]: i["score"] for i in e["output"]}   # last valid run, as the app uses
        same = total = abst = 0
        diffs = []
        by_c = defaultdict(lambda: [0, 0])
        for r in rows:
            s = p1.get(r["Project ID"], {}).get(KEY[r["Criterion"]])
            if s is None:
                continue
            if s == "ABSTAIN":
                abst += 1
                continue
            total += 1
            same += int(s) == r["rubric_mode"]
            diffs.append(r["rubric_mode"] - int(s))
            by_c[r["Criterion"]][0] += int(s) == r["rubric_mode"]
            by_c[r["Criterion"]][1] += 1
        rec["phase2_strict_mode_vs_phase1_single_run"] = {
            "compared": total, "phase1_abstentions_excluded": abst, "identical": same, "identical_rate": same / total,
            "mean_phase2_minus_phase1": sum(diffs) / len(diffs),
            "identical_rate_by_criterion": {c: by_c[c][0] / by_c[c][1] for c in CRITS}}
    out["reconciliation_with_phase1"] = rec

    # 8. refit the Phase 1 monotone-table method (B2) on development 10-run modes, per prompt
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from rubric_scoring.calibration import fit_table
    dev = [r for r in rows if r["Set"] == "development" and r["human_grade"] is not None]
    refit = {}
    for raw in ("rubric", "human"):
        pairs = {c: [(r[raw + "_mode"], r["human_grade"]) for r in dev if r["Criterion"] == c] for c in CRITS}
        t = fit_table(pairs)
        refit[raw] = {c: {"refit": [t[c][k] for k in range(1, 6)], "reported": TABLES[raw][c],
                          "dev_pairs_by_raw_score": [sum(1 for a, _ in pairs[c] if a == k) for k in range(1, 6)]}
                      for c in CRITS}
    out["refit_on_development"] = refit
    # sensitivity: arm D rebuilt with the reproducible development refit of the human-like table
    tab = {c: refit["human"][c]["refit"] for c in CRITS}

    def d_prime(r):
        mapped = [tab[r["Criterion"]][x - 1] for x in r["human_runs"]]
        return Counter(mapped).most_common(1)[0][0]
    out["sensitivity_D_with_dev_refit_table"] = {
        "test": agree([d_prime(r) for r in test], [r["human_grade"] for r in test]),
        "test_instructor_1_to_3_exact": agree([d_prime(r) for r in test if r["human_grade"] <= 3],
                                              [r["human_grade"] for r in test if r["human_grade"] <= 3])["exact"]}

    # 9. compare recomputed test metrics with the reported metrics file
    rep = {(d["Set"], d["Criterion"], d["Method"]): d for d in csv.DictReader(open(REPORTED, newline="", encoding="utf-8-sig"))}
    worst = 0.0
    for s in ("development", "test"):
        for col, name in ARMS.values():
            r = rep[(s, "All five", name)]
            for k in ("exact", "mae", "within1", "mean_diff", "qwk"):
                worst = max(worst, abs(float(r[k]) - out["agreement"][s][name][k]))
    out["max_abs_difference_vs_reported_pooled_metrics"] = worst

    OUT.write_text(json.dumps(out, indent=2))
    print(json.dumps({k: out[k] for k in ("internal_checks", "max_abs_difference_vs_reported_pooled_metrics",
                                          "reconciliation_with_phase1")}, indent=2))


if __name__ == "__main__":
    main()
