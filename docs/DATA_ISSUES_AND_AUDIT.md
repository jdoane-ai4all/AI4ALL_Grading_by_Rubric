# Data issue log, audit plan and checklists

Use this document for P0 (pre-scoring audit). Historical labels are **never edited**. Resolutions are recorded in `docs/templates/resolution_log.csv`, and any new same-artifact ratings are stored separately from historical labels.

## 1. Prioritised data-issue log

| ID | Issue | Affects | Priority | Proposed handling | Owner | Status |
|---|---|---|---|---|---|---|
| DI-01 | Six projects have conflicting score vectors (020, 033, 058, 059, 118; 084 complete-vs-partial) | Label validity | High | Keep blank. Check LMS history for a regrade, and use it only if documented. Otherwise exclude, with the reason logged | PI | Open |
| DI-02 | 64 PDFs have no transferable complete label; the source's "zero" rule may mean some were real zeros | Selection bias at the low end | High | Ask the program which all-zero records were "graded 0" vs "not graded". Compare labelled vs unlabelled artifact features descriptively | PI + program | Open |
| DI-03 | 33 accepted projects also have incomplete teammate records | Group vs individual grading | Medium | Confirm with the program that Final Presentation grades were group-level. If any were individual, document the exceptions | PI | Open |
| DI-04 | Two essential-question wordings | Essential Question construct | Medium | Find out which cohort received which wording. Until then, the scorer accepts either (D-07) | PI | Open |
| DI-05 | Two Canva watermarked drafts (original preparation rows 125 and 154) | Artifact equivalence | Medium | Resolve current IDs from the manifest. Run the equivalence checklist. Exclude if the draft differs materially from the graded submission | PI | Open |
| DI-06 | 196 groups for 198 PDFs: provisional duplicates | Split integrity | Medium | Verify each multi-artifact group; split by group regardless | PI | Open |
| DI-07 | 124 low-OCR-confidence pages | Text-only condition | Low | Do not repair. Use as a robustness stratum (§9) | Engineer | Open |
| DI-08 | Redaction may remove references and data-source lines | Citations criterion | High | Check 15 decks for redaction of reference slides before scoring. If it is widespread, Citations is reported as E2-only | PI | Open |
| DI-09 | Instructor-to-project assignment unverified (AG blank); Tutorial Code is not an instructor ID | Rater effects | Low (not estimable anyway) | Record as a limitation. Never proxy instructors by tutorial | PI | Open |
| DI-11 | The project-137 deck ('Predicting Stock Outperformance'; unlabelled) has 'AI4ALL PROPOSAL PRESENTATION' on its title and closing slides | Artifact equivalence | Medium | Run the equivalence checklist: is this the final deck on a reused template, or the proposal deck? Also check that it is not the same project as project-084 (both are stock-forecasting decks) | PI | Open |
| DI-12 | project-199 row is shifted one column in the Safe Data export (total 30 sits in the Project Description column) | One label | Low | Excluded by the out-of-range gate. PI to correct the source sheet. Not auto-repaired | PI | Open |
| DI-13 | A scorer agent reported that one deck's extracted text (Drive file 1cPtGhJUfMpVG8qxYKTg3pxYxF0tCgYDT, test split) still appears to contain participant surnames on pages 1 and 22 | Privacy / redaction | High | PI to re-redact the text file (and check its PDF and ZIP). The agent reports names were not used or written to output. Consider a name-pattern sweep of all 198 text files before any further runs | PI | Open |
| DI-10 | Possible appendix or draft pages in some PDFs | All criteria | Low | Scorer flags `possible_draft_or_appendix_pages`. Review on development | PI | Open |

## 2. Prioritised evidence audit (before any scoring)
Review about 30 decks in total, using the PDFs only and never the labels, except for the conflict cases:
1. All six conflict cases (DI-01).
2. Five no-label decks with roster hits (DI-02), as a sample.
3. Every multi-artifact group (DI-06).
4. The two watermarked drafts (DI-05).
5. Fifteen decks for reference/redaction status (DI-08), sampled across cohorts.
6. Five visually dense, low-OCR decks (DI-07).

## 3. Artifact-equivalence checklist (one row per artifact in `resolution_log.csv`)
- [ ] The PDF's resource ID matches the graded submission's link (exact ID match, already verified for all 198).
- [ ] The PDF export date or version is consistent with the submission window.
- [ ] No watermark, "draft", or template placeholder text on scored slides.
- [ ] The page count and slide sequence are plausible for a 10-minute final presentation (not a proposal deck).
- [ ] If the group has multiple artifacts: they are substantively the same deck, or differences are listed.
- [ ] Redaction did not remove whole scored sections (references, visualizations, next steps). If it did, list them.
- [ ] Decision: `equivalent` / `equivalent_with_notes` / `not_equivalent_exclude`, with the reviewer's initials and date.

## 4. Reviewer checklist for label-conflict cases
- [ ] All source records for the artifact are listed (not just the first lookup hit).
- [ ] For each record: complete/partial/zero, total, timestamp if available.
- [ ] Is there documented evidence of a regrade? If yes, cite it. If no, keep the label blank.
- [ ] Never average, never majority-vote, never choose the complete vector over conflicting partial evidence.
- [ ] Record the outcome in `resolution_log.csv`. Historical data are unchanged.

## 5. Group-level vs student-specific grading
The study assumes the Final Presentation rubric was applied once per group and copied to each teammate. Agreeing copies are therefore **one** rating, not several. They must not be used as human–human reliability evidence (D-04).
