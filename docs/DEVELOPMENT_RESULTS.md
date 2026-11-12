# Development-set results: free-plan pilot (F1: evidence prompt, all six criteria per agent, text only)

**Status:** development split only (46 artifacts / 45 groups). These results are descriptive and exist to tune the design. They are **not** the study's findings, which come only from the locked test set. Every run passed the access audit (49/49) and schema validation (0 invalid). Generated 2026-11-02 from `runs/run_log.jsonl`. CIs are 95% project-group cluster bootstrap.

## Agreement with historical instructor scores

| Criterion | coverage | AI MAE [95% CI] | always-5 baseline MAE | exact (AI / baseline) | within 1 | severe (≥2) | signed bias | QWK |
|---|---|---|---|---|---|---|---|---|
| Project Description | 46/46 | 0.57 [0.36, 0.80] | 0.43 | 0.61 / 0.67 | 0.83 | 0.17 | −0.39 | 0.39 |
| Data Visualization* | 36/46 | 0.14 [0.00, 0.39] | 0.37 | 0.94 / 0.78 | 0.97 | 0.03 | +0.14 | n/a |
| Algorithm | 46/46 | 0.74 [0.54, 0.93] | 0.54 | 0.37 / 0.57 | 0.91 | 0.09 | −0.52 | 0.33 |
| Essential Question | 46/46 | 1.13 [0.89, 1.36] | 0.76 | 0.20 / 0.50 | 0.72 | 0.28 | −1.00 | 0.26 |
| Next Steps | 46/46 | 0.96 [0.67, 1.27] | 0.74 | 0.39 / 0.46 | 0.78 | 0.22 | −0.61 | 0.10 |
| Citations | 43/46 | 0.56 [0.31, 0.86] | 0.74 | 0.63 / 0.59 | 0.88 | 0.12 | −0.19 | 0.53 |

*Under the text-only rule D-11, Data Visualization is either 5 or ABSTAIN, so its agreement is computed on a pre-selected easy subset and isn't comparable with the other rows.

**Totals:** 33 of 46 projects had all six criteria scored.
- AI: MAE 2.91 [2.27, 3.58]; ICC(A,1) 0.45 [0.21, 0.65]; bias −2.24; agreement at the 24/30 threshold 0.67; cancellation ratio 0.24.
- Always-5 baseline: total MAE 3.59; threshold agreement 0.83.

## What the pattern says
1. **The AI is systematically stricter than the historical scores on every content criterion.** It beats the trivial always-5 baseline only on Citations (and on total MAE). On Project Description, Algorithm, Essential Question and Next Steps it is worse than the baseline.
2. **The gaps track specific rubric clauses the AI applied literally:**
   - Next Steps: "measurable" and "deadlines" were unmet in 21 and 19 AI-lower cases.
   - Algorithm: "pros & cons" unmet in 16.
   - Essential Question: "grounded in research" unmet in 23, and "goes well beyond program content" in 12.
   - The AI **never** gave Essential Question a 5, because it can't see the curriculum and was told to flag that case rather than guess. The historical scores gave 5 in 23 of 46.
3. **Three explanations, which this design can't yet separate:**
   - (a) Instructors gave holistic or lenient credit relative to the literal descriptors.
   - (b) Instructors saw evidence the AI didn't: oral delivery, demos, discussion of challenges and project evolution.
   - (c) The text-only extraction lost content.

   The blinded same-artifact human rescoring (Protocol §13) is the design that separates (a) and (b) from AI error.
4. **Decision-relevant consequence:** at the 24/30 nomination threshold, the AI agrees with historical outcomes in 67% of projects, against 83% for the always-5 baseline. Its strictness pushes projects below the threshold.

## Decision needed before the test set (gate G2)
The PI must choose, on development data only, between:
- **A. Rubric-literal scorer (no change).** Run the test set to confirm the strictness gap as a pre-registered negative result about reproducing historical grades.
- **B. Calibrated scorer.** Add operational rules decided on development data, then freeze and run the test set. Example: resolve the Essential Question 4-versus-5 call upward when every other level-5 element is met, because the AI cannot observe the program-context clause. Report A and B side by side, because B tunes toward historical scores rather than toward the rubric text.
