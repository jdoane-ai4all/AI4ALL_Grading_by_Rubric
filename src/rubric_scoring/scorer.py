"""Scoring runner: builds requests, calls the Claude API, validates, logs everything.

Every attempt (valid, invalid, refused, errored) is appended to a JSONL run log.
Labels are never imported here.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .inputs import Artifact, assert_no_leakage, deck_block
from .prompts import PROMPT_VERSION, SCORE_ENUM, SYSTEM_PROMPT, output_schema, prompt_hash, task_text
from .rubric import CRITERIA

# Per-million-token prices for budgeting only. VERIFY against current pricing before committing spend.
PRICES = {"claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_read": 0.20, "cache_write": 5.00}}


def build_params(artifact: Artifact, cond: dict, scfg: dict, criterion_key: str | None) -> tuple[dict, dict]:
    block, input_hash = deck_block(artifact, cond["input"])
    params = {
        "model": scfg["model"],
        "max_tokens": scfg["max_tokens"],
        "system": [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": [
            block,
            {"type": "text", "text": task_text(cond["prompt"], cond["organisation"], criterion_key)},
        ]}],
        "thinking": {"type": "adaptive"},
        "output_config": {
            "effort": scfg["effort"],
            "format": {"type": "json_schema",
                       "schema": output_schema(cond["prompt"], cond["organisation"], criterion_key)},
        },
    }
    assert_no_leakage(params)
    meta = {"input_sha256": input_hash,
            "prompt_sha": prompt_hash(cond["prompt"], cond["organisation"], criterion_key)}
    return params, meta


def validate(obj: dict, cond: dict, criterion_key: str | None) -> list[dict]:
    """Returns a list of per-criterion records, or raises ValueError."""
    items = [obj] if cond["organisation"] == "separate" else obj.get("scores", [])
    expected = [criterion_key] if criterion_key else CRITERIA
    got = [i.get("criterion") for i in items]
    if sorted(got) != sorted(expected):
        raise ValueError(f"criteria mismatch: {got}")
    for i in items:
        if i.get("score") not in SCORE_ENUM:
            raise ValueError(f"bad score {i.get('score')}")
        if i["score"] == "ABSTAIN" and i.get("abstention_reason") == "none":
            raise ValueError("abstained without a reason")
    return items


def usage_dict(u) -> dict:
    keys = ["input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"]
    return {k: getattr(u, k, None) or 0 for k in keys}


def cost_usd(model: str, u: dict) -> float:
    p = PRICES.get(model)
    if not p:
        return float("nan")
    return (u["input_tokens"] * p["input"] + u["output_tokens"] * p["output"]
            + u["cache_read_input_tokens"] * p["cache_read"]
            + u["cache_creation_input_tokens"] * p["cache_write"]) / 1e6


class RunLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, rec: dict) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

    def completed_keys(self) -> set:
        if not self.path.exists():
            return set()
        done = set()
        for line in self.path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r.get("status") == "valid":
                done.add((r["condition"], r["replicate"], r["project_id"], r["call_criterion"]))
        return done


def score_artifact(client, artifact: Artifact, cond_name: str, cond: dict, scfg: dict,
                   replicate: int, log: RunLog, run_id: str, done: set, dry_run: bool = False) -> None:
    calls = CRITERIA if cond["organisation"] == "separate" else [None]
    for ck in calls:
        key = (cond_name, replicate, artifact.project_id, ck or "ALL")
        if key in done:
            continue
        params, meta = build_params(artifact, cond, scfg, ck)
        base = {"run_id": run_id, "condition": cond_name, "replicate": replicate,
                "project_id": artifact.project_id, "call_criterion": ck or "ALL",
                "model_requested": scfg["model"], "effort": scfg["effort"],
                "prompt_version": PROMPT_VERSION, **meta}
        if dry_run:
            log.append({**base, "status": "dry_run", "timestamp_utc": _now()})
            continue
        for attempt in range(scfg["max_retries_invalid_output"] + 1):
            rec = {**base, "attempt": attempt, "timestamp_utc": _now()}
            t0 = time.time()
            try:
                resp = client.messages.create(**params)
            except Exception as e:  # logged, counted as failure; SDK already retries 429/5xx
                rec.update(status="api_error", error=f"{type(e).__name__}: {e}"[:500])
                log.append(rec)
                continue
            rec.update(latency_s=round(time.time() - t0, 2), model_served=resp.model,
                       stop_reason=resp.stop_reason, response_id=resp.id, usage=usage_dict(resp.usage))
            rec["cost_usd"] = cost_usd(scfg["model"], rec["usage"])
            if resp.stop_reason == "refusal":
                rec.update(status="refusal",
                           stop_details=str(getattr(resp, "stop_details", None))[:500])
                log.append(rec)
                break  # not retried: a refusal is a reportable outcome
            text = next((b.text for b in resp.content if b.type == "text"), "")
            try:
                items = validate(json.loads(text), cond, ck)
                rec.update(status="valid", output=items)
                log.append(rec)
                break
            except (ValueError, json.JSONDecodeError) as e:
                rec.update(status="invalid_output", error=str(e)[:300], raw_text=text[:4000])
                log.append(rec)


def run_condition(artifacts: list[Artifact], cond_name: str, config: dict, log_path: str | Path,
                  replicates: int = 1, dry_run: bool = False, client=None) -> str:
    scfg = config["scoring"]
    cond = scfg["conditions"][cond_name]
    log = RunLog(log_path)
    done = log.completed_keys()
    run_id = f"{cond_name}-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"
    if client is None and not dry_run:
        import anthropic
        client = anthropic.Anthropic(max_retries=4)
    for rep in range(1, replicates + 1):
        for a in artifacts:  # order recorded via timestamps; shuffled upstream
            score_artifact(client, a, cond_name, cond, scfg, rep, log, run_id, done, dry_run)
    return run_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def predictions_table(log_path: str | Path) -> list[dict]:
    """Flattens valid outputs to one row per (condition, replicate, project, criterion).

    Calls that never produced a valid output are emitted as status='failed' rows so
    they stay in denominators.
    """
    recs = [json.loads(x) for x in Path(log_path).read_text(encoding="utf-8").splitlines()]
    by_call: dict[tuple, list[dict]] = {}
    for r in recs:
        if r.get("status") == "dry_run":
            continue
        by_call.setdefault((r["condition"], r["replicate"], r["project_id"], r["call_criterion"]), []).append(r)
    rows = []
    for (cond, rep, pid, cc), rs in by_call.items():
        valid = [r for r in rs if r["status"] == "valid"]
        crits = CRITERIA if cc == "ALL" else [cc]
        if not valid:
            for c in crits:
                rows.append({"condition": cond, "replicate": rep, "project_id": pid, "criterion": c,
                             "status": "failed", "score": None, "abstention_reason": None,
                             "attempts": len(rs), "final_status": rs[-1]["status"]})
            continue
        v = valid[-1]
        for item in v["output"]:
            s = item["score"]
            rows.append({"condition": cond, "replicate": rep, "project_id": pid, "criterion": item["criterion"],
                         "status": "abstain" if s == "ABSTAIN" else "scored",
                         "score": None if s == "ABSTAIN" else int(s),
                         "abstention_reason": item.get("abstention_reason"),
                         "limiting_factors": ";".join(item.get("limiting_factors", [])),
                         "n_evidence": len(item.get("evidence", [])),
                         "attempts": len(rs), "final_status": "valid"})
    return rows
