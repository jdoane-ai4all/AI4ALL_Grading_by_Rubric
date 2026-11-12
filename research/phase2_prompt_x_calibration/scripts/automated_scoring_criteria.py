"""Phase 2 against conventional automated-scoring criteria (Williamson, Xi & Breyer, 2012, EM:IP 31(1)):
QWK >= .70, Pearson r >= .70, |standardised mean difference| <= .15. The human-human degradation criterion
needs a second human rating, which this study doesn't have.

Uses the current results (Revisions 1 + 2) on the locked test set; aggregate output only:
    research/phase2_prompt_x_calibration/metrics/automated_scoring_criteria.json

    python3 research/phase2_prompt_x_calibration/scripts/automated_scoring_criteria.py
"""
import csv
import json
import math
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))
import recalibrate_human_like as R  # noqa: E402
from verify_phase2 import qwk  # noqa: E402

rows = R.load()
labels = {d["project_id"]: d for d in csv.DictReader(open(ROOT / "data/private/labels.csv", encoding="utf-8-sig"))}
for r in rows:
    v = (labels.get(r["Project ID"], {}).get(R.KEY[r["Criterion"]]) or "").strip()
    r["g"] = int(v) if v else None
table = json.loads((ROOT / "research/phase2_prompt_x_calibration/calibration/human_like_table_dev_fit.json").read_text())
R.apply_table(rows, "human", table["table_outputs_for_raw_1_to_5"], "human_cal_rev")
test = [r for r in rows if r["Set"] == "test" and r["g"] is not None]
ARMS = {"Strict rubric": "rubric", "Strict rubric + calibration": "rubric_cal", "Human-like": "human",
        "Human-like + calibration": "human_cal_rev"}


def smd(a, h):
    sp = math.sqrt((st.pvariance(a) + st.pvariance(h)) / 2)
    return (st.mean(a) - st.mean(h)) / sp


def pearson(a, h):
    ma, mh = st.mean(a), st.mean(h)
    return sum((x - ma) * (y - mh) for x, y in zip(a, h)) / math.sqrt(
        sum((x - ma) ** 2 for x in a) * sum((y - mh) ** 2 for y in h))


h_all = [r["g"] for r in test]
out = {"criteria": {"qwk_min": 0.70, "pearson_min": 0.70, "abs_smd_max": 0.15,
                    "source": "Williamson, Xi & Breyer (2012), Educational Measurement: Issues and Practice 31(1)"},
       "n_test_grades": len(test), "human_mean": st.mean(h_all), "human_sd": st.pstdev(h_all), "arms": {}}
for name, c in ARMS.items():
    a = [r[c + "_mode"] for r in test]
    res = {"qwk": qwk(a, h_all), "pearson": pearson(a, h_all), "smd": smd(a, h_all), "ai_sd": st.pstdev(a),
           "by_criterion": {}}
    for cr in R.CRITS:
        aa = [r[c + "_mode"] for r in test if r["Criterion"] == cr]
        hh = [r["g"] for r in test if r["Criterion"] == cr]
        res["by_criterion"][cr] = {"qwk": qwk(aa, hh), "pearson": pearson(aa, hh), "smd": smd(aa, hh)}
    res["passes"] = {"qwk": res["qwk"] >= .70, "pearson": res["pearson"] >= .70, "smd": abs(res["smd"]) <= .15}
    out["arms"][name] = res
(ROOT / "research/phase2_prompt_x_calibration/metrics/automated_scoring_criteria.json").write_text(json.dumps(out, indent=2))
print(json.dumps({k: {m: round(v[m], 3) for m in ("qwk", "pearson", "smd", "ai_sd")} for k, v in out["arms"].items()}, indent=1))
