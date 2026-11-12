# Data governance

- **Private, never committed:** student PDFs, text, images, ZIPs, the workbook, all labels, the split registry, model outputs, run logs and results. One approved exception (DECISION_LOG D-16): `app/data/precomputed.json`, the AI scores and rationales the reviewer app serves. `data/`, `runs/`, `outputs/` and the registry are git-ignored. The repository holds only code, configuration, the rubric and documentation.
- **Never loaded by code:** `Student_Grade_Lookup`, `SU25-26` (contains names, emails, self-reflections), and `Data` columns AJ:AK.
- **Model inputs:** redacted decks plus the rubric only (allowlist in `PROTOCOL.md` §6.2).
- **External processing:** sending redacted student work to an external model API needs confirmation that AI4ALL's data and AI-use policies permit it, with appropriate data-retention settings on the API account. **Gate G0 requires this sign-off.**
- **Reviewer app and unredacted uploads:** the app redacts names, contact details and faces locally before any AI call (`src/rubric_scoring/redact.py`). It sends an image-only copy with no text layer or metadata, and blocks a request if a removed term is still in the text. Redaction is best effort and a reviewer checks it. The app host (Streamlit Community Cloud) still receives the original upload. Whether unredacted participant decks may be uploaded there is an AI4ALL policy decision; until it is approved, upload redacted decks and set `APP_PASSWORD`.
- **Phase 2 imports:** the per-project joined table and the original handoff, which pair project titles with instructor grades, are kept in git-ignored `data/private/phase2/`. Only aggregate findings and metrics are committed (`research/phase2_prompt_x_calibration/`, DECISION_LOG D-17).
- **Demographics:** none are used or inferred. See `PROTOCOL.md` §10 for the governed extension.
- **Decisions:** AI outputs never alter historical grades or any participant decision. People make every evaluative decision.
- **Public reporting:** aggregate results only, with no artifact excerpts that could identify a team, and with program review before anything is shared externally.
