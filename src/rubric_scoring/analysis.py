"""Join predictions to labels AFTER scoring and compute the pre-specified analyses.

The test split can only be analysed when data/TEST_UNLOCKED exists. That file is
created by `cli unlock-test`, which records who unlocked it, when, and the frozen
prompt/policy hashes. Everything is reported with denominators.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import metrics as M
from .rubric import CRITERIA

UNLOCK_FILE = Path("data/TEST_UNLOCKED")


def unlock_test(who: str, frozen: dict) -> None:
    if UNLOCK_FILE.exists():
        raise FileExistsError("test set already unlocked")
    UNLOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    UNLOCK_FILE.write_text(json.dumps({"unlocked_by": who, "utc": datetime.now(timezone.utc).isoformat(),
                                       "frozen": frozen}, indent=2))


def _units(preds, labels, split_of, split, condition, replicate=1):
    """One unit per (project, criterion) for the requested split/condition/replicate."""
    out = []
    for p in preds:
        if p["condition"] != condition or p["replicate"] != replicate:
            continue
        pid = p["project_id"]
        lab = labels.get(pid)
        if not lab or not lab["eligible"] or split_of.get(pid) != split:
            continue
        out.append({"project_id": pid, "group_id": lab["group_id"], "cohort": lab["cohort"],
                    "criterion": p["criterion"], "human": lab[p["criterion"]],
                    "ai": p["score"], "status": p["status"]})
    return out


def analyse(preds: list[dict], labels: dict, registry: dict, config: dict, split: str = "development") -> dict:
    if split == "test" and not UNLOCK_FILE.exists():
        raise PermissionError("test split is locked; run `cli unlock-test` after freezing prompts and policy")
    split_of = registry["project_split"]
    reps = config["metrics"]["bootstrap_reps"]
    thr = config["metrics"]["decision_threshold_total"]
    results = {"split": split, "generated_utc": datetime.now(timezone.utc).isoformat(), "conditions": {}}

    for cond in config["scoring"]["conditions"]:
        units = _units(preds, labels, split_of, split, cond)
        if not units:
            continue
        res = {"criteria": {}, "total": None}
        for c in CRITERIA:
            cu = [u for u in units if u["criterion"] == c]
            scored = [u for u in cu if u["status"] == "scored"]
            pt = M.criterion_point([u["human"] for u in scored], [u["ai"] for u in scored])
            pt["n_calls"] = len(cu)
            pt["coverage"] = len(scored) / len(cu) if cu else float("nan")
            pt["n_abstain"] = sum(u["status"] == "abstain" for u in cu)
            pt["n_failed"] = sum(u["status"] == "failed" for u in cu)
            pt["confusion_human_rows_ai_cols"] = M.confusion([u["human"] for u in scored],
                                                               [u["ai"] for u in scored]).tolist()
            pt["mae_ci"] = M.cluster_bootstrap(
                scored, "group_id", lambda s: float(np.mean([abs(u["ai"] - u["human"]) for u in s])) if s else float("nan"),
                reps)["ci95"]
            pt["qwk_ci"] = M.cluster_bootstrap(
                scored, "group_id", lambda s: M.weighted_kappa([u["human"] for u in s], [u["ai"] for u in s]), reps)["ci95"]
            res["criteria"][c] = pt

        # Totals: only projects with all six criteria scored (denominator reported).
        per_proj = defaultdict(dict)
        meta = {}
        for u in units:
            per_proj[u["project_id"]][u["criterion"]] = u
            meta[u["project_id"]] = u["group_id"]
        complete = {pid: d for pid, d in per_proj.items()
                    if len(d) == 6 and all(x["status"] == "scored" for x in d.values())}
        if len(complete) >= 3:
            ht = [sum(d[c]["human"] for c in CRITERIA) for d in complete.values()]
            at = [sum(d[c]["ai"] for c in CRITERIA) for d in complete.values()]
            se = [sum(abs(d[c]["ai"] - d[c]["human"]) for c in CRITERIA) for d in complete.values()]
            tot = M.total_point(ht, at, thr, se)
            tot["n_projects_in_split"] = len(per_proj)
            tot["n_projects_all_six_scored"] = len(complete)
            tunits = [{"group_id": meta[pid], "h": h, "a": a} for pid, h, a in zip(complete, ht, at)]
            tot["mae_ci"] = M.cluster_bootstrap(tunits, "group_id",
                                                lambda s: float(np.mean([abs(u["a"] - u["h"]) for u in s])), reps)["ci95"]
            tot["icc_ci"] = M.cluster_bootstrap(tunits, "group_id",
                                                lambda s: M.icc_a1([u["h"] for u in s], [u["a"] for u in s]), reps)["ci95"]
            res["total"] = tot
        results["conditions"][cond] = res

    results["paired_contrasts"] = _contrasts(preds, labels, split_of, split, config, reps)
    results["stability"] = _stability(preds, labels, split_of, split, config)
    return results


def _contrasts(preds, labels, split_of, split, config, reps):
    out = {}
    pairs = [config["scoring"]["primary_contrast"]] + config["scoring"]["secondary_contrasts"]
    for a, b in pairs:
        ua = {(u["project_id"], u["criterion"]): u for u in _units(preds, labels, split_of, split, a)}
        ub = {(u["project_id"], u["criterion"]): u for u in _units(preds, labels, split_of, split, b)}
        common = [k for k in ua if k in ub and ua[k]["status"] == ub[k]["status"] == "scored"]
        if not common:
            continue
        rows = [{"group_id": ua[k]["group_id"], "ea": abs(ua[k]["ai"] - ua[k]["human"]),
                 "eb": abs(ub[k]["ai"] - ub[k]["human"]), "crit": k[1]} for k in common]
        res = {"n_pairs_both_scored": len(common),
               "pooled_mae_diff_A_minus_B": M.paired_difference(
                   rows, "group_id", lambda s: float(np.mean([r["ea"] for r in s])),
                   lambda s: float(np.mean([r["eb"] for r in s])), reps)}
        res["by_criterion"] = {}
        for c in CRITERIA:
            rc = [r for r in rows if r["crit"] == c]
            if rc:
                res["by_criterion"][c] = M.paired_difference(
                    rc, "group_id", lambda s: float(np.mean([r["ea"] for r in s])),
                    lambda s: float(np.mean([r["eb"] for r in s])), reps)
        out[f"{a}__vs__{b}"] = res
    return out


def _stability(preds, labels, split_of, split, config):
    out = {}
    for cond in config["scoring"]["conditions"]:
        rs = defaultdict(list)
        for p in preds:
            if p["condition"] == cond and split_of.get(p["project_id"]) == split:
                rs[(p["project_id"], p["criterion"])].append(p["score"])
        if any(len(v) > 1 for v in rs.values()):
            out[cond] = M.stability(rs)
    return out


def write_markdown(results: dict, path: str | Path) -> None:
    L = [f"# Results - {results['split']} split", "",
         f"Generated {results['generated_utc']}. All values computed from logged model outputs joined to "
         "historical scores after scoring. CIs: 95% percentile, project-group cluster bootstrap.", ""]
    for cond, r in results["conditions"].items():
        L += [f"## {cond}", "", "| Criterion | calls | coverage | n scored | MAE [95% CI] | exact | within 1 | severe | bias | QWK [95% CI] | human<=3 n |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        for c, m in r["criteria"].items():
            L.append(f"| {c} | {m['n_calls']} | {m['coverage']:.2f} | {m['n']} | {m['mae']:.2f} [{m['mae_ci'][0]:.2f}, {m['mae_ci'][1]:.2f}] "
                     f"| {m['exact']:.2f} | {m['within_one']:.2f} | {m['severe_rate']:.2f} | {m['signed_bias']:+.2f} "
                     f"| {m['qwk']:.2f} [{m['qwk_ci'][0]:.2f}, {m['qwk_ci'][1]:.2f}] | {m['n_human_low']} |")
        t = r.get("total")
        if t:
            L += ["", f"Total (n={t['n_projects_all_six_scored']} of {t['n_projects_in_split']} with all six scored): "
                  f"MAE {t['mae']:.2f} [{t['mae_ci'][0]:.2f}, {t['mae_ci'][1]:.2f}]; ICC(A,1) {t['icc_a1']:.2f} "
                  f"[{t['icc_ci'][0]:.2f}, {t['icc_ci'][1]:.2f}]; bias {t['signed_bias']:+.2f}; "
                  f"agreement at 24/30 threshold {t['threshold_agreement']:.2f}; cancellation ratio {t.get('cancellation_ratio', float('nan')):.2f}."]
        L.append("")
    Path(path).write_text("\n".join(L))
