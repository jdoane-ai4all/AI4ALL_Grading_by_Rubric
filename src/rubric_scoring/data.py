"""Label loading with an explicit column allowlist.

The `Data` tab is exported as CSV and read by column LETTER (the layout is
documented in docs/PROTOCOL.md). Only allowlisted columns are ever read, so
student-name lookup columns (AJ:AK) and other tabs never enter memory.

Labels produced here are used ONLY for splitting (stratification) and for the
post-scoring join. They are never passed to the scorer.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

from .rubric import CRITERIA


def col_index(letter: str) -> int:
    """Spreadsheet column letter -> zero-based index ('A'->0, 'AA'->26)."""
    n = 0
    for ch in letter.strip().upper():
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _to_int(v: str):
    v = (v or "").strip()
    if v == "":
        return None
    try:
        f = float(v)
    except ValueError:
        return None
    return int(f) if f.is_integer() else None


@dataclass
class LabelRow:
    project_id: str
    group_id: str
    cohort: str
    scores: dict  # criterion -> int | None
    total_reported: int | None
    artifact_equivalence: str = ""
    exclusion_reasons: list = field(default_factory=list)

    @property
    def total(self):
        vals = [self.scores[c] for c in CRITERIA]
        return sum(vals) if all(v is not None for v in vals) else None

    @property
    def eligible(self) -> bool:
        return not self.exclusion_reasons


def load_labels(csv_path: str | Path, config: dict, header_rows: int = 1, source: str = "label_source") -> list[LabelRow]:
    cols = config[source]["columns"]
    forbidden = {col_index(c) for c in config[source]["never_load_columns"]}
    idx = {k: col_index(v) for k, v in cols.items()}
    assert not (set(idx.values()) & forbidden), "allowlist overlaps forbidden columns"

    rows: list[LabelRow] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for i, raw in enumerate(reader):
            if i < header_rows:
                continue
            get = lambda k: raw[idx[k]].strip() if idx[k] < len(raw) else ""  # noqa: E731
            pid = get("project_id")
            if not pid:
                continue
            scores = {c: _to_int(get(c)) for c in CRITERIA}
            row = LabelRow(
                project_id=pid,
                group_id=get("duplicate_group") or pid,
                cohort=get("cohort") or "UNKNOWN",
                scores=scores,
                total_reported=_to_int(get("total")),
                artifact_equivalence=get("artifact_equivalence"),
            )
            apply_label_gates(row)
            rows.append(row)
    return rows


def apply_label_gates(row: LabelRow) -> None:
    """Pre-specified label-quality gates. Never repairs or imputes a label."""
    vals = [row.scores[c] for c in CRITERIA]
    if all(v is None for v in vals):
        row.exclusion_reasons.append("no_located_label")
        return
    if any(v is None for v in vals):
        row.exclusion_reasons.append("partial_vector")
    elif any(not (1 <= v <= 5) for v in vals):
        row.exclusion_reasons.append("out_of_range_score")
    if row.total is not None and row.total_reported is not None and row.total != row.total_reported:
        row.exclusion_reasons.append("total_mismatch")


def eligibility_flow(rows: list[LabelRow]) -> dict:
    """Counts for the CONSORT-style eligibility diagram (artifacts and groups)."""
    reasons: dict[str, int] = {}
    for r in rows:
        for x in r.exclusion_reasons:
            reasons[x] = reasons.get(x, 0) + 1
    eligible = [r for r in rows if r.eligible]
    groups_all = {r.group_id for r in rows}
    groups_elig = {r.group_id for r in eligible}
    # A group is mixed if some artifacts are eligible and some are not.
    mixed = {g for g in groups_elig if any(r.group_id == g and not r.eligible for r in rows)}
    by_cohort: dict[str, dict] = {}
    for r in rows:
        d = by_cohort.setdefault(r.cohort, {"artifacts": 0, "eligible_artifacts": 0})
        d["artifacts"] += 1
        d["eligible_artifacts"] += int(r.eligible)
    return {
        "artifacts_total": len(rows),
        "groups_total": len(groups_all),
        "artifacts_eligible": len(eligible),
        "groups_eligible": len(groups_elig),
        "groups_with_mixed_eligibility": len(mixed),
        "exclusion_reasons": reasons,
        "by_cohort": by_cohort,
    }


def score_distribution(rows: list[LabelRow]) -> dict:
    out = {}
    for c in CRITERIA:
        counts = {str(k): 0 for k in range(1, 6)}
        for r in rows:
            if r.eligible:
                counts[str(r.scores[c])] += 1
        out[c] = counts
    return out


def write_label_table(rows: list[LabelRow], path: str | Path) -> None:
    """Writes the PRIVATE label table (data/ is git-ignored)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["project_id", "group_id", "cohort", *CRITERIA, "total", "eligible", "exclusion_reasons"])
        for r in rows:
            w.writerow([r.project_id, r.group_id, r.cohort, *[r.scores[c] for c in CRITERIA],
                        r.total, int(r.eligible), ";".join(r.exclusion_reasons)])


def read_label_table(path: str | Path) -> dict[str, dict]:
    out = {}
    with open(path, newline="", encoding="utf-8") as f:
        for d in csv.DictReader(f):
            d["eligible"] = d["eligible"] == "1"
            for c in CRITERIA + ["total"]:
                d[c] = int(d[c]) if d[c] not in ("", "None") else None
            out[d["project_id"]] = d
    return out


def load_config(path: str | Path = "config/study_config.json") -> dict:
    return json.loads(Path(path).read_text())
