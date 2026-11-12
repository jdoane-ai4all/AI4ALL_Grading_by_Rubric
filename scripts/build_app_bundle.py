"""Build app/data/precomputed.json (AI study-scorer outputs, NO historical grades) and
app/data/deck_index.json (project_id -> title / Drive PDF id / size) for the hosted app.

Precomputed results are only ever shown when a user uploads the matching deck.
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
from rubric_scoring.scorer import validate  # noqa: E402

OUT = Path("app/data")
OUT.mkdir(parents=True, exist_ok=True)
best = {}
for line in Path("runs/run_log.jsonl").read_text().splitlines():
    r = json.loads(line)
    if r.get("status") != "valid" or r.get("call_criterion") != "ALL":
        continue
    v = r.get("prompt_version", "")
    rank = 2 if v.endswith("free.2") else 1
    prev = best.get(r["project_id"])
    if prev is None or rank >= prev[0]:
        best[r["project_id"]] = (rank, r)
pre = {}
for pid, (_, r) in sorted(best.items()):
    items = validate({"scores": r["output"]}, {"organisation": "joint"}, None)
    pre[pid] = {"items": {i["criterion"]: i for i in items}, "prompt_version": r.get("prompt_version"), "input": "text"}
(OUT / "precomputed.json").write_text(json.dumps(pre, separators=(",", ":")))
print("precomputed decks:", len(pre))

idx_src = Path("data/private/app_index.csv")
if idx_src.exists():
    rows = []
    for d in csv.DictReader(open(idx_src, newline="", encoding="utf-8")):
        pid = (d.get("project_id") or d.get("Project ID") or "").strip()
        title = (d.get("title") or d.get("Presentation Title") or d.get("Title") or "").strip()
        link = d.get("pdf_link") or d.get("PDF Link") or ""
        import re
        m = re.search(r"/d/([A-Za-z0-9_-]{20,})", link)
        rows.append({"project_id": pid, "title": title, "pdf_file_id": m.group(1) if m else "",
                     "pdf_size_bytes": d.get("pdf_size_bytes") or ""})
    (OUT / "deck_index.json").write_text(json.dumps(rows, separators=(",", ":")))
    print("index rows:", len(rows), "with titles:", sum(bool(r["title"]) for r in rows))
else:
    print("no data/private/app_index.csv yet: deck matching disabled until it is added")
