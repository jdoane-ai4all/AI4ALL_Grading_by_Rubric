"""Grouped, stratified development / locked-test split with a tamper-evident registry.

* Unit of assignment = provisional duplicate/version group, so copies and versions of
  a project never straddle the split.
* Strata = cohort x total-score band (band edges at the 24/30 nomination threshold).
* Within each stratum, groups are shuffled with a fixed seed and allocated so that
  each stratum contributes ~dev_fraction of its groups to development (largest-
  remainder rounding keeps the overall count exact).
* The registry is written once. Re-running refuses to overwrite it.
"""
from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .data import LabelRow


def total_band(total: float, bands: dict) -> str:
    for name, (lo, hi) in bands.items():
        if lo <= total <= hi:
            return name
    raise ValueError(f"total {total} outside configured bands")


def group_strata(rows: list[LabelRow], bands: dict) -> dict[str, str]:
    by_group: dict[str, list[LabelRow]] = defaultdict(list)
    for r in rows:
        if r.eligible:
            by_group[r.group_id].append(r)
    strata = {}
    for g, rs in by_group.items():
        cohort = sorted({r.cohort for r in rs})[0]
        mean_total = sum(r.total for r in rs) / len(rs)
        strata[g] = f"{cohort}|{total_band(round(mean_total), bands)}"
    return strata


def allocate(strata: dict[str, str], dev_fraction: float, seed: int) -> dict[str, str]:
    rng = random.Random(seed)
    members: dict[str, list[str]] = defaultdict(list)
    for g, s in sorted(strata.items()):
        members[s].append(g)
    n_total = len(strata)
    n_dev_target = round(dev_fraction * n_total)
    quotas = {s: dev_fraction * len(m) for s, m in members.items()}
    alloc = {s: int(q) for s, q in quotas.items()}
    remainder = n_dev_target - sum(alloc.values())
    # largest remainder, ties broken by seeded shuffle for determinism
    order = sorted(quotas, key=lambda s: (-(quotas[s] - int(quotas[s])), s))
    for s in order[: max(remainder, 0)]:
        alloc[s] += 1
    assignment = {}
    for s in sorted(members):
        gs = members[s][:]
        rng.shuffle(gs)
        for i, g in enumerate(gs):
            assignment[g] = "development" if i < alloc[s] else "test"
    return assignment


def assignment_hash(assignment: dict[str, str]) -> str:
    payload = json.dumps(sorted(assignment.items()), separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def build_registry(rows: list[LabelRow], config: dict) -> dict:
    sp = config["split"]
    strata = group_strata(rows, sp["total_bands"])
    assignment = allocate(strata, sp["development_fraction"], sp["seed"])
    project_split = {}
    for r in rows:
        if r.eligible and r.group_id in assignment:
            project_split[r.project_id] = assignment[r.group_id]
        else:
            # Unlabeled/ineligible artifacts: usable only for label-free checks
            # (abstention behaviour, extraction QA), never for agreement metrics.
            # A group with ANY eligible artifact follows that group's split.
            project_split[r.project_id] = assignment.get(r.group_id, "unlabeled_pool")
    summary = defaultdict(lambda: {"development": 0, "test": 0})
    for g, s in strata.items():
        summary[s][assignment[g]] += 1
    return {
        "study_id": config["study_id"],
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "seed": sp["seed"],
        "unit": sp["unit"],
        "development_fraction": sp["development_fraction"],
        "group_assignment": dict(sorted(assignment.items())),
        "group_stratum": dict(sorted(strata.items())),
        "project_split": dict(sorted(project_split.items())),
        "stratum_counts": dict(sorted(summary.items())),
        "assignment_sha256": assignment_hash(assignment),
        "label_exposure_note": (
            "Aggregate label distributions were inspected during data QA before this split. "
            "Individual test labels must not be viewed again until the test set is unlocked."
        ),
    }


def write_registry(registry: dict, path: str | Path, overwrite: bool = False) -> Path:
    path = Path(path)
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} exists; the split is locked. Delete deliberately and log why.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2))
    return path


def verify_registry(path: str | Path) -> bool:
    reg = json.loads(Path(path).read_text())
    return assignment_hash(reg["group_assignment"]) == reg["assignment_sha256"]
