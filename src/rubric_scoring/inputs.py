"""Scorer input construction under a strict allowlist.

The ONLY things that may enter a scoring request are:
  * the frozen system prompt (rubric + rules),
  * the redacted deck content (PDF bytes, or extracted text with page markers),
  * the criterion task text.
No project ID, title metadata, filename, cohort, tutorial, label, audit field or
student record is ever placed in the request. Joining uses the request's
custom_id, which lives outside the model context.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Artifact:
    project_id: str
    pdf_path: Path | None
    text_path: Path | None
    extraction_json: Path | None = None


def read_manifest(path: str | Path) -> list[Artifact]:
    """Manifest columns: project_id,pdf_path,text_path[,extraction_json]. Nothing else is read."""
    out = []
    base = Path(path).parent
    with open(path, newline="", encoding="utf-8") as f:
        for d in csv.DictReader(f):
            p = lambda k: (base / d[k]) if d.get(k) else None  # noqa: E731
            out.append(Artifact(d["project_id"], p("pdf_path"), p("text_path"), p("extraction_json")))
    return out


def deck_text(a: Artifact) -> str:
    """Page-marked text. Prefers per-page text from extraction.json when present."""
    if a.extraction_json and a.extraction_json.exists():
        ex = json.loads(a.extraction_json.read_text(encoding="utf-8"))
        pages = ex.get("pages") if isinstance(ex, dict) else None
        if pages and all(isinstance(pg, dict) and "text" in pg for pg in pages):
            return "\n\n".join(f"[Page {pg.get('page', i + 1)}]\n{pg['text']}" for i, pg in enumerate(pages))
    if a.text_path is None or not a.text_path.exists():
        raise FileNotFoundError(f"no text for {a.project_id}")
    return a.text_path.read_text(encoding="utf-8")


def deck_block(a: Artifact, modality: str) -> tuple[dict, str]:
    """Returns (content block, sha256 of the exact bytes sent)."""
    if modality == "pdf":
        raw = a.pdf_path.read_bytes()
        block = {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf",
                       "data": base64.standard_b64encode(raw).decode("ascii")},
            "title": "Student final presentation (redacted)",
        }
    elif modality == "text":
        txt = deck_text(a)
        raw = txt.encode("utf-8")
        block = {"type": "text", "text": "<slide_deck_text>\n" + txt + "\n</slide_deck_text>"}
    else:
        raise ValueError(modality)
    block["cache_control"] = {"type": "ephemeral"}
    return block, hashlib.sha256(raw).hexdigest()


FORBIDDEN_KEYS = {"project_id", "cohort", "tutorial", "label", "score_hist", "group_id", "source_row", "instructor"}


def assert_no_leakage(params: dict, forbidden_values: list[str] = ()) -> None:
    """Defensive check run on every request before it is sent."""
    def walk(o):
        if isinstance(o, dict):
            bad = FORBIDDEN_KEYS & set(o)
            if bad:
                raise AssertionError(f"forbidden key(s) in request: {bad}")
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(params)
    blob = json.dumps(params)
    for v in forbidden_values:
        if v and v in blob:
            raise AssertionError("forbidden value found in request (value withheld from log)")
