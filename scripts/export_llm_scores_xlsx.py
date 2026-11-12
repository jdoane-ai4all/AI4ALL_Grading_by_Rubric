"""Export every logged LLM scoring run to an Excel workbook (private: written to outputs/, which is git-ignored).

Sheets: About · Scores by run (one row per attempt) · Scores by deck (one row per project) ·
Rationale & evidence (one row per run x criterion) · Calibration table (drives the calibrated columns).
No historical instructor grades are included.

    python3 scripts/export_llm_scores_xlsx.py [outputs/LLM_scores.xlsx]
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

sys.path.insert(0, "src")
from rubric_scoring.rubric import CRITERIA, criterion  # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "outputs/LLM_scores.xlsx")
OUT.parent.mkdir(parents=True, exist_ok=True)
runs = [json.loads(line) for line in Path("runs/run_log.jsonl").read_text().splitlines()]
runs.sort(key=lambda r: (r["project_id"], r["timestamp_utc"]))
split = json.loads(Path("registry/split_registry.json").read_text())["project_split"]
cal = json.loads(Path("config/calibration_fit_dev.json").read_text())["B2_table"]
NAMES = [criterion(c)["name"] for c in CRITERIA]

# the app uses the last valid run per deck (same rule as scripts/build_app_bundle.py)
used = {}
for r in runs:
    if r["status"] == "valid" and r["call_criterion"] == "ALL":
        used[r["project_id"]] = r["run_key"]
by_deck = defaultdict(list)
for r in runs:
    by_deck[r["project_id"]].append(r)

F = "Arial"
HEAD = PatternFill("solid", fgColor="112A3E")
HFONT = Font(name=F, bold=True, color="FFFFFF")
BODY = Font(name=F, size=10)
ABST = PatternFill("solid", fgColor="FFF1E6")
thin = Side(style="thin", color="D9E4EA")


def header(ws, cols, widths):
    ws.append(cols)
    for i, w in enumerate(widths, 1):
        c = ws.cell(row=1, column=i)
        c.font, c.fill = HFONT, HEAD
        c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = "B2"


def score_val(s):
    return int(s) if s in {"1", "2", "3", "4", "5"} else "ABSTAIN"


def finish(ws, name, n_rows, n_cols):
    for row in ws.iter_rows(min_row=2, max_row=n_rows + 1, max_col=n_cols):
        for c in row:
            c.font = BODY
            c.border = Border(bottom=thin)
            if c.value == "ABSTAIN":
                c.fill = ABST
    ref = f"A1:{get_column_letter(n_cols)}{n_rows + 1}"
    t = Table(displayName=name, ref=ref)
    t.tableStyleInfo = TableStyleInfo(name="TableStyleLight1", showRowStripes=True)
    ws.add_table(t)


wb = Workbook()

# ── About ────────────────────────────────────────────────────────────────
ab = wb.active
ab.title = "About"
ab.column_dimensions["A"].width = 30
ab.column_dimensions["B"].width = 110
lines = [
    ("LLM rubric scores: AI4ALL Ignite final presentations", None),
    ("What this is", "Every logged AI scoring run of the strict rubric scorer (prompt v1-free.2), one per deck plus "
                     "repeat attempts. Scores are the AI's strict-rubric scores (1-5, or ABSTAIN when content could "
                     "not be judged). Calibrated columns apply the AI4ALL B2 calibration table (sheet 'Calibration table')."),
    ("Not included", "Historical instructor grades. Join on project_id with the private labels file if needed."),
    ("Decks", f"{len(by_deck)} decks, {len(runs)} runs. "
              f"{sum(1 for v in by_deck.values() if len(v) > 1)} decks were scored more than once (an early "
              "format check, then the main run); see 'Runs for this deck' and 'Runs agree?'."),
    ("Input", "Text extracted from the redacted PDFs (no slide images), so Data Visualization often abstains."),
    ("Scorer", "Claude Code subagents on the free plan (session model, not API-pinned); one fresh agent per deck."),
    ("Set", "dev = 46 development decks used to fit calibration; test = 84 locked test decks; "
            "unlabeled_pool = decks without a usable historical grade."),
    ("Raw logs (private, git-ignored)", "runs/run_log.jsonl: one JSON line per run, with all six criteria, rationale "
                                       "and evidence"),
    ("", "runs/agent_outputs/rk-*.json: each agent's raw reply, named by run key"),
    ("", "runs/predictions.csv: long format (deck x criterion) used by the analysis scripts"),
    ("", "app/data/precomputed.json: the copy the reviewer app shows (last run per deck)"),
    ("Rebuild", "python3 scripts/export_llm_scores_xlsx.py"),
    ("Handling", "Internal research data keyed by pseudonymous project IDs. Review before sharing outside the team."),
]
for i, (a, b) in enumerate(lines, 1):
    ab.cell(row=i, column=1, value=a).font = Font(name=F, bold=True, size=14 if i == 1 else 10, color="112A3E")
    if b:
        c = ab.cell(row=i, column=2, value=b)
        c.font = BODY
        c.alignment = Alignment(wrap_text=True, vertical="top")

# ── Calibration table ────────────────────────────────────────────────────
ct = wb.create_sheet("Calibration table")
header(ct, ["Strict score"] + NAMES, [13] + [18] * 6)
for s in range(1, 6):
    ct.append([s] + [cal[c][str(s)] for c in CRITERIA])
for row in ct.iter_rows(min_row=2, max_row=6, min_col=2, max_col=7):
    for c in row:
        c.font = Font(name=F, size=10, color="0000FF")
ct["A8"] = "Source: config/calibration_fit_dev.json (B2 monotone table fitted on the 46 development decks). Blue = input."
ct["A8"].font = Font(name=F, size=9, italic=True)

# ── Scores by run ────────────────────────────────────────────────────────
sr = wb.create_sheet("Scores by run")
cols = ["project_id", "Set", "Attempt", "Runs for this deck", "Used in app", "Run key", "Run batch", "Scored (UTC)"]
crit_start = len(cols) + 1
cols += NAMES + ["Strict total (scored criteria)", "Abstentions"] + [f"{n} (calibrated)" for n in NAMES] + \
        ["Calibrated total"]
header(sr, cols, [13, 14, 8, 9, 8, 10, 22, 17] + [12] * 6 + [12, 11] + [12] * 6 + [11])
r_i = 1
for pid in sorted(by_deck):
    for k, r in enumerate(by_deck[pid], 1):
        r_i += 1
        items = {i["criterion"]: i for i in r["output"]}
        row = [pid, split.get(pid, "?"), k, len(by_deck[pid]), "yes" if used.get(pid) == r["run_key"] else "no",
               r["run_key"], r["run_id"], r["timestamp_utc"][:16].replace("T", " ")]
        row += [score_val(items[c]["score"]) for c in CRITERIA]
        a, b = get_column_letter(crit_start), get_column_letter(crit_start + 5)
        row += [f"=SUM({a}{r_i}:{b}{r_i})", f'=COUNTIF({a}{r_i}:{b}{r_i},"ABSTAIN")']
        for j in range(6):
            sc = get_column_letter(crit_start + j)
            tc = get_column_letter(2 + j)
            row.append(f"=IF(ISNUMBER({sc}{r_i}),INDEX('Calibration table'!${tc}$2:${tc}$6,{sc}{r_i}),\"ABSTAIN\")")
        c0, c1 = get_column_letter(crit_start + 8), get_column_letter(crit_start + 13)
        row.append(f"=SUM({c0}{r_i}:{c1}{r_i})")
        sr.append(row)
finish(sr, "ScoresByRun", r_i - 1, len(cols))
sr.cell(row=1, column=crit_start + 6).comment = Comment("Sum of the criteria the AI scored; ABSTAIN counts as 0, so "
                                                        "compare totals only when Abstentions = 0.", "export")

# ── Scores by deck ───────────────────────────────────────────────────────
sd = wb.create_sheet("Scores by deck")
dcols = ["project_id", "Set", "Runs logged", "Runs agree?"] + [f"{n} (all runs)" for n in NAMES] + \
        [f"{n} (app)" for n in NAMES] + ["Strict total (app)", "Abstentions (app)"]
header(sd, dcols, [13, 14, 9, 10] + [13] * 6 + [12] * 6 + [12, 11])
d_i = 1
for pid in sorted(by_deck):
    d_i += 1
    rs = by_deck[pid]
    per = {c: [score_val({i["criterion"]: i for i in r["output"]}[c]["score"]) for r in rs] for c in CRITERIA}
    app_run = next(r for r in rs if r["run_key"] == used[pid])
    app = {i["criterion"]: score_val(i["score"]) for i in app_run["output"]}
    agree = "single run" if len(rs) == 1 else ("yes" if all(len(set(map(str, v))) == 1 for v in per.values()) else "no")
    row = [pid, split.get(pid, "?"), len(rs), agree] + [", ".join(map(str, per[c])) for c in CRITERIA] + \
          [app[c] for c in CRITERIA]
    a, b = get_column_letter(11), get_column_letter(16)
    row += [f"=SUM({a}{d_i}:{b}{d_i})", f'=COUNTIF({a}{d_i}:{b}{d_i},"ABSTAIN")']
    sd.append(row)
finish(sd, "ScoresByDeck", d_i - 1, len(dcols))

# ── Rationale & evidence ─────────────────────────────────────────────────
re_ = wb.create_sheet("Rationale & evidence")
ecols = ["project_id", "Run key", "Criterion", "Score", "Abstention reason", "Limiting factors", "Rationale",
         "Slides cited", "Evidence"]
header(re_, ecols, [13, 10, 20, 9, 22, 26, 70, 12, 90])
e_i = 1
for pid in sorted(by_deck):
    for r in by_deck[pid]:
        for it in r["output"]:
            e_i += 1
            ev = it.get("evidence", [])
            re_.append([pid, r["run_key"], criterion(it["criterion"])["name"], score_val(it["score"]),
                        it.get("abstention_reason", ""), ", ".join(it.get("limiting_factors", [])),
                        it.get("rationale", ""), ", ".join(str(e["page"]) for e in ev),
                        " | ".join(f"p{e['page']}: {e['observation']}" for e in ev)])
finish(re_, "Rationale", e_i - 1, len(ecols))
for row in re_.iter_rows(min_row=2, max_row=e_i, min_col=7, max_col=9):
    for c in row:
        c.alignment = Alignment(wrap_text=True, vertical="top")

wb.move_sheet("Calibration table", offset=3)
wb.save(OUT)
print(OUT, "runs:", len(runs), "decks:", len(by_deck))
