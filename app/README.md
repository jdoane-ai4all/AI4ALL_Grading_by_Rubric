# Rubric Auto-fill Reviewer (Streamlit)

A human-reviewed grading workspace for the AI4ALL Ignite Final Presentation rubric. The slides sit at the top with the AI's evidence beside them, and the six-criterion score card runs underneath. You move through a queue of submissions with Back and Next.

- **AI scores are filled in automatically.** Each one is page-cited and comes from the strict scorer, optionally with the AI4ALL calibration layer. Hover a criterion name to see its rubric levels. Click *Evidence* to see the AI's reasoning and the slides it cited; clicking a cited slide jumps the viewer to it.
- **The reviewer checks and changes scores** (0–5, where 0 means missing) and adds instructor comments. If any score is still unchanged from the auto-fill, *Confirm* first shows a reminder to check it, which can be turned off for the session. People make every grading decision.
- **Review flags** mark abstentions, low scores, totals near the 24/30 cut, and text-only input.

## Modes
| Mode | What happens to a deck | Cost |
|---|---|---|
| **Free** (default) | A deck from the study (198 AI4ALL decks) shows its **stored study score** as soon as it's uploaded. For any other deck the app gives a ready-made prompt to run in Claude chat, for one deck or many. You paste Claude's reply back and the card fills in. You can also prefill the most common historical score (5) and grade by hand. | Free |
| **API** | Any deck is scored live. Switching to API asks for an Anthropic API key, unless one is set in the app's secrets. A key typed into the app stays in that browser session only. | About $0.40–0.80 per deck (estimate, not yet measured on a live key) |

## Unredacted decks
Any deck can be uploaded. For a deck that isn't a stored study deck, the app redacts it **before** anything goes to Claude (`src/rubric_scoring/redact.py`):
- **Names:** found by a small language model that runs inside the app (spaCy), and by cue words such as "Presented by", "Group 3C:", "Team members:" or "Mentor". After a cue, the app follows the name list onto the next lines and rejoins a name that wraps mid-name. On the first two slides it also catches a comma-separated list of names with no cue. Names in any alphabet count, including accented ones. A name found once is removed everywhere in the deck.
- **Contact details:** emails, phone numbers, @handles and social-profile or GitHub links.
- **Faces and headshots:** faces are found with OpenCV's YuNet model, and every photo on a page that lists team names is blacked out.

Citation authors ("Smith et al.") and References pages are kept, because Citations is scored.

Claude receives an **image-only PDF** with no text layer and no metadata, plus the redacted text. In API mode, a final check refuses to send the request if any removed term still appears in the text. In Free mode you download the redacted copy (`submission-001.pdf`) and attach that to Claude chat, never the original.

Redaction is best effort. Use the viewer's **Redacted** view to check, and type any missed names into "Missed a name?". The Streamlit host does receive the original upload, as it does any file you upload. The original stays in that browser session's memory and isn't saved.

## Getting decks in
- **Upload:** many PDFs at once, or a `.zip` of PDFs (for example a Drive folder downloaded as a zip).
- **Google Drive browser (optional, free):**
  1. In a free Google Cloud project, enable the **Google Drive API**. Create a **service account** and download its JSON key.
  2. Share the decks folder with the service account's email (`...@...iam.gserviceaccount.com`) as **Viewer**.
  3. In the app's **Settings → Secrets**, add the JSON key as a multi-line string:
     ```toml
     GOOGLE_SERVICE_ACCOUNT_JSON = '''
     { "type": "service_account", ... paste the whole file ... }
     '''
     ```
  The sidebar then shows a folder browser with "Select all". The account sees only the folders you share with it. This has not yet been tested against a live account.

## How stored scores are matched
`app/data/precomputed.json` holds the study scorer's AI output for each deck. It contains no historical grades. `app/data/deck_index.json` maps each project to its deck title, Drive file ID and file size. An upload matches by Drive file ID first, then filename plus size, then a unique filename. If none of those match, it falls back to **content**: it checks what share of a study deck's distinctive words (taken from the stored AI evidence notes) appear in the upload. It accepts a match at 50% or more, provided that's at least twice the runner-up. This means an unredacted original still finds its stored score. In a test on 6 real decks, the right deck scored 63–88% every time and the best wrong deck scored 29% at most. Each matched deck shows its match % and has a *Not this deck?* button. Build both files with:

```bash
python3 scripts/build_app_bundle.py
```

The script reads `runs/run_log.jsonl` and, for the index, `data/private/app_index.csv`. That CSV has the columns `Project ID`, `Presentation Title` and `PDF Link`, plus an optional `pdf_size_bytes` column. Without the index, Free mode still works, but no upload will match its stored score.

**Privacy:** anyone who can open the app and has a study deck, or guesses its exact filename, can see that deck's stored AI rationale. Turn on `APP_PASSWORD` or make the app private if that matters.

## Run locally

```bash
pip install -r requirements.txt
```

```bash
streamlit run app/streamlit_app.py
```

## Hosting (Streamlit Community Cloud, free)
The app is deployed at https://doane-rubric-reviewer.streamlit.app from `main`, with main file `app/streamlit_app.py`. Every push to `main` redeploys it. You can add these optional secrets in the app's settings (template in `.streamlit/secrets.toml.example`):

```toml
ANTHROPIC_API_KEY = "sk-ant-..."         # makes API mode work without asking each user for a key
APP_PASSWORD = "choose-a-team-password"  # puts a password gate in front of the app
GOOGLE_SERVICE_ACCOUNT_JSON = '''...'''  # turns on the Drive browser
```

If you add a key, set a monthly spend limit on it in the Claude Console.

## Reliability testing (2026-11-03)
Each run used a fresh `pip install -r requirements.txt` on Python 3.12 (installs also succeed on 3.13 and 3.14). CPU and memory were capped with a Linux cgroup to mimic Streamlit's free tier when its servers are busy. The browser suite in `tests/e2e/` runs 28 checks per user.

| Stage | Result |
|---|---|
| Full CPU, 1 user, plus a rapid-clicking user | 28/28 checks; rapid clicking OK; peak memory 436 MB; no server restart |
| 8% of one core, 1 GB, cold server, 1 user | 28/28 checks; first screen 8 s, 3-deck upload 13 s, redacting a 21 MB 17-slide deck 36 s (with progress bar); peak memory 406 MB; no restart |
| 25% of one core, 1 GB, 3 users running the full suite plus 1 rapid clicker, all at once | 3 × 28/28 checks; rapid clicking OK; peak memory 659 MB; no restart; no server errors |

**Updates on Streamlit Cloud.** A push makes the host re-run `app/streamlit_app.py` without restarting the process, and Streamlit only reloads modules inside `app/`. Before the reload guard at the top of `app/streamlit_app.py`, the host kept running the `src/rubric_scoring` code it had loaded at its last restart. Its logs showed the result: `no attribute 'load_bundle'` and `KeyError: 'fill'`. The guard fingerprints `src/rubric_scoring/*.py` and reloads the package when it changes. Sessions started by an older version are reset with a notice. The footer shows the running **build** ID. A local simulation reproduced the error with the guard turned off, and showed it fixed with the guard on.

The host uses **Python 3.14**, and the tests were rerun on 3.14.

The bug these tests caught: PDFium, the PDF renderer, is not thread-safe. Before `src/rubric_scoring/pdfsafe.py` was added, using it from several threads at once crashed the server process (segfault or abort) every time it was tested. Every PDFium call now goes through one lock. `tests/test_redact.py::test_concurrent_use_is_safe` guards against a regression.

## Limits
- The tool was validated as reviewed pre-fill, not autograding. Calibrated error is about 0.53 points per criterion on the locked test set (`docs/TEST_RESULTS.md`).
- Stored scores came from **text-only** input, so Data Visualization is often an abstention. PDF input in API mode and in Claude chat lets the AI see charts, but that path has not been re-validated.
- In API mode and in Claude chat, only the locally redacted copy of a new deck goes to Anthropic. Redaction is best effort, so check the Redacted view. Whether unredacted participant decks may be uploaded to the Streamlit host at all is an AI4ALL policy decision (`docs/DATA_GOVERNANCE.md`).
