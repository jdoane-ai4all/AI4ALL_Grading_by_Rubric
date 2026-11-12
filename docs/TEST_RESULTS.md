# Locked test-set results (pre-registered; free-plan F1 scorer, prompt v1-free.2)

**Run:** 84 test artifacts (83 groups), scored once by fresh agents under the frozen prompt, after the calibration fit was registered (`config/calibration_fit_dev.json`, commit before any test deck was scored).
- 84/84 outputs were schema-valid, and 133/133 agent transcripts passed the access audit.
- The test split was unlocked after scoring finished (record: `data/TEST_UNLOCKED`, kept locally).
- CIs are 95% project-group cluster bootstrap with 5,000 resamples.
- Reference scores are historical instructor grades: one per project, informed by the oral presentation; provisional, not adjudicated truth.

## 1. Per-criterion agreement

| Criterion | Always-5 baseline (C0) MAE | Literal AI (B0) MAE · bias · QWK | Calibrated AI (B2) MAE · within-1 · severe | Human ≤3 (n) |
|---|---|---|---|---|
| Project Description | 0.40 | 0.73 · −0.47 · 0.20 | **0.46** · 0.98 · 0.02 | 7 |
| Data Visualization* | 0.30 | 0.22 · +0.22 · — | 0.22 · 0.97 · 0.03 | 2 |
| Algorithm | 0.56 | 0.89 · −0.70 · 0.25 | 0.54 · 0.92 · 0.08 | 10 |
| Essential Question | 0.64 | 1.31 · −1.24 · 0.05 | 0.64 · 0.92 · 0.08 | 9 |
| Next Steps | 0.87 | 0.60 · −0.36 · **0.60** | 0.61 · 0.90 · 0.10 | 14 |
| Citations | 0.65 | 0.72 · −0.41 · 0.40 | 0.65 · 0.81 · 0.19 | 16 |

*Text-only Data Visualization is scored only when at least 3 visualizations are evidenced (D-11), so it covers 60/84 decks, a pre-selected easy subset.

Coverage for the other criteria was 83 or 84 of 84.

## 2. Paired contrasts (pooled criterion MAE, A − B, same resampled groups; 476 pairs)

| Contrast | Difference [95% CI] | Reading |
|---|---|---|
| Literal B0 − always-5 C0 | **+0.20 [+0.07, +0.34]** | The literal scorer is worse than the trivial baseline at reproducing historical grades (confirms development) |
| Calibrated B2 − literal B0 | **−0.24 [−0.31, −0.17]** | The 46-deck leniency layer removes most of the gap |
| Calibrated B2 − always-5 C0 | −0.04 [−0.13, +0.06] | On average, the calibrated AI is indistinguishable from "give every project a 5" |

## 3. Totals and the 24/30 nomination decision

| | Always-5 | Literal B0 | B1 shift | Calibrated B2 |
|---|---|---|---|---|
| Total MAE | 3.43 (n=84) | 3.37 (n=57) | 2.32 (n=57) | 2.11 (n=57) |
| Signed bias | +3.43 | −2.95 | −0.42 | +0.04 |
| Agreement at 24/30 | 0.83 | 0.72 | 0.81 | 0.84 |
| ICC(A,1) | 0 (constant) | 0.30 | 0.41 | 0.31 |

AI totals require all six criteria to be scored, so their n is 57. Most of the drop comes from Data Visualization abstentions. The baseline's n is 84. Compare totals with that difference in mind.

## 4. Learning curve: how many locally graded decks does a new organisation need?
B2 was refitted on k random development groups (200 draws each) and evaluated on the test set (pooled criterion MAE):
- k=5: 0.62 [0.53, 0.73]
- k=10: 0.59 [0.52, 0.69]
- k=20: 0.56 [0.52, 0.61]
- k=30: 0.54 [0.51, 0.59]
- Literal (k=0): 0.75

Most of the benefit arrives by 10–20 graded decks, with diminishing returns after that.

## 5. Interpretation
1. **The confirmed, pre-registered finding:** a rubric-literal AI scorer is systematically stricter than these instructors on every content criterion.
   - The largest gap is Essential Question (−1.24). The AI never awards the "beyond program content" level, because it can't observe it.
   - At the nomination cut, the literal scorer agrees with historical outcomes 72% of the time, against 83% for the baseline.
2. **The calibration layer works as a portable, inspectable correction:** small per-criterion tables cut error by a quarter of a point per criterion and remove the total-score bias (−2.95 → +0.04).
3. **But average agreement is the wrong bar here.** Historical grades sit at the ceiling, so "always 5" is a strong MAE baseline that carries no information. The calibrated AI only ties it.
   - The literal scorer has the discrimination the baseline lacks: QWK 0.60 on Next Steps and 0.40 on Citations.
   - Calibration partly flattens that discrimination (Next Steps QWK drops from 0.60 to 0.22), because the historical mapping collapses literal levels 1–4 into a 4.
   - **There's a real trade-off between matching a lenient grader and telling projects apart.**
4. **Against the pre-specified tolerances (MAE ≤ 0.5, within-1 ≥ 0.90, severe ≤ 5%, threshold ≥ 0.85):** no condition meets all of them for any content criterion except calibrated Project Description, which is close. **AI scoring is not supported for unsupervised use.** A supported use is AI pre-fill with mandatory human confirmation, with the literal scorer's evidence and checklists given to the human reviewer.

## 6. Limits specific to these results
- The scorer is not API-pinned (Protocol §17).
- Input is text only, so charts are unseen.
- Historical grades are single-rater and saw the oral delivery.
- The low-score region is thin (7–16 human scores of 3 or below per criterion).
- Aggregate development distributions were seen before the split.
- DI-13: one test deck's text was reported to contain unredacted surnames; per the agent, they weren't used.
- The leniency-versus-missing-information question needs the blinded same-artifact rescoring extension (Protocol §13).
