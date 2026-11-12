# Research Phases

This project has two research phases. Both use the same 198 redacted AI4ALL Ignite final-presentation decks, the same historical instructor grades, and the same locked split (46 development, 84 test, 68 unlabelled).

| Phase | Question | Where | Status |
|---|---|---|---|
| **Phase 1 · Strict Rubric, Local Calibration** | Can a rubric-literal AI scorer reproduce instructors, and can a small calibration layer close the gap? One run per deck; six criteria; abstains when content is unobservable | Pipeline in `src/`, `scripts/`, `config/`; results in [`docs/`](../docs/) ([`TEST_RESULTS.md`](../docs/TEST_RESULTS.md)) | Complete; pre-registered; locked test unlocked 2026-11-02 |
| **Phase 2 · Prompt × Calibration (2 × 2) with 10 Repeated Runs** | Does an instructor-like prompt do better than the strict one, with and without calibration? How repeatable are 10 runs, and what does calibration cost for low grades? Five criteria | [`phase2_prompt_x_calibration/`](phase2_prompt_x_calibration/) | **Closed 2026-11-04.** Produced outside this repository; independently verified. Revision 1: development-only refit of the human-like table. Revision 2: corrected `project-199` label |

## What the two phases say together
1. **A rubric-literal AI scorer is consistently stricter than these instructors**, most of all on Essential Question. The two phases agree: Phase 2's 10-run strict consensus equals Phase 1's single-run grade for 98% of deck-criterion pairs.
2. **A small per-criterion calibration table removes most of the average gap** for either prompt. But it pushes grades upward and **loses most low instructor grades**: about 14% exact agreement on instructor grades 1–3, against 53% before calibration.
3. **Nothing tested beats "always 5" on exact agreement at the criterion level.** The calibrated arms do beat it on MAE, within ±1 and project totals.
4. **After calibration, the choice of prompt barely matters.** The instructor-like prompt is closer to instructors before calibration. With both tables fitted on development decks only (Phase 2 Revision 1), the two calibrated arms give the same grade 91% of the time and don't differ significantly. So the prompt should be chosen on defensibility: the strict scorer cites evidence and can abstain, while the instructor-like prompt returns a bare integer.
5. **The supported use is human-reviewed pre-fill, never autograding.** The next valuable study is an instructor-adjudicated evidence audit on a new holdout, oversampling low grades.
