"""Core logic for the human-reviewed auto-fill scorer (UI-independent, testable).

Flow per deck:
  1. score_deck()      strict rubric scorer: one call per criterion, page-cited evidence,
                       abstention when content is unobservable (Stage 1 of the study)
  2. calibrate()       optional local leniency layer, e.g. the AI4ALL Ignite fit (Stage 2)
  3. review_flags()    routing reasons a reviewer should look at first
  4. review_record()   the exported record; requires a human-confirmed score for every criterion

The AI never finalises a grade: review_record() refuses to export without human scores.
"""
from __future__ import annotations

import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from .calibration import apply as apply_cal
from .inputs import Artifact
from .rubric import CRITERIA, criterion
from .scorer import build_params, cost_usd, usage_dict, validate

DEFAULT_MODEL = "claude-opus-5-5"
CALIBRATION_PATH = Path(__file__).resolve().parents[2] / "config" / "calibration_fit_dev.json"
NOMINATION_THRESHOLD = 24


def load_calibration(path: str | Path = CALIBRATION_PATH) -> dict:
    fit = json.loads(Path(path).read_text())
    return {c: {int(k): v for k, v in t.items()} for c, t in fit["B2_table"].items()}


def _artifact_from_upload(data: bytes, filename: str) -> tuple[Artifact, str]:
    suffix = Path(filename).suffix.lower()
    tmp = Path(tempfile.mkdtemp(prefix="deck_")) / f"deck{suffix}"
    tmp.write_bytes(data)
    if suffix == ".pdf":
        return Artifact("upload", tmp, None), "pdf"
    if suffix in (".txt", ".md"):
        return Artifact("upload", None, tmp), "text"
    raise ValueError("Upload a PDF or a .txt export of the slide deck")


REDACTION_NOTE = ("This deck was redacted before it reached you: black boxes and tags such as [name], [email] or "
                  "[face] mark removed personal information. Score the content that remains and never lower a score "
                  "because of redaction. If you notice personal information that was missed (a name, email or face), "
                  "do not repeat it in your reply; write 'a team member' instead.")


def _text_of(params: dict) -> str:
    """All text that will be sent, excluding base64 document data."""
    out = [b["text"] for b in params.get("system", []) if b.get("type") == "text"]
    for m in params["messages"]:
        out += [b["text"] for b in m["content"] if b.get("type") == "text"]
    return "\n".join(out)


def _one_call(client, artifact, modality, model, effort, ck, extra_text=None, guard=None):
    cond = {"prompt": "evidence", "input": modality, "organisation": "separate"}
    scfg = {"model": model, "effort": effort, "max_tokens": 16000}
    params, meta = build_params(artifact, cond, scfg, ck)
    if extra_text is not None:
        content = params["messages"][0]["content"]
        content.insert(1, {"type": "text", "text": REDACTION_NOTE + "\n\n<slide_deck_text_redacted>\n" + extra_text
                           + "\n</slide_deck_text_redacted>", "cache_control": {"type": "ephemeral"}})
        content[0].pop("cache_control", None)
    if guard is not None and guard(_text_of(params)):
        raise RuntimeError("Redaction check failed: removed personal information was still in the request, "
                           "so nothing was sent.")
    last_err = None
    for _ in range(3):
        resp = client.messages.create(**params)
        u = usage_dict(resp.usage)
        if resp.stop_reason == "refusal":
            return ck, None, u, "The model declined to score this criterion"
        text = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            return ck, validate(json.loads(text), cond, ck)[0], u, None
        except (ValueError, json.JSONDecodeError) as e:
            last_err = str(e)
    return ck, None, u, f"Invalid model output after retries: {last_err}"


def score_deck(client, data: bytes, filename: str, model: str = DEFAULT_MODEL, effort: str = "medium",
               progress=None, extra_text: str | None = None, guard=None) -> dict:
    """Strict-rubric scoring. The first call warms the deck cache; the other five run in parallel.

    For an unredacted upload, pass the redacted image-only PDF as data, its redacted text as extra_text,
    and guard=lambda text: leaks(text, redaction) so a request with a removed term in it is never sent.
    """
    artifact, modality = _artifact_from_upload(data, filename)
    results, usage, errors = {}, [], {}
    first = CRITERIA[0]
    ck, item, u, err = _one_call(client, artifact, modality, model, effort, first, extra_text, guard)
    results[ck], usage = item, [u]
    if err:
        errors[ck] = err
    if progress:
        progress(1, len(CRITERIA))
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = [ex.submit(_one_call, client, artifact, modality, model, effort, c, extra_text, guard)
                for c in CRITERIA[1:]]
        for i, f in enumerate(futs, start=2):
            ck, item, u, err = f.result()
            results[ck] = item
            usage.append(u)
            if err:
                errors[ck] = err
            if progress:
                progress(i, len(CRITERIA))
    total = {k: sum(x[k] for x in usage) for k in usage[0]}
    return {"modality": modality, "model": model, "effort": effort, "items": results, "errors": errors,
            "usage": total, "cost_usd_estimate": cost_usd(model, total),
            "scored_utc": datetime.now(timezone.utc).isoformat()}


def ai_score(item: dict | None) -> int | None:
    if not item or item.get("score") == "ABSTAIN":
        return None
    return int(item["score"])


def calibrate(result: dict, table: dict | None) -> dict[str, int | None]:
    out = {}
    for c in CRITERIA:
        s = ai_score(result["items"].get(c))
        out[c] = apply_cal("B2_table", table, c, s) if (table and s is not None) else s
    return out


def review_flags(result: dict, suggested: dict[str, int | None]) -> dict[str, list[str]]:
    """Reasons to look closely, per criterion plus 'deck' for deck-level flags."""
    flags = {c: [] for c in CRITERIA}
    flags["deck"] = []
    for c in CRITERIA:
        item = result["items"].get(c)
        if c in result["errors"]:
            flags[c].append("AI failed: score manually")
        elif item and item["score"] == "ABSTAIN":
            flags[c].append(f"AI abstained ({item['abstention_reason'].replace('_', ' ')})")
        if suggested.get(c) is not None and suggested[c] <= 3:
            flags[c].append("Low score: confirm against the deck")
        for f in (item or {}).get("limiting_factors", []):
            flags[c].append(f.replace("_", " "))
    if all(v is not None for v in suggested.values()):
        tot = sum(suggested.values())
        if abs(tot - NOMINATION_THRESHOLD) <= 2:
            flags["deck"].append(f"Suggested total {tot} is within 2 of the {NOMINATION_THRESHOLD}/30 nomination cut")
    if result.get("modality") == "text":
        flags["deck"].append("Text-only input: the AI cannot see charts or images")
    return flags


def review_record(deck_label: str, reviewer: str, result: dict, suggested: dict, final: dict,
                  reasons: dict, notes: str = "", calibration_name: str = "none") -> dict:
    missing = [c for c in CRITERIA if final.get(c) is None]
    if missing:
        raise ValueError(f"Human-confirmed scores are required for: {', '.join(missing)}")
    if not reviewer.strip():
        raise ValueError("Reviewer initials are required")
    rows = []
    for c in CRITERIA:
        item = result["items"].get(c) or {}
        rows.append({
            "criterion": criterion(c)["name"],
            "ai_literal": ai_score(item),
            "ai_suggested": suggested.get(c),
            "human_final": int(final[c]),
            "overridden": suggested.get(c) != int(final[c]),
            "override_reason": reasons.get(c, ""),
            "ai_rationale": item.get("rationale", ""),
            "evidence_pages": sorted({e["page"] for e in item.get("evidence", [])}),
        })
    return {
        "deck": deck_label, "reviewer": reviewer.strip(), "reviewed_utc": datetime.now(timezone.utc).isoformat(),
        "human_total": sum(r["human_final"] for r in rows), "calibration": calibration_name,
        "model": result["model"], "input": result["modality"], "criteria": rows, "notes": notes,
        "disclaimer": "Scores were confirmed by the named reviewer. AI output is advisory only.",
    }


def demo_result() -> dict:
    """Synthetic output for trying the interface without an API key. Not a real deck."""
    def it(c, s, why, pages, lf=()):
        return {"criterion": c, "score": s, "abstention_reason": "none" if s != "ABSTAIN" else "extraction_or_render_failure",
                "rationale": why, "evidence": [{"page": p, "observation": "(demo evidence)"} for p in pages],
                "checklist": [], "counted_items": 0, "limiting_factors": list(lf), "extraction_issues": []}
    items = {
        "project_description": it("project_description", "4", "Describes goal and evolution; no challenge-plus-solution pair found.", [2, 3]),
        "data_visualization": it("data_visualization", "5", "Four distinct data charts with titles and axes.", [5, 6, 8]),
        "algorithm": it("algorithm", "3", "Names a random forest, supervised, inputs and outputs; no pros and cons.", [7], ["borderline_rubric_level"]),
        "essential_question": it("essential_question", "4", "Weighs benefits and risks with research; beyond-program clause not observable.", [11, 12], ["requires_program_context"]),
        "next_steps": it("next_steps", "3", "Steps listed but no measures or deadlines.", [14]),
        "citations": it("citations", "ABSTAIN", "Reference slide appears truncated.", [15], ["possible_redaction"]),
    }
    return {"modality": "pdf", "model": "DEMO (synthetic)", "effort": "-", "items": items, "errors": {},
            "usage": {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
            "cost_usd_estimate": 0.0, "scored_utc": datetime.now(timezone.utc).isoformat()}


# ── v2: grading workspace helpers ─────────────────────────────────────────
import hashlib as _hashlib
import re as _re
import unicodedata as _ud

APP_DATA = Path(__file__).resolve().parents[2] / "app" / "data"
HISTORICAL_MODE = {c: 5 for c in CRITERIA}  # most common instructor score for every criterion (dataset audit)


def norm_title(s: str) -> str:
    s = _ud.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = _re.sub(r"\.pdf$", "", s.strip())
    s = _re.sub(r"\s*\(\d+\)$", "", s)          # "Deck (1).pdf" from repeated downloads
    return _re.sub(r"[^a-z0-9]+", " ", s).strip()


def load_bundle() -> tuple[dict, dict]:
    """(precomputed results by project_id, lookup index by normalised title / drive id / size)."""
    pre_p, idx_p = APP_DATA / "precomputed.json", APP_DATA / "deck_index.json"
    pre = json.loads(pre_p.read_text()) if pre_p.exists() else {}
    index = {"title": {}, "drive_id": {}, "size": {}}
    if idx_p.exists():
        for row in json.loads(idx_p.read_text()):
            if row.get("title"):
                index["title"].setdefault(norm_title(row["title"]), []).append(row["project_id"])
            if row.get("pdf_file_id"):
                index["drive_id"][row["pdf_file_id"]] = row["project_id"]
            if row.get("pdf_size_bytes"):
                index["size"].setdefault(int(row["pdf_size_bytes"]), []).append(row["project_id"])
    return pre, index


def match_deck(filename: str, size: int, index: dict, drive_id: str | None = None) -> tuple[str | None, str]:
    """Return (project_id, how). Drive ID beats size+title, which beats a unique title."""
    if drive_id and drive_id in index["drive_id"]:
        return index["drive_id"][drive_id], "Drive file"
    by_title = index["title"].get(norm_title(Path(filename).name), [])
    by_size = index["size"].get(size, [])
    both = [p for p in by_title if p in by_size]
    if len(both) == 1:
        return both[0], "filename + size"
    if len(by_title) == 1:
        return by_title[0], "filename"
    if len(by_size) == 1 and not by_title:
        return by_size[0], "file size"
    return None, "no match"


def result_from_items(items: list[dict], source: str, model: str = "-", modality: str = "pdf") -> dict:
    return {"modality": modality, "model": model, "effort": "-", "items": {i["criterion"]: i for i in items},
            "errors": {}, "usage": {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
                                    "cache_creation_input_tokens": 0},
            "cost_usd_estimate": 0.0, "scored_utc": datetime.now(timezone.utc).isoformat(), "source": source}


def precomputed_result(pid: str, pre: dict) -> dict | None:
    rec = pre.get(pid)
    if not rec:
        return None
    r = result_from_items(list(rec["items"].values()), source="precomputed",
                          model=f"study scorer ({rec.get('prompt_version', '')})", modality=rec.get("input", "text"))
    return r


def _extract_json(text: str):
    text = text.strip()
    fence = _re.search(r"```(?:json)?\s*(.*?)```", text, _re.S)
    if fence:
        text = fence.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("No JSON found in the pasted text")
    return json.loads(text[start:text.rfind("}" if text[start] == "{" else "]") + 1])


def parse_pasted(text: str) -> dict[str, list[dict]]:
    """Parse Claude's reply. Returns {filename_or_'*': [criterion items]} after schema validation.

    Accepts {"scores":[...]} (one deck), {"decks":[{"file":..,"scores":[..]}]} or a list of those.
    """
    obj = _extract_json(text)
    decks = obj.get("decks") if isinstance(obj, dict) and "decks" in obj else (obj if isinstance(obj, list) else [obj])
    out = {}
    cond = {"organisation": "joint"}
    for d in decks:
        items = validate({"scores": d["scores"]}, cond, None)
        out[d.get("file") or "*"] = items
    return out


def claude_prompt(batch: bool = False) -> str:
    """Copy-paste prompt for Claude chat (attach the PDF[s]); the reply is pasted back into the app."""
    from .prompts import SYSTEM_PROMPT, task_text, output_schema
    schema = output_schema("evidence", "joint")
    if batch:
        head = ("I have attached several student slide-deck PDFs. Score EACH attached file separately and "
                "independently against the rubric below, as if you had never seen the other files.")
        out = ('Reply with ONE JSON object and nothing else: {"decks": [{"file": "<exact attached filename>", '
               '"scores": [ ...six criterion objects... ]}, ...]} with one entry per attached file. '
               "Each criterion object must follow this JSON Schema item definition:\n"
               + json.dumps(schema["properties"]["scores"]["items"], separators=(",", ":")))
    else:
        head = "I have attached one student slide-deck PDF. Score it against the rubric below."
        out = ("Reply with ONE JSON object and nothing else, valid against this JSON Schema:\n"
               + json.dumps(schema, separators=(",", ":")))
    return "\n\n".join([head, REDACTION_NOTE, SYSTEM_PROMPT, task_text("evidence", "joint", None),
                        "Look at every slide image as well as the text, so charts are visible to you.", out])


def file_key(data: bytes) -> str:
    return _hashlib.sha256(data).hexdigest()[:16]


# ---- fuzzy matching of an upload to a stored study deck, by content ----
_STOP = set("""the and for with that this from are was were has have had not but all any can its our their they them
these those into onto than then there here when where which who whom what how why will would could should may might
also each such more most other some only very just over under about after before between both during while being been
does did doing using used use uses page pages slide slides deck shows show shown states stated stating includes include
included including provides provided describes described mentions mentioned lists listed level levels rubric criterion
score scored evidence clear clearly explicit explicitly present presents presented none no yes one two three four five
six seven""".split())


def _stem(w: str) -> str:
    for suf in ("ations", "ation", "ings", "ing", "ies", "ed", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[:-len(suf)]
    return w


def _tokens(text: str) -> set[str]:
    return {_stem(w) for w in _re.findall(r"[a-z][a-z0-9\-]{2,}|\d{3,}", (text or "").lower()) if w not in _STOP}


def content_profiles(pre: dict, max_df: float = 0.08) -> dict[str, set[str]]:
    """Distinctive words per study deck, from the stored AI evidence notes and rationales."""
    raw = {}
    for pid, rec in pre.items():
        parts = []
        for it in rec["items"].values():
            parts.append(it.get("rationale", ""))
            parts += [e.get("observation", "") for e in it.get("evidence", [])]
        raw[pid] = _tokens(" ".join(parts))
    df: dict[str, int] = {}
    for toks in raw.values():
        for t in toks:
            df[t] = df.get(t, 0) + 1
    cap = max(2, int(max_df * len(raw)))
    return {pid: {t for t in toks if df[t] <= cap} for pid, toks in raw.items()}


def content_match(text: str, profiles: dict[str, set[str]], min_terms: int = 6) -> list[tuple[str, float]]:
    """[(project_id, coverage)] best first: the share of a deck's distinctive words found in the upload."""
    up = _tokens(text)
    out = [(pid, len(p & up) / len(p)) for pid, p in profiles.items() if len(p) >= min_terms]
    return sorted(out, key=lambda x: -x[1])


def best_content_match(text: str, profiles: dict[str, set[str]], min_share: float = 0.5,
                       min_ratio: float = 2.0) -> tuple[str | None, float]:
    """The study deck this upload most likely is, or (None, best share) when not confident.

    Validated on 6 real deck texts: the true deck ranked first every time with 63-88% of its distinctive
    words present; the best wrong deck reached at most 29%.
    """
    ranked = content_match(text, profiles)
    if not ranked:
        return None, 0.0
    top, second = ranked[0], (ranked[1][1] if len(ranked) > 1 else 0.0)
    if top[1] >= min_share and top[1] >= min_ratio * max(second, 1e-9):
        return top[0], top[1]
    return None, top[1]


def pdf_text(data: bytes) -> str:
    from .pdfsafe import page_texts
    return "\n".join(page_texts(data))
