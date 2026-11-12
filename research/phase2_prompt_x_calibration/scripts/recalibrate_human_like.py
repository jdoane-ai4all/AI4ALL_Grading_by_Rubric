"""Phase 2 current results: Revision 1 (development-only refit of the human-like calibration table) and
Revision 2 (Phase 1's PI-corrected `project-199` Project Description label). Recomputes every number.

Revision 2: Phase 2 used an uncorrected workbook row for `project-199`, so its Project Description label was
missing (419 test labels, 83 complete totals). Labels now come from Phase 1's `data/private/labels.csv`
(PI-corrected, DECISION_LOG D-14). The script stops unless that is the only label that changes, giving 420
test labels and 84 complete totals. This affects the test numbers of every arm.

- The fitting method is Phase 1's registered B2 method (`rubric_scoring.calibration.fit_table`): the median
  instructor grade for each raw grade, made monotone by pooling adjacent violators. A raw grade with no
  development decks is filled by the mean development shift, and the table is kept monotone. It is fitted
  on the 10-run modes of the 46 development decks; no test labels are used.
- Application is unchanged from Phase 2: each of the 10 runs is mapped through the table and the mode of
  the mapped runs is the reported grade. A tie between mapped grades (none occurred) would fall back to
  mapping the raw mode.
- Arms A, B and C are unchanged. The strict table refits to exactly Phase 1's registered table.

The metrics are computed exactly as in the delivered metrics workbook: first the script recomputes the
workbook's A, B and C rows and stops if any differs.

Reads the private joined table; writes aggregate outputs only:
    research/phase2_prompt_x_calibration/calibration/human_like_table_dev_fit.json
    research/phase2_prompt_x_calibration/metrics/evaluation_metrics_revised.csv
    research/phase2_prompt_x_calibration/metrics/AI_Grading_Evaluation_Metrics_revised.xlsx
    research/phase2_prompt_x_calibration/metrics/revised_results.json (and the generated tables in FINDINGS.md, README.md)

    python3 research/phase2_prompt_x_calibration/scripts/recalibrate_human_like.py
"""
from __future__ import annotations

import csv
import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))
from rubric_scoring.calibration import fit_table  # noqa: E402
from verify_phase2 import CRITS, KEY, TABLES, agree, pearson, runs  # noqa: E402

P2 = ROOT / "research/phase2_prompt_x_calibration"
JOINED = ROOT / "data/private/phase2/grading_four_methods_joined_by_project.csv"
REPORTED = P2 / "metrics/evaluation_metrics.csv"
METHODS = ["Strict rubric", "Strict rubric + calibration", "Human-like", "Human-like + calibration"]
COLS = {"Strict rubric": "rubric", "Strict rubric + calibration": "rubric_cal", "Human-like": "human",
        "Human-like + calibration": "human_cal"}


def load() -> list[dict]:
    rows = list(csv.DictReader(open(JOINED, newline="", encoding="utf-8-sig")))
    for r in rows:
        r["g"] = int(float(r["Historical human grade"])) if r["Historical human grade"] else None
        for c in COLS.values():
            r[c + "_runs"] = runs(r[f"{c} 10 runs"])
            r[c + "_mode"] = int(r[f"{c} mode"])
    return rows


def fit_dev(rows: list[dict], raw: str) -> dict[str, list[int]]:
    dev = [r for r in rows if r["Set"] == "development" and r["g"] is not None]
    pairs = {c: [(r[raw + "_mode"], r["g"]) for r in dev if r["Criterion"] == c] for c in CRITS}
    t = fit_table(pairs)
    return {c: [t[c][k] for k in range(1, 6)] for c in CRITS}


def apply_table(rows: list[dict], raw: str, table: dict, col: str) -> int:
    ties = 0
    for r in rows:
        mapped = [table[r["Criterion"]][x - 1] for x in r[raw + "_runs"]]
        top = Counter(mapped).most_common()
        if len(top) > 1 and top[0][1] == top[1][1]:
            ties += 1
            mode = table[r["Criterion"]][r[raw + "_mode"] - 1]
        else:
            mode = top[0][0]
        r[col + "_runs"], r[col + "_mode"] = mapped, mode
    return ties


def unanimous(r, col):
    return len(set(r[col + "_runs"])) == 1


def pairwise(r, col):
    x = r[col + "_runs"]
    return sum(a == b for i, a in enumerate(x) for b in x[i + 1:]) / 45


def metric_rows(rows: list[dict], cols: dict) -> list[dict]:
    """The delivered workbook's rows: pooled by set, plus per-criterion on test."""
    out = []
    specs = [(s, "All five") for s in ("development", "test", "all")] + [("test", c) for c in CRITS]
    for s, crit in specs:
        sub = [r for r in rows if r["g"] is not None and (s == "all" or r["Set"] == s)
               and (crit == "All five" or r["Criterion"] == crit)]
        for m in METHODS:
            col = cols[m]
            a = agree([r[col + "_mode"] for r in sub], [r["g"] for r in sub])
            out.append({"Set": s, "Criterion": crit, "Method": m, "Valid labels": len(sub),
                        "Projects": len({r["Project ID"] for r in sub}), "exact": a["exact"], "mae": a["mae"],
                        "within1": a["within1"], "mean_diff": a["mean_diff"], "over_rate": a["over_rate"],
                        "under_rate": a["under_rate"], "qwk": a["qwk"],
                        "unanimous_rate": sum(unanimous(r, col) for r in sub) / len(sub),
                        "pairwise_rate": sum(pairwise(r, col) for r in sub) / len(sub)})
    return out


def _pct(x):
    return f"{x * 100:.1f}%"


def _md(header, rows):
    return "\n".join(["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] +
                      ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def render_docs(out: dict, revised: list[dict]) -> None:
    """Write the generated tables into FINDINGS.md and README.md between <!-- auto:NAME --> markers."""
    ARMS = [("A · Strict", "Strict rubric"), ("B · Strict + cal", "Strict rubric + calibration"),
            ("C · Human-like", "Human-like"), ("D · Human-like + cal", "Human-like + calibration")]
    M = {(m["Set"], m["Criterion"], m["Method"]): m for m in revised}
    ex = out["test_exact_counts"]
    a5 = out["always5_test"]
    n = out["test_labels"]
    t = {}
    t["main"] = _md(["Arm", "Exact", "MAE", "Within ±1", "Bias (AI − human)", "QWK", "Unanimous (test)", "Pairwise (test)"],
                    [[lab, f"{_pct(M[('test', 'All five', m)]['exact'])} ({ex[m]})", f"{M[('test', 'All five', m)]['mae']:.3f}",
                      _pct(M[("test", "All five", m)]["within1"]), f"{M[('test', 'All five', m)]['mean_diff']:+.3f}",
                      f"{M[('test', 'All five', m)]['qwk']:.3f}", _pct(M[("test", "All five", m)]["unanimous_rate"]),
                      _pct(M[("test", "All five", m)]["pairwise_rate"])] for lab, m in ARMS] +
                    [["Always 5 (baseline)", f"{_pct(a5['exact'])} ({round(a5['exact'] * n)})", f"{a5['mae']:.3f}",
                      _pct(a5["within1"]), f"{a5['mean_diff']:+.3f}", "0", "—", "—"]])
    lo = out["instructor_1_to_3"]
    t["headline"] = _md(["Arm", "Exact", "MAE", "Within ±1", "Bias (AI − human)", "QWK",
                         f"Exact when instructor gave 1–3 (n = {lo['Strict rubric']['n']})"],
                        [[lab, _pct(M[("test", "All five", m)]["exact"]), f"{M[('test', 'All five', m)]['mae']:.3f}",
                          _pct(M[("test", "All five", m)]["within1"]), f"{M[('test', 'All five', m)]['mean_diff']:+.3f}",
                          f"{M[('test', 'All five', m)]['qwk']:.3f}", _pct(lo[m]["exact"])] for lab, m in ARMS] +
                        [["Always 5 (baseline)", _pct(a5["exact"]), f"{a5['mae']:.3f}", _pct(a5["within1"]),
                          f"{a5['mean_diff']:+.3f}", "0", "0%"]])
    b = out["bootstrap_test_5000"]
    t["bootstrap"] = _md(["Contrast", "Exact agreement", "MAE improvement"],
                         [[k, f"{b[k]['exact']['point'] * 100:+.1f} pp [{b[k]['exact']['ci95'][0] * 100:+.1f}, "
                              f"{b[k]['exact']['ci95'][1] * 100:+.1f}]",
                           f"{b[k]['mae']['point']:+.3f} [{b[k]['mae']['ci95'][0]:+.3f}, {b[k]['mae']['ci95'][1]:+.3f}]"]
                          for k in ("B vs A", "D vs C", "D vs B")])
    rows = []
    for c in CRITS:
        vals = [M[("test", c, m)]["exact"] for _, m in ARMS]
        best = max(vals)
        rows.append([c, M[("test", c, ARMS[0][1])]["Valid labels"]] +
                    [f"**{_pct(v)}**" if abs(v - best) < 1e-12 and len(set(vals)) > 1 else _pct(v) for v in vals])
    t["by_criterion"] = _md(["Criterion", "Labels"] + [lab for lab, _ in ARMS], rows)
    ld = out["test_label_distribution"]
    t["labels"] = _md(["Grade", "1", "2", "3", "4", "5"], [["Labels"] + [ld.get(str(k), ld.get(k, 0)) for k in range(1, 6)]])
    md = out["test_mode_distribution"]
    t["modes"] = _md(["Arm", "1", "2", "3", "4", "5"],
                     [[lab] + [md[m].get(str(k), md[m].get(k, 0)) for k in range(1, 6)] for lab, m in ARMS] +
                     [["Instructors"] + [ld.get(str(k), ld.get(k, 0)) for k in range(1, 6)]])
    tt = out["totals"]
    np_ = tt["projects"]
    t["totals"] = _md(["Arm", "Mean predicted", "Total MAE", "RMSE", "Exact total", "Pearson r with human", "Bias"],
                      [[lab, f"{tt[m]['mean_pred']:.2f}", f"{tt[m]['mae']:.2f}", f"{tt[m]['rmse']:.2f}",
                        f"{tt[m]['exact']}/{np_}", f"{tt[m]['pearson']:.3f}", f"{tt[m]['mean_diff']:+.3f}"] for lab, m in ARMS] +
                      [["Always 25 (baseline)", "25", f"{tt['Always 5 (25 per project)']['mae']:.2f}", "—",
                        f"{tt['Always 5 (25 per project)']['exact']}/{np_}", "—",
                        f"+{tt['Always 5 (25 per project)']['mae']:.2f}"]])
    rp = out["repeatability_all_990"]
    t["repeat"] = _md(["Arm", "All 10 runs identical", "Mean pairwise agreement", "Mean modal share"],
                      [[lab, f"{rp[m]['unanimous']} ({_pct(rp[m]['unanimous_rate'])})", _pct(rp[m]["pairwise"]),
                        _pct(rp[m]["modal_share"])] for lab, m in ARMS])
    t["other"] = _md(["Arm", "Development exact (230)", "Development MAE",
                      f"Pooled exact ({M[('all', 'All five', ARMS[0][1])]['Valid labels']})", "Pooled MAE"],
                     [[lab, _pct(M[("development", "All five", m)]["exact"]), f"{M[('development', 'All five', m)]['mae']:.3f}",
                       _pct(M[("all", "All five", m)]["exact"]), f"{M[('all', 'All five', m)]['mae']:.3f}"] for lab, m in ARMS])
    import re as _re
    t = {k: _re.sub(r"(?<![\w\[])-(?=\d)", "−", v) for k, v in t.items()}     # typographic minus, as in the docs
    for path in (P2 / "FINDINGS.md", P2 / "README.md"):
        text = path.read_text()
        for name, table in t.items():
            text = _re.sub(rf"(<!-- auto:{name} -->\n).*?(\n<!-- /auto:{name} -->)",
                           lambda mm: mm.group(1) + table + mm.group(2), text, flags=_re.S)
        path.write_text(text)


def main() -> None:
    rows = load()

    # 0. the method must reproduce the delivered workbook before it is trusted for the revision
    rep = {(d["Set"], d["Criterion"], d["Method"]): d for d in csv.DictReader(open(REPORTED, encoding="utf-8-sig"))}
    worst = 0.0
    for m in metric_rows(rows, COLS):
        d = rep[(m["Set"], m["Criterion"], m["Method"])]
        for k in ("exact", "mae", "within1", "mean_diff", "over_rate", "under_rate", "qwk", "unanimous_rate",
                  "pairwise_rate"):
            worst = max(worst, abs(float(d[k]) - m[k]))
    assert worst < 1e-9, f"metric code does not reproduce the delivered workbook (max diff {worst})"

    # Revision 2: labels from Phase 1's PI-corrected labels.csv (only project-199 Project Description differs)
    labels = {d["project_id"]: d for d in csv.DictReader(open(ROOT / "data/private/labels.csv", encoding="utf-8-sig"))}
    fixes = []
    for r in rows:
        v = (labels.get(r["Project ID"], {}).get(KEY[r["Criterion"]]) or "").strip()
        new = int(v) if v else None
        if new != r["g"]:
            fixes.append((r["Project ID"], r["Criterion"], r["Set"]))
            r["g"] = new
    assert fixes == [("project-199", "Project Description", "test")], fixes

    # 1. fit on development only
    strict_refit = fit_dev(rows, "rubric")
    assert strict_refit == TABLES["rubric"], "strict table should refit to Phase 1's registered table"
    human_table = fit_dev(rows, "human")
    dev = [r for r in rows if r["Set"] == "development" and r["g"] is not None]
    support = {c: [sum(1 for r in dev if r["Criterion"] == c and r["human_mode"] == k) for k in range(1, 6)]
               for c in CRITS}
    (P2 / "calibration").mkdir(exist_ok=True)
    (P2 / "calibration/human_like_table_dev_fit.json").write_text(json.dumps({
        "name": "Human-like calibration table, revision 1 (development fit)",
        "method": "Phase 1 B2: median instructor grade per raw grade, monotone pooling (PAVA), unseen raw grades "
                  "filled with the mean development shift, then forced monotone",
        "fitted_on": "46 development decks, 10-run modes of the human-like prompt; no test labels",
        "table_outputs_for_raw_1_to_5": human_table,
        "development_decks_per_raw_grade_1_to_5": support,
        "replaces (as delivered, fitting procedure undocumented)": TABLES["human"],
        "strict_table_refit_equals_phase1_registered_table": True,
    }, indent=2))

    # 2. apply to every deck (test is the evaluation set)
    ties = apply_table(rows, "human", human_table, "human_cal_rev")
    cols_rev = dict(COLS, **{"Human-like + calibration": "human_cal_rev"})
    revised = metric_rows(rows, cols_rev)
    with open(P2 / "metrics/evaluation_metrics_revised.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(revised[0]))
        w.writeheader()
        w.writerows(revised)

    # 3. everything else that involves arm D
    out: dict = {"mapped_mode_ties": ties, "human_like_table_dev_fit": human_table,
                 "development_support": support,
                 "label_corrections": [{"project": p, "criterion": c, "set": st} for p, c, st in fixes],
                 "test_labels": sum(1 for r in rows if r["Set"] == "test" and r["g"] is not None)}
    test = [r for r in rows if r["Set"] == "test" and r["g"] is not None]
    base = [5] * len(test)
    out["always5_test"] = agree(base, [r["g"] for r in test])
    for name, cond in (("instructor_1_to_3", lambda g: g <= 3), ("instructor_5", lambda g: g == 5)):
        sub = [r for r in test if cond(r["g"])]
        out[name] = {m: {"n": len(sub), "exact_count": sum(r[c + "_mode"] == r["g"] for r in sub),
                         "exact": sum(r[c + "_mode"] == r["g"] for r in sub) / len(sub),
                         "mean_diff": sum(r[c + "_mode"] - r["g"] for r in sub) / len(sub)}
                     for m, c in cols_rev.items()}
    out["test_label_distribution"] = dict(sorted(Counter(r["g"] for r in test).items()))
    out["test_mode_distribution"] = {m: dict(sorted(Counter(r[c + "_mode"] for r in test).items()))
                                     for m, c in cols_rev.items()}
    out["test_exact_counts"] = {m: sum(r[c + "_mode"] == r["g"] for r in test) for m, c in cols_rev.items()}
    out["test_within1_counts"] = {m: sum(abs(r[c + "_mode"] - r["g"]) <= 1 for r in test) for m, c in cols_rev.items()}
    # per-criterion bias/MAE on test for D (FINDINGS §6 cites them)
    out["test_by_criterion"] = {c: {m: agree([r[col + "_mode"] for r in test if r["Criterion"] == c],
                                             [r["g"] for r in test if r["Criterion"] == c])
                                    for m, col in cols_rev.items()} for c in CRITS}
    # convergence: how often do the two calibrated arms (and the two raw prompts) give the same grade?
    out["same_grade_test"] = {c: {"B_vs_revised_D": sum(r["human_cal_rev_mode"] == r["rubric_cal_mode"] for r in test
                                                         if c == "All five" or r["Criterion"] == c),
                                  "A_vs_C_raw": sum(r["human_mode"] == r["rubric_mode"] for r in test
                                                    if c == "All five" or r["Criterion"] == c),
                                  "n": sum(1 for r in test if c == "All five" or r["Criterion"] == c)}
                              for c in ["All five"] + CRITS}
    # totals: 83 test projects with all five labels
    byp = defaultdict(list)
    for r in test:
        byp[r["Project ID"]].append(r)
    comp = [rs for rs in byp.values() if len(rs) == 5]
    hum = [sum(r["g"] for r in rs) for rs in comp]
    out["totals"] = {"projects": len(comp), "human_mean": sum(hum) / len(hum)}
    for m, c in cols_rev.items():
        pred = [sum(r[c + "_mode"] for r in rs) for rs in comp]
        d = [p - h for p, h in zip(pred, hum)]
        out["totals"][m] = {"mean_pred": sum(pred) / len(pred), "mae": sum(map(abs, d)) / len(d),
                            "rmse": math.sqrt(sum(x * x for x in d) / len(d)), "exact": sum(x == 0 for x in d),
                            "pearson": pearson(pred, hum), "mean_diff": sum(d) / len(d)}
    out["totals"]["Always 5 (25 per project)"] = {"mae": sum(25 - h for h in hum) / len(hum),
                                                  "exact": sum(h == 25 for h in hum)}
    # repeatability across all 990 groups
    out["repeatability_all_990"] = {m: {"unanimous": sum(unanimous(r, c) for r in rows),
                                        "unanimous_rate": sum(unanimous(r, c) for r in rows) / len(rows),
                                        "pairwise": sum(pairwise(r, c) for r in rows) / len(rows),
                                        "modal_share": sum(Counter(r[c + "_runs"]).most_common(1)[0][1] / 10
                                                           for r in rows) / len(rows)}
                                    for m, c in cols_rev.items()}
    # project-cluster bootstrap for the contrasts that involve D (5,000 resamples)
    rng = random.Random(20261104)
    pids = sorted(byp)
    keys = {"B vs A": ("rubric_cal", "rubric"), "D vs C": ("human_cal_rev", "human"),
            "D vs B": ("human_cal_rev", "rubric_cal")}
    reps = {k: {"exact": [], "mae": []} for k in keys}
    for _ in range(5000):
        rs = [r for p in (rng.choice(pids) for _ in pids) for r in byp[p]]
        ref = [r["g"] for r in rs]
        for k, (a, b) in keys.items():
            ma, mb = agree([r[a + "_mode"] for r in rs], ref), agree([r[b + "_mode"] for r in rs], ref)
            reps[k]["exact"].append(ma["exact"] - mb["exact"])
            reps[k]["mae"].append(mb["mae"] - ma["mae"])          # positive = D has lower error
    point = {k: {"exact": agree([r[a + "_mode"] for r in test], [r["g"] for r in test])["exact"]
                 - agree([r[b + "_mode"] for r in test], [r["g"] for r in test])["exact"],
                 "mae": agree([r[b + "_mode"] for r in test], [r["g"] for r in test])["mae"]
                 - agree([r[a + "_mode"] for r in test], [r["g"] for r in test])["mae"]} for k, (a, b) in keys.items()}
    out["bootstrap_test_5000"] = {k: {s: {"point": point[k][s], "ci95": [sorted(v)[124], sorted(v)[4874]]}
                                      for s, v in reps[k].items()} for k in keys}

    (P2 / "metrics/revised_results.json").write_text(json.dumps(out, indent=2))
    render_docs(out, revised)

    # 4. revised workbook (same layout as delivered, with a revision note in the Guide)
    try:
        import openpyxl
        from openpyxl.styles import Font
        wb = openpyxl.load_workbook(P2 / "metrics/AI_Grading_Evaluation_Metrics.xlsx")
        ws = wb["Evaluation Metrics"]
        idx = {(ws.cell(i, 1).value, ws.cell(i, 2).value, ws.cell(i, 3).value): i for i in range(2, ws.max_row + 1)}
        heads = [ws.cell(1, j).value for j in range(1, ws.max_column + 1)]
        for m in revised:
            i = idx[(m["Set"], m["Criterion"], m["Method"])]
            for j, h in enumerate(heads, start=1):
                ws.cell(i, j).value = m[h]
        g = wb["Guide"]
        g.append(["Revision 1 (2026-11-04)",
                  "Human-like + calibration rows recomputed with a calibration table refitted on the 46 development "
                  "decks only (Phase 1 B2 method; calibration/human_like_table_dev_fit.json)."])
        g.cell(g.max_row, 1).font = Font(bold=True)
        g.append(["Revision 2 (2026-11-04)",
                  "project-199 Project Description label restored from the PI-corrected Phase 1 labels: test and all "
                  "rows of every method recomputed (420 test labels, 650 labelled)."])
        g.cell(g.max_row, 1).font = Font(bold=True)
        for r in range(1, g.max_row + 1):
            if g.cell(r, 1).value == "Locked test note":
                g.cell(r, 2).value = "84 test decks; 420 criterion labels after Revision 2 (419 as delivered)"
        wb.save(P2 / "metrics/AI_Grading_Evaluation_Metrics_revised.xlsx")
    except ImportError:
        pass
    print(json.dumps({"reproduces_delivered_workbook": True, "mapped_mode_ties": ties,
                      "human_like_table_dev_fit": human_table}, indent=1))


if __name__ == "__main__":
    main()
