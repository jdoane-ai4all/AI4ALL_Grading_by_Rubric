# Results table and figure specifications (no data; nothing here is a finding)

**T1. Eligibility flow.** Counts of artifacts and groups at each gate, by cohort (from `outputs/eligibility_flow.json`).

**T2. Per-criterion agreement, test, C2 replicate 1.** Columns: criterion | calls | coverage | n scored | MAE [95% CI] | exact | within-1 | severe (≥2) | signed bias | QWK [95% CI] | n human ≤3 | over-scoring rate when human ≤3. Footnote: denominators include abstentions and failures; CIs from project-group cluster bootstrap.

**T3. Total score.** n with all six scored / n in split | MAE [CI] | bias | ICC(A,1) [CI] | Bland–Altman LoA | agreement at 24 | false-nominate | false-exclude | cancellation ratio.

**T4. Paired contrasts.** C2−C1, C2−C3, C2−C4: pooled and per-criterion MAE differences [CI], Holm-adjusted for the three primary contrasts.

**T5. Stability.** Per condition with replicates: any-change rate, abstain flips, range ≥2 rate.

**T6. Review policy on test.** Frozen policy: coverage | workload | severe-error rate among accepted | criterion error rate among accepted | threshold misclassification among accepted. Plus routing reasons, counted.

**F1. Criterion confusion matrices.** Six 5×5 heatmaps (human rows, AI columns), counts annotated, shared color scale.

**F2. Total-score difference plot.** Bland–Altman: mean of human and AI totals vs difference; vertical line at 24; points jittered; group duplicates marked.

**F3. Error by human level (descriptive).** Signed error by historical score level per criterion, with n per level printed. Captioned as susceptible to regression artefacts.

**F4. Stability.** Share of project-criterion pairs with any change across 3 replicates, by criterion.

**F5. Coverage–risk curve.** Development set only for tuning: x = coverage (share auto-accepted), y = severe-error rate among accepted, one point per policy setting. The chosen frozen policy is marked, and its test-set point is overlaid.

**F6. Robustness diagnostics.** Cohort and format strata (descriptive, with n); labelled "process robustness, not demographic fairness".
