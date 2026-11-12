# Strict Rubric, Local Calibration · AI4ALL edition

> **AI4ALL edition.** The study code, results and the Rubric Auto-fill Reviewer app, restyled to the AI4ALL Style
> Guide (v1.2): Forest, Plum, Mint and Miami palette, Miriam Libre and Crimson Text, and the official AI4ALL logo
> artwork (taken unmodified from the style guide) in place of the original's personal branding. The original
> research presentation decks are not included.

**Can AI scoring of student AI/ML project presentations reproduce trained instructors' grades, and where must a person stay in the loop?**

This is an independent applied-AI research study by Jonathan Doane, Ph.D. It uses 198 redacted AI4ALL Ignite final-presentation decks and their historical instructor rubric grades: six criteria scored 1–5 each, a 6–30 total, and a 24/30 nomination threshold. Only aggregate results are reported; no student work is in this repository.

The project has three stages:

```
 1. STRICT RUBRIC SCORER  ──►  2. HISTORICAL-GRADING CALIBRATION  ──►  3. EVALUATION / RESULTS
    portable, rubric-literal       small per-criterion leniency layer       locked test set, baseline,
    AI scorer, blind to grades     fitted on 46 development decks           tolerances, learning curve
```

**Headline (locked test set, 84 decks):**
- The literal scorer is systematically stricter than instructors. It trails "always give 5" by +0.20 MAE per criterion [0.07, 0.34].
- The calibration layer cuts error by 0.24 [0.17, 0.31] and removes the total-score bias (−2.95 → +0.04).
- Calibration then only ties the baseline, and it flattens the literal scorer's ability to rank work (Next Steps κ 0.60 → 0.22).
- Supported use: AI pre-fill that a person reviews, not autograding. Full results: [`docs/TEST_RESULTS.md`](docs/TEST_RESULTS.md).

**Phase 2 (verified, in [`research/phase2_prompt_x_calibration/`](research/phase2_prompt_x_calibration/)):** a 2 × 2 of strict vs instructor-like prompt, with and without calibration, using 10 runs per deck and criterion over five criteria.
- **Replicates Phase 1:** the strict arms match it closely, with the same grade on 98% of deck-criterion pairs.
- **Grading is repeatable:** all 10 strict runs agree on 90% of pairs.
- **Calibration hides weak work:** about 14% exact agreement on instructor grades 1–3, against 53% without it.
- **Nothing beats "always 5" on exact agreement.**
- **After calibration, prompt choice washes out:** with both tables fitted on development decks only, the strict and instructor-like arms give the same grade 91% of the time.
- **Phase 2 is closed (2026-11-04):** revised for a development-only refit and the corrected `project-199` label.

See [`research/README.md`](research/README.md) for both phases together.

---

## Stage 1 · Strict rubric scorer
A rubric-literal scorer any organisation could use. It is blind to every grade and cites page evidence for each score.

| What | Where |
|---|---|
| Canonical rubric (verbatim from the program document) | `config/rubric_final_presentation.json` |
| Scorer rules, criterion procedures, output schema | `src/rubric_scoring/prompts.py` |
| Frozen free-plan scorer instructions (v1-free.2) | `prompts/free_plan_subagent.md` |
| Input allowlist and leakage guard | `src/rubric_scoring/inputs.py` |
| API scorer for a funded, pinned replication | `src/rubric_scoring/scorer.py` |
| Agent output validation and transcript access audit | `scripts/ingest_agent_outputs.py`, `scripts/audit_agent_access.py` |

Key rules:
- Score only what is observable.
- Abstain when redaction, missing images or oral-only content make a clause unjudgeable (D-10, D-11).
- Never apply the "missing names = 0" rule, because the decks are redacted.

## Stage 2 · Historical-grading calibration
A small, inspectable layer that maps literal scores to one organisation's grading habits. It's portable because only the table changes from one organisation to the next.

| What | Where |
|---|---|
| Methods: B1 additive shift, B2 monotone table (primary) | `src/rubric_scoring/calibration.py` |
| Pre-registered fit (46 development decks, committed before any test scoring) | `config/calibration_fit_dev.json` |
| Pre-registration text | `docs/PROTOCOL.md` §18 |
| Development-set findings that motivated it | `docs/DEVELOPMENT_RESULTS.md` |

## Stage 3 · Evaluation and results
A locked test set, a trivial baseline, pre-set tolerances and clustered uncertainty.

| What | Where |
|---|---|
| Grouped, stratified 35/65 split and locked registry | `src/rubric_scoring/split.py` |
| Metrics: MAE, weighted kappa, ICC(A,1), threshold agreement, cancellation ratio, cluster bootstrap | `src/rubric_scoring/metrics.py`, `analysis.py` |
| Test analysis (C0 baseline, B0 literal, B1, B2, learning curve) | `scripts/analyse_test.py` |
| Results | `docs/TEST_RESULTS.md` |
| Simulated precision analysis (pre-study) | `docs/SIMULATED_PRECISION.md` |

---

## Phase 2 · Prompt × calibration (2 × 2), 10 repeated runs
Produced outside this repository (a separate Claude account and ChatGPT) and imported with an independent verification. The per-project table is private (`data/private/phase2/`).

| What | Where |
|---|---|
| Overview, design, headline, file map | [`research/phase2_prompt_x_calibration/README.md`](research/phase2_prompt_x_calibration/README.md) |
| Full findings (Revision 1: human-like table refitted on development decks) | [`research/phase2_prompt_x_calibration/FINDINGS.md`](research/phase2_prompt_x_calibration/FINDINGS.md) |
| Instructor-like prompt | [`research/phase2_prompt_x_calibration/prompts/human_like_prompt.py`](research/phase2_prompt_x_calibration/prompts/human_like_prompt.py) |
| Verification and reconciliation with Phase 1 | [`research/phase2_prompt_x_calibration/VERIFICATION.md`](research/phase2_prompt_x_calibration/VERIFICATION.md) |
| Aggregate metrics and verification output | `research/phase2_prompt_x_calibration/metrics/` |

---

## Design and governance
- `docs/PROTOCOL.md`: estimands, claim/evidence matrix, design, metrics, review policy, psychometric-model scope, limitations. §17 covers free-plan execution and §18 the calibration pre-registration.
- `docs/DECISION_LOG.md`: every material decision, with the split hash and the test-unlock record.
- `docs/DATA_ISSUES_AND_AUDIT.md`: the data-issue log (including DI-13, a redaction gap to fix) and audit checklists.
- `docs/DATA_GOVERNANCE.md`: privacy rules. No student work, names, labels or per-project outputs are committed.

## Reproducing

```bash
pip install -e ".[dev]"
```

```bash
python -m pytest -q
```

```bash
python -m rubric_scoring.cli --source label_source_safe_index prepare data/private/safe_index.csv
```

```bash
python -m rubric_scoring.cli --source label_source_safe_index split data/private/safe_index.csv
```

Score decks with fresh agents using `prompts/free_plan_subagent.md` (or `cli score` with an API key). Then run:

```bash
python scripts/audit_agent_access.py <transcripts_dir> --jobs runs/agent_jobs.jsonl
```

```bash
python scripts/ingest_agent_outputs.py && python -m rubric_scoring.cli predictions
```

```bash
python -m rubric_scoring.cli unlock-test --who "<name>" && python scripts/analyse_test.py
```

`data/`, `runs/`, `outputs/` and the split registry are private and git-ignored.
