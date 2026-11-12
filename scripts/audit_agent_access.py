"""Leakage audit for free-plan scorer agents.

Scans agent transcript JSONL files and reports every tool call each agent made.
An agent PASSES only if its calls are limited to: ToolSearch, reading the
instruction file, one Drive read of its assigned file ID, and writing its own
output file. Anything else (other reads, shell, search, other Drive files) FAILS
and that run is excluded and logged.

Usage: python scripts/audit_agent_access.py <transcripts_dir> [--jobs runs/agent_jobs.jsonl]
"""
import json
import sys
from pathlib import Path

ALLOWED_READ = "/home/user/ml_grading_by_rubric/prompts/free_plan_subagent.md"
OUT_DIR = "/home/user/ml_grading_by_rubric/runs/agent_outputs/"


def tool_calls(path: Path):
    for line in path.read_text(errors="ignore").splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = ev.get("message") or {}
        content = msg.get("content") if isinstance(msg, dict) else None
        if isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    yield b.get("name", ""), b.get("input", {}) or {}


def audit(path: Path, file_id: str | None, run_key: str | None):
    problems, calls = [], []
    for name, inp in tool_calls(path):
        calls.append(name)
        if name in ("ToolSearch", "SubagentHandback"):
            continue
        if name == "Read" and inp.get("file_path") == ALLOWED_READ:
            continue
        if name == "Write" and str(inp.get("file_path", "")).startswith(OUT_DIR) \
                and (run_key is None or inp["file_path"].endswith(f"{run_key}.json")):
            continue
        if name.endswith("read_file_content") and (file_id is None or inp.get("fileId") == file_id):
            continue
        problems.append(f"{name}:{json.dumps(inp)[:160]}")
    return {"transcript": path.name, "n_calls": len(calls), "calls": calls, "pass": not problems, "violations": problems}


if __name__ == "__main__":
    d = Path(sys.argv[1])
    jobs = {}
    if "--jobs" in sys.argv:
        for x in Path(sys.argv[sys.argv.index("--jobs") + 1]).read_text().splitlines():
            j = json.loads(x)
            if j.get("agent_id"):
                jobs[j["agent_id"]] = j
    results = []
    for p in sorted(d.glob("*.output")):
        if jobs and p.stem not in jobs:
            continue  # only audit registered scorer agents
        j = jobs.get(p.stem, {})
        r = audit(p, j.get("file_id"), j.get("run_key"))
        r["run_key"] = j.get("run_key")
        results.append(r)
        print(("PASS" if r["pass"] else "FAIL"), p.stem, r["run_key"], r["calls"], r["violations"][:3])
    Path("runs/access_audit.json").write_text(json.dumps(results, indent=2))
