# Browser tests for the reviewer app

`suite.js` drives the real app in Chromium (Playwright) through 32 checks:
- uploads (several PDFs at once, and a .zip) and the sidebar queue
- content matching and the "Not this deck?" undo
- cited-slide links, hover text and zoom, and hover bubbles that never stay on screen after a click
- the Redacted view, the Claude pop-up and the Ctrl+Enter paste
- changing scores, the confirm warning, Previous / Next
- the gradebook and CSV export, and the API key pop-up
- no app, browser or "Failed to fetch" errors

`rapid.js` clicks faster than the server can keep up, and checks the app still responds.

```bash
python tests/e2e/make_fixtures.py e2e_fixtures
```

```bash
streamlit run app/streamlit_app.py --server.port 8601 --server.headless true
```

```bash
cd e2e_fixtures && node ../tests/e2e/suite.js http://localhost:8601 && node ../tests/e2e/rapid.js http://localhost:8601
```

The suite also needs `Original Unredacted Version.pdf`: a study deck's text, with fake names added on the first slide, saved as a PDF. It tests content matching. It's built from private data, so it's never committed; check matching with any study deck you have locally.

Stability testing ran the suite against a fresh `pip install -r requirements.txt`. CPU was limited with a Linux cgroup to 8% and to 25% of one core, with 1 GB of memory, which is roughly the free Streamlit tier when it's busy. The 25% run had four browser users at the same time. Results are in `app/README.md`.
