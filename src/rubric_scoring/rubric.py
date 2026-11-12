"""Canonical rubric access. The rubric text is loaded verbatim from config/; it is never regenerated."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

CRITERIA = [
    "project_description",
    "data_visualization",
    "algorithm",
    "essential_question",
    "next_steps",
    "citations",
]

RUBRIC_PATH = Path(__file__).resolve().parents[2] / "config" / "rubric_final_presentation.json"


@lru_cache(maxsize=1)
def load_rubric(path: str | None = None) -> dict:
    rubric = json.loads(Path(path or RUBRIC_PATH).read_text(encoding="utf-8"))
    keys = [c["key"] for c in rubric["criteria"]]
    assert keys == CRITERIA, f"rubric criteria order mismatch: {keys}"
    return rubric


def criterion(key: str) -> dict:
    return next(c for c in load_rubric()["criteria"] if c["key"] == key)


def render_criterion(key: str) -> str:
    c = criterion(key)
    lines = [f"Criterion: {c['name']}"]
    for s in ["5", "4", "3", "2", "1"]:
        lines.append(f"  {s} ({load_rubric()['scale']['labels'][s]}): {c['levels'][s]}")
    return "\n".join(lines)


def render_full_rubric() -> str:
    return "\n\n".join(render_criterion(k) for k in CRITERIA)
