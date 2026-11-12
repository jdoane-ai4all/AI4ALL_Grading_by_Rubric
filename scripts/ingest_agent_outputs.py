"""Validate free-plan agent outputs and append them to the standard run log.

Each agent writes runs/agent_outputs/<run_key>.json. runs/agent_jobs.jsonl maps
run_key -> (condition, replicate, project_id, file_id, agent_id). Invalid or
missing outputs are logged as failures so they stay in denominators.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "src")
from rubric_scoring.scorer import RunLog, validate  # noqa: E402

PROMPT_VERSION = "2026-11-02.v1-free.2"
COND = {"prompt": "evidence", "input": "text", "organisation": "joint"}


def main():
    jobs = [json.loads(x) for x in Path("runs/agent_jobs.jsonl").read_text().splitlines()]
    log = RunLog("runs/run_log.jsonl")
    seen = set()
    if log.path.exists():
        seen = {json.loads(x).get("run_key") for x in log.path.read_text().splitlines()}
    n_ok = n_bad = 0
    for j in jobs:
        if j["run_key"] in seen:
            continue
        p = Path("runs/agent_outputs") / f"{j['run_key']}.json"
        rec = {"run_id": j["batch"], "run_key": j["run_key"], "condition": j["condition"], "replicate": j["replicate"],
               "project_id": j["project_id"], "call_criterion": "ALL", "agent_id": j.get("agent_id"),
               "model_requested": "claude-code-subagent (session model, not API-pinned)",
               "prompt_version": PROMPT_VERSION, "input_drive_file_id": j["file_id"],
               "timestamp_utc": datetime.now(timezone.utc).isoformat(), "attempt": 0}
        if not p.exists():
            if j.get("finished"):
                rec.update(status="missing_output"); log.append(rec); n_bad += 1
            continue
        txt = p.read_text().strip()
        try:
            items = validate(json.loads(txt), COND, None)
            rec.update(status="valid", output=items); n_ok += 1
        except Exception as e:  # noqa: BLE001
            rec.update(status="invalid_output", error=str(e)[:300], raw_text=txt[:4000]); n_bad += 1
        log.append(rec)
    print(f"ingested valid={n_ok} invalid_or_missing={n_bad}")


if __name__ == "__main__":
    main()
