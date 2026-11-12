# Phase 2 Verification and Reconciliation with Phase 1

**What this is:** an independent check of the Phase 2 findings, done in this repository on 2026-11-04. The check recomputes the numbers from the private joined table (990 deck-criterion rows, 10 runs per arm), then cross-checks against Phase 1's labels, locked split, calibration fit and scoring logs.

**Script:** [`scripts/verify_phase2.py`](scripts/verify_phase2.py). **Output:** [`metrics/verification.json`](metrics/verification.json), aggregate numbers only.

**Bottom line:**
- Every reported number reproduces.
- The strict arms (A, B) replicate Phase 1 closely.
- The **human-like calibration table could not be reproduced from development data**. It has since been **refitted on development decks only (Revision 1)**, and arm D is now the same as arm B. [`FINDINGS.md`](FINDINGS.md) carries the revised numbers; this file documents the checks that led to the revision.

---

## 1. Reproduction of the reported results

| Check | Result |
|---|---|
| Pooled metrics (exact, MAE, within ±1, bias, QWK) for development and test, all four arms, against `evaluation_metrics.csv` | **Identical** (largest difference 1e-16) |
| Test label distribution (9 / 8 / 41 / 121 / 240) and always-5 baseline (57.3% exact, MAE 0.628) | **Reproduced** |
| Exact agreement on instructor grades 1–3: A 53.4%, B 13.8%, C 22.4%, D 13.8% (n = 58) | **Reproduced** |
| Project totals (83 projects): MAE, RMSE, exact totals, Pearson r, bias for all arms | **Reproduced** |
| Repeatability across 990 groups: unanimous 892 / 930 / 859 / 929; pairwise; modal share | **Reproduced** |
| "Three identical in a row" stopping rule: 990/990 match the mode, 3.11 calls on average | **Reproduced** |
| Cluster-bootstrap intervals (B vs A, D vs C, D vs B) | **Reproduced** within resampling noise (2,000 resamples, different seed) |
| Modes: ties, and mode = most frequent of 10 | 0 ties, 0 mismatches |
| Calibrated runs = table applied to raw runs, for every run of every row | **Exact** for both tables |

## 2. Reconciliation with Phase 1

| Check | Result |
|---|---|
| Instructor labels: Phase 2 joined table vs Phase 1 `labels.csv` | **649/649 identical** |
| Split membership vs the locked registry (`registry/split_registry.json`) | **Identical** (46 / 84 / 68) |
| Strict calibration table vs Phase 1's registered fit (`config/calibration_fit_dev.json`, `B2_table`) | **Identical** |
| Phase 2 strict 10-run mode vs Phase 1 single-run strict grade (same deck and criterion) | **962/981 identical (98.1%)**. Mean difference +0.01. 9 Phase 1 abstentions excluded |

**Strict grade identical across phases, by criterion:**

| Project Description | Algorithm | Essential Question | Next Steps | Citations |
|---|---|---|---|---|
| 97.0% | 98.0% | 98.0% | 98.5% | 99.0% |

**Locked-test MAE by criterion, Phase 1 vs Phase 2:**

| Criterion | Phase 1 literal (B0) | Phase 2 A · Strict | Phase 1 calibrated (B2) | Phase 2 B · Strict + cal |
|---|---|---|---|---|
| Project Description | 0.73 | 0.78 | 0.46 | 0.51 |
| Algorithm | 0.89 | 0.93 | 0.54 | 0.56 |
| Essential Question | 1.31 | 1.32 | 0.64 | 0.64 |
| Next Steps | 0.60 | 0.64 | 0.61 | 0.62 |
| Citations | 0.72 | 0.70 | 0.65 | 0.65 |

**Reading:**
- **Arms A and B replicate Phase 1.** The single Phase 1 run almost always matched what the 10-run Phase 2 consensus later found. That fits Phase 2's 98% modal share: one run usually equals the mode.
- **The two phases agree on the main conclusions:**
  - the strict scorer is far stricter than instructors on Essential Question;
  - calibration removes most of the gap;
  - calibration flattens discrimination (Next Steps QWK 0.60 → 0.22 in Phase 1, 0.53 → 0.22 in Phase 2).
- **Arm B has the strongest guarantee against test leakage.** Its table is Phase 1's, which was committed before any test deck was scored (DECISION_LOG D-13 to D-15).

## 3. The human-like calibration table does not reproduce

FINDINGS §3–4 say both tables were fitted on the 46 development decks without test labels. The strict table reproduces exactly from the development modes. The **human-like table does not**: 15 fitting variants were tried (rows below), and none reproduces more than 1 of its 5 criteria.

| Variant tried | Fitted on | Criteria matching the reported table |
|---|---|---|
| Phase 1 method (median per raw grade, monotone pooling) | development | 1/5 (Next Steps) |
| Mean or mode per raw grade, monotone pooling | development | 0–1/5 |
| Any of the above on all 10 runs instead of modes | development | 0–1/5 |
| The same variants | test only, or development + test | 0–1/5 |

**Refit with the Phase 1 method on development (a reproducible human-like table):**

| Criterion | Reported | Reproducible refit | Development decks per raw grade 1–5 |
|---|---|---|---|
| Project Description | [1, 2, 4, **5**, 5] | [1, 2, 4, **4**, 5] | 0, 0, 3, 19, 24 |
| Algorithm | [1, **3, 4**, 5, 5] | [1, **2, 3**, 5, 5] | 0, 0, 3, 15, 28 |
| Essential Question | [**1**, 3, 4, 4, 5] | [**3**, 3, 4, 4, 5] | 2, 1, 9, 19, 15 |
| Next Steps | [1, 2, 4, 4, 5] | [1, 2, 4, 4, 5] | 0, 0, 6, 32, 8 |
| Citations | [1, 3, 3, **5**, 5] | [1, 3, 3, **4**, 5] | 0, 2, 10, 12, 22 |

Several reported cells rest on few or no development decks. For example, human-like Algorithm raw 2 has none and raw 3 has 3. So those cells come from a rule or a judgement call, not from the data. The fitting procedure isn't documented.

The table does **not** look as if it was fitted on test labels either: test-only fits don't reproduce it. **The procedure is simply unknown.**

**Sensitivity of arm D (locked test, the 419 labels as delivered):**

| Arm | Exact | MAE | Within ±1 | Bias | QWK | Exact on instructor 1–3 |
|---|---|---|---|---|---|---|
| D · reported table | 57.0% | 0.554 | 89.3% | +0.138 | 0.300 | 13.8% |
| **D · reproducible development refit** | **51.3%** | **0.609** | 89.7% | −0.017 | 0.265 | 15.5% |
| B · Strict + cal (for reference) | 52.5% | 0.597 | 89.7% | −0.014 | 0.269 | 13.8% |

**Implication:** D's lead over B depended on the human-like table, and its MAE advantage was already not distinguishable from zero.

**Resolution (Revision 1, 2026-11-04):** the reproducible development refit is now the human-like table (`calibration/human_like_table_dev_fit.json`, built by `scripts/recalibrate_human_like.py`), and every arm-D number in FINDINGS is recomputed with it.
- Before revising anything, the script checks that its metric code reproduces every row of the delivered workbook.
- D vs B is now −1.2 pp exact [−3.8, +1.2] and −0.012 MAE improvement [−0.040, +0.014]: no difference.
- B and D give the same grade on 91% of test comparisons, against 62% for the raw prompts. Calibration maps both prompts onto essentially the same grades.

## 4. The project-199 label

**Resolved in Revision 2:** FINDINGS now uses Phase 1's corrected label (420 test labels, 84 totals).

As delivered, Phase 2 counted 419 test labels because `project-199`'s Project Description entry was invalid (30) in the source workbook.
- Phase 1 recorded the PI's correction of that shifted row (DECISION_LOG D-14). Phase 1's `labels.csv` has a valid Project Description for `project-199`; the Phase 2 joined table has it as missing.
- So Phase 2 used the uncorrected workbook. Its other four `project-199` labels match Phase 1's corrected row, so only this one cell is affected.
- Re-scoring with the corrected label would give **420 labels and 84 complete totals**. That needs no new LLM calls, only a re-run of the metrics.

## 5. Methodological differences between the phases

| | Phase 1 | Phase 2 |
|---|---|---|
| Call structure | One joint call scores all six criteria | One call per criterion |
| Unobservable content | The scorer may **abstain** (redaction, oral-only, missing images) | Every run returns 1–5; no abstention |
| Data Visualization | Scored only when at least 3 visualisations are evidenced (D-11) | Excluded |
| Runs | 1 per deck | 10 per deck and criterion; the mode is reported |
| Audit trail in this repository | Prompts frozen (v1-free.2), access audits for every agent, run log, schema validation | Aggregate tables and 10-run sequences; prompts, model IDs and raw transcripts not in the handoff |

**Abstention vs forced score:** Phase 1's abstentions were rare (9 of the 990 deck-criterion cells compared here), but they mark exactly the cases defensibility cares about (FINDINGS §12, point 3). Phase 2's forced 1–5 grades for those cells can't be told apart from grades with real evidence.

## 6. Additional observations

- **On project totals, the calibrated arms beat "always 25" clearly:** current total MAE B 2.17 and D 2.06 vs 3.13. The "doesn't beat the baseline" caution applies to criterion-level exact agreement, not to totals.
- **On within ±1, the calibrated arms beat the baseline:** currently B 89.8%, D 89.8%, always-5 86.2%.
- **Calibration creates the repeatability gains for reported grades** (A 90.1% → B 93.9% unanimous). The table merges grades, so the underlying model is no more consistent (FINDINGS §9).

## 7. What cannot be verified here, and recommendations

**Can't be verified from the handoff:**
- **Generation provenance** for the 19,800 runs: the Phase 2 strict prompt text, model and version, settings, dates, and whether the 10 runs were independent (separate sessions, no caching or shared context). The instructor-like prompt was supplied on 2026-11-04 (`prompts/human_like_prompt.py`).
- **The original fitting code** for the human-like table. This is no longer needed: Revision 1 replaces the table (§3).

**Recommendations, in order:**
1. ~~Recover the instructor-like prompt; refit the human-like table on development and re-report D~~ **Done (Revision 1).**
2. ~~Re-run the metrics with `project-199`'s corrected label~~ **Done (Revision 2).**
3. **Record generation provenance** for any future runs, following FINDINGS §12 point 4 and Phase 1's run log and access-audit pattern.
4. **Bring abstention back** for unobservable content, or flag low-evidence cells, before any use that affects students.
5. **Next study, as FINDINGS §13 recommends:**
   - an instructor-adjudicated evidence audit, oversampling instructor grades 1–3;
   - a new later holdout.
