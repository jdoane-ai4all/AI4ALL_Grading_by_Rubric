# Phase 2 · Prompt × Calibration (2 × 2) with 10 Repeated Runs

**Question:** Does an instructor-like prompt grade closer to historical instructors than the strict rubric prompt, and does post-hoc calibration still help? How repeatable is the grading across 10 runs, and what does calibration cost in telling weak work apart?

**Status:** **Closed (2026-11-04).** Independently verified, then revised twice:
- **Revision 1:** the human-like calibration table is refitted on development decks only.
- **Revision 2:** the PI-corrected `project-199` label is restored, giving 420 test labels.

See [`FINDINGS.md`](FINDINGS.md) §15 and [`VERIFICATION.md`](VERIFICATION.md) before citing any number.

**Provenance:** The grading runs and the analysis were produced outside this repository, in a separate Claude account and ChatGPT, and imported here. The repository holds the aggregate findings, the aggregate metrics and a verification script. The per-project table stays private.

---

## Design in one table

| | No calibration | Criterion-specific calibration |
|---|---|---|
| **Strict rubric prompt** | **A** · Strict rubric | **B** · Strict rubric + calibration |
| **Instructor-like prompt** | **C** · Human-like | **D** · Human-like + calibration |

- **Decks:** all 198, the same split as Phase 1: 46 development, 84 locked test, 68 unlabelled.
- **Criteria:** 5, scored 1–5 each, for a 5–25 total. Data Visualization was excluded because text-only input cannot judge it.
- **Runs:** 10 per deck and criterion, so 9,900 outputs per prompt and 19,800 LLM outputs in all. Calibration is a lookup applied afterwards and needed no extra LLM calls.
- **Reported grade:** the mode of the 10 runs; a project total is the sum of its five criterion modes.

## Headline (locked test: 420 criterion labels, 84 decks)

<!-- auto:headline -->
| Arm | Exact | MAE | Within ±1 | Bias (AI − human) | QWK | Exact when instructor gave 1–3 (n = 58) |
|---|---|---|---|---|---|---|
| A · Strict | 41.7% | 0.874 | 77.1% | −0.612 | 0.291 | 53.4% |
| B · Strict + cal | 52.6% | 0.595 | 89.8% | −0.014 | 0.270 | 13.8% |
| C · Human-like | 47.6% | 0.683 | 86.4% | −0.207 | 0.289 | 22.4% |
| D · Human-like + cal | 51.4% | 0.607 | 89.8% | −0.017 | 0.266 | 15.5% |
| Always 5 (baseline) | 57.4% | 0.626 | 86.2% | +0.626 | 0 | 0% |
<!-- /auto:headline -->

**Takeaways:**
1. **Repeatability is high.** All 10 strict runs agreed on 90% of deck-criterion pairs. But a stable grade is not necessarily an accurate one.
2. **Calibration closes the gap to instructors, but hides weak work.** The calibrated arms recognise only 8 (B) and 9 (D) of the 58 low instructor grades, against 31 for the uncalibrated strict prompt.
3. **After calibration the prompt choice washes out.** B and D give the same grade on 91% of test comparisons (their raw prompts agree on only 62%). They don't differ significantly: D vs B is −1.2 pp exact [−3.8, +1.2].
4. **No arm beats "always 5" on exact agreement.** The calibrated arms beat it on MAE, within ±1 and project totals (total MAE 2.17 and 2.06 vs 3.13).
5. **Arms A and B replicate Phase 1.** The strict 10-run mode equals Phase 1's single-run grade for 98.1% of deck-criterion pairs, and the strict calibration table is Phase 1's table.
6. **Choose the prompt on defensibility.** The instructor-like prompt ([`prompts/human_like_prompt.py`](prompts/human_like_prompt.py)) returns a bare integer with no evidence. The strict scorer cites slides and can abstain.

**Revisions:** the human-like table as delivered could not be reproduced from development data. It reported D at 57.0% exact and 0.554 MAE, ranking D first. Refitted on development only and with the corrected `project-199` label, D is 51.4% and 0.607, the same as B (52.6%, 0.595). See [`FINDINGS.md`](FINDINGS.md) §15.

## Close-out
Phase 2 answered its questions:
- Repeatability is high.
- Calibration transfers, but hides weak work.
- Prompt choice washes out after calibration.
- No arm beats "always 5" on exact agreement.

**Open, not blocking:**
- The Phase 2 strict prompt text was not supplied. Its grades match Phase 1's scorer on 98% of pairs.
- The private case studies quote arm-D grades from the as-delivered table.

**Next phase:** an instructor-adjudicated evidence audit on a new holdout that oversamples instructor grades 1–3. It should use the evidence-citing strict scorer, which can abstain, and show raw and calibrated grades side by side ([`FINDINGS.md`](FINDINGS.md) §13).

## Files

| File | What it is |
|---|---|
| [`FINDINGS.md`](FINDINGS.md) | The full Phase 2 findings: design, calibration tables, test results, subgroups, totals, repeatability, defensibility, conclusions |
| [`VERIFICATION.md`](VERIFICATION.md) | Independent recomputation of every headline number, reconciliation with Phase 1, and caveats |
| [`prompts/human_like_prompt.py`](prompts/human_like_prompt.py) | The instructor-like grading prompt (arms C and D), verbatim |
| `calibration/human_like_table_dev_fit.json` | Revision 1 human-like table: development fit, with its method and how many development decks support each cell |
| `metrics/AI_Grading_Evaluation_Metrics_revised.xlsx` · `metrics/evaluation_metrics_revised.csv` | **Current** aggregate metrics by set, criterion and arm (Revisions 1 + 2) |
| `metrics/AI_Grading_Evaluation_Metrics.xlsx` · `metrics/evaluation_metrics.csv` | Aggregate metrics as delivered, with a Guide sheet (kept for provenance) |
| `metrics/revised_results.json` | Current subgroup, mode-distribution, totals, repeatability, convergence and bootstrap results |
| `metrics/verification.json` | Aggregate output of the verification script |
| `scripts/verify_phase2.py` | Verifies the as-delivered results against the private joined table and Phase 1's private files |
| `scripts/recalibrate_human_like.py` | Builds the current results and regenerates the tables in `FINDINGS.md` and this README. It first checks that it reproduces the delivered workbook, then applies Revisions 1 and 2 |

**Private, git-ignored** (`data/private/phase2/`):
- `grading_four_methods_joined_by_project.csv`: 990 rows, one per project and criterion. Each row has the title, the instructor grade, and the full 10-run sequence for each arm.
- `AI4ALL_LLM_Grading_Research_Handoff_original.md`: the handoff as received, including per-project case studies.

Rebuild the verification and Revision 1 (no LLM calls):

```bash
python3 research/phase2_prompt_x_calibration/scripts/verify_phase2.py
```

```bash
python3 research/phase2_prompt_x_calibration/scripts/recalibrate_human_like.py
```

## How Phase 2 relates to Phase 1

| | Phase 1 · Strict rubric, local calibration ([`docs/`](../../docs/)) | Phase 2 · Prompt × calibration (this folder) |
|---|---|---|
| Criteria | 6, including Data Visualization (abstains unless evidenced) | 5 (Data Visualization excluded) |
| Runs | 1 per deck: a joint call for all six criteria; the scorer may abstain | 10 per deck and criterion, one criterion per call; always returns 1–5 |
| Prompts | Strict rubric | Strict rubric, and instructor-like |
| Calibration | B1 shift, B2 monotone table (registered before testing) | B2 table for strict (the same table); B2 refit on development for human-like (Revision 1) |
| Arm names | B0 literal, B2 calibrated, C0 always-5 | A ≈ B0, B ≈ B2, C and D new, plus an always-5 baseline |
