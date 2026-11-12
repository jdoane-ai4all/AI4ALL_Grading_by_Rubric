"""Rubric Auto-fill Reviewer: a human-reviewed grading workspace in AI4ALL's brand (Style Guide v1.2).

Where AI suggestions come from, per uploaded deck:
  1. Stored study scores (the AI4ALL Ignite decks), matched by Drive ID / filename / size
  2. API mode: live scoring with Claude, on a locally redacted copy of the deck
  3. Free mode: a redacted copy plus a prompt for Claude chat; the reply is pasted back
  4. Or a most-common-score prefill (labelled, not AI)
Scores are filled in automatically; a person checks, changes and confirms every one before export.

Run locally:   streamlit run app/streamlit_app.py
"""
import base64
import html
import csv
import io
import json
import os
import sys
import zipfile
from pathlib import Path

import streamlit as st
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def _code_version() -> str:
    """Fingerprint of the app's own Python code outside this file."""
    import hashlib
    h = hashlib.sha1()
    for f in sorted((ROOT / "src" / "rubric_scoring").glob("*.py")) + [ROOT / "app" / "app_drive.py"]:
        h.update(f.name.encode() + f.read_bytes())
    return h.hexdigest()[:12]


# Streamlit Cloud applies a new push by re-running this file WITHOUT restarting the process, and it only
# reloads modules inside app/. Our package lives in src/, so without this the server keeps running the
# helper code it loaded at its last restart. When the code changes, drop the old modules and caches so
# the imports below load the current version.
CODE_VERSION = _code_version()
_pkg = sys.modules.get("rubric_scoring")
if _pkg is not None and getattr(_pkg, "_code_version", None) != CODE_VERSION:
    for _m in [m for m in sys.modules if m == "rubric_scoring" or m.startswith("rubric_scoring.") or m == "app_drive"]:
        del sys.modules[_m]
    st.cache_resource.clear()
    st.cache_data.clear()
import rubric_scoring  # noqa: E402
rubric_scoring._code_version = CODE_VERSION
import hashlib as _hl  # noqa: E402
BUILD = _hl.sha1((CODE_VERSION + Path(__file__).read_text()).encode()).hexdigest()[:7]
from rubric_scoring import pdfsafe  # noqa: E402
from rubric_scoring import redact as R  # noqa: E402
from rubric_scoring import review_tool as rt  # noqa: E402
from rubric_scoring.rubric import CRITERIA, criterion, load_rubric  # noqa: E402

ASSETS = Path(__file__).resolve().parent / "assets"
st.set_page_config(page_title="Rubric Auto-fill Reviewer · AI4ALL", page_icon=Image.open(ASSETS / "ai4all_mark.png"),
                   layout="wide")
OPTS = ["—", 0, 1, 2, 3, 4, 5]
RUBRIC_URL = ("https://docs.google.com/document/d/1DQhQFxY00mRilbdSle2KqOHl7COa49eEnVI9diTk1_g/edit"
              "?tab=t.0#heading=h.x1frx31jk0bn")


@st.cache_data
def img64(name):
    return base64.b64encode((ASSETS / name).read_bytes()).decode()


def secret(name):
    try:
        return st.secrets.get(name) or os.environ.get(name)
    except Exception:
        return os.environ.get(name)


@st.cache_resource
def bundle():
    return rt.load_bundle()


@st.cache_resource
def profiles():
    return rt.content_profiles(bundle()[0])




@st.cache_resource
def warm_models():
    """Load the name and face models in the background once per server, so the first redaction is quick."""
    import threading

    def _load():
        try:      # lowest CPU priority, so it never slows the page someone is using (per-thread on Linux)
            os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), 19)
        except Exception:
            pass
        R._nlp()
        R._face_detector()
    t = threading.Thread(target=_load, daemon=True)
    t.start()
    return t


@st.cache_resource
def cal_table():
    return rt.load_calibration()


@st.cache_data(show_spinner=False, max_entries=40)
def render_page(key: str, _data: bytes, page: int, scale: float, redacted: bool, red_ver: str, _red=None) -> tuple[str, int]:
    """Base64 JPEG of one page (optionally with redaction boxes) and the page count."""
    n = pdfsafe.page_count(_data)
    img = R.render_redacted(_data, _red if redacted else None, min(page, n - 1), scale)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode(), n


st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Crimson+Text:ital,wght@0,400;0,600;0,700;1,400&family=Miriam+Libre:wght@400;700&display=swap" rel="stylesheet">
<style>
/* AI4ALL palette: Forest #32533D, Plum #930059, Mint #ACE4AA, Miami #FFDDE2, Sunshine #FFB200, Coral #FF0054 */
:root { --navy:#32533D; --blue:#930059; --bright:#930059; --ice:#FFEEF1; --sky:#ACE4AA; --ink:#1D3325; --muted:#5E7065; --orange:#FF0054;
        --head:"Miriam Libre", "Trebuchet MS", Arial, sans-serif; }
html, body, [class*="css"], .stMarkdown, input, textarea { font-family:'Crimson Text', Georgia, serif !important; }
.stMarkdown p, .stMarkdown li { font-size: 1.06rem; }
h1, h2, h3, h4, button, label, .kicker, .step b, .pill, .total .l, .deckhead .dn, .deckhead .dname, .citelabel, table.gb th, .footer, .slideno { font-family: var(--head) !important; }
.block-container { padding-top: 3.2rem; max-width: 1600px; }
h1, h2, h3, h4 { color: var(--bright); font-weight: 700; letter-spacing: 0; }
.hero { background: radial-gradient(circle at 85% 30%, #4A7058 0%, var(--navy) 45%, #243C2C 100%); border-radius: 18px;
        padding: 22px 32px; color: white; display:flex; align-items:center; justify-content:space-between;
        box-shadow: 0 8px 24px rgba(50,83,61,.18); margin-bottom: 14px; }
.hero h1 { color: white; margin: 2px 0 6px 0; font-size: 2.0rem; }
.hero .kicker { color: var(--sky); font-size: .78rem; font-weight: 600; letter-spacing: .12em; text-transform: uppercase; }
.hero p { color: #E3F3E2; margin: 0; font-size: 1rem; max-width: 760px; }
.hero img { height: 128px; image-rendering: pixelated; }
.hero.slim { padding: 10px 24px; } .hero.slim h1 { font-size: 1.25rem; margin:0; } .hero.slim img { height: 48px; }
.step b { color: var(--bright); display:block; font-size:.78rem; letter-spacing:.1em; text-transform:uppercase; margin-bottom:4px; }
.step { color: var(--ink); font-size: .95rem; }
.pill { background: var(--ice); color: var(--blue); padding: 2px 9px; border-radius: 999px; font-weight: 600; font-size: .76rem; margin: 0 4px 0 0; white-space: nowrap; display:inline-block; }
.pill.none { background:#F1F3F5; color: var(--muted); } .pill.changed { background:#FFF1CC; color:#7A5200; }
.pill.ok { background:#E3F6E2; color:#2F6B3F; } .pill.fill { background:#FFEEF1; color:#930059; border:1px dashed #E58AA9; }
.flag { background:#FFF1CC; padding:2px 8px; border-radius:8px; color:#7A5200; font-size:0.76rem; margin:2px 4px 2px 0; display:inline-block; }
.total { background: var(--navy); color: white; border-radius: 16px; padding: 12px 18px; }
.total .n { font-size: 2.2rem; font-weight: 700; line-height: 1.05; } .total .l { color: var(--sky); font-size:.72rem; letter-spacing:.1em; text-transform:uppercase; }
.total .src { font-size:.8rem; color:#E3F3E2; margin-top: 4px; }
.viewer { overflow:auto; max-height: 54vh; border-radius: 12px; background:#22382A; padding: 6px; }
.viewer img { display:block; margin: 0 auto; border-radius: 6px; }
.viewer-bar { color: var(--muted); font-size: .85rem; }
.tip { position: relative; display: inline-block; font-weight: 650; color: var(--navy); font-size: .95rem; cursor: help; }
.tip.cname > .tname { text-decoration: underline dotted #C77FA6; text-decoration-thickness: 1px; text-underline-offset: 4px; }
.tip .tipbox { visibility: hidden; opacity: 0; transition: opacity .12s; position: absolute; z-index: 9999; bottom: 130%; left: 0;
       width: 340px; background: var(--navy); color: #F3FAF2; padding: 12px 14px; border-radius: 12px; font-weight: 400;
       font-size: .8rem; line-height: 1.4; box-shadow: 0 10px 28px rgba(0,0,0,.28); }
.tip .tipbox.right { left: auto; right: 0; }
.tip .tipbox b { color: var(--sky); }
.tip:hover .tipbox { visibility: visible; opacity: 1; }
[data-testid="stButton"] button { position: relative; overflow: visible; }
[data-testid="stButton"] button::after { position: absolute; z-index: 10001; bottom: calc(100% + 8px); left: 50%;
       transform: translateX(-50%); width: max-content; max-width: 300px; white-space: normal; text-align: left;
       background: var(--navy); color: #F3FAF2; padding: 7px 10px; border-radius: 8px; font-size: .78rem; font-weight: 400;
       line-height: 1.35; box-shadow: 0 6px 18px rgba(0,0,0,.22); pointer-events: none;
       visibility: hidden; opacity: 0; transition: opacity .1s, visibility 0s linear .1s; }
[data-testid="stButton"] button:hover::after { visibility: visible; opacity: 1; transition: opacity .12s .35s, visibility 0s .35s; }
[data-testid="stButton"] button:not(:hover)::after { visibility: hidden !important; opacity: 0 !important; }
.st-key-view { position: relative; overflow: visible !important; }
.st-key-view::after { content: "Redacted shows what Claude is given for a new deck."; position: absolute; z-index: 10001;
       bottom: calc(100% + 8px); left: 50%; transform: translateX(-50%); width: max-content; max-width: 300px;
       background: var(--navy); color: #F3FAF2; padding: 7px 10px; border-radius: 8px; font-size: .78rem; line-height: 1.35;
       box-shadow: 0 6px 18px rgba(0,0,0,.22); pointer-events: none; visibility: hidden; opacity: 0; }
.st-key-view:hover::after { visibility: visible; opacity: 1; transition: opacity .12s .35s, visibility 0s .35s; }
.st-key-viewbar, .st-key-viewbar * { overflow: visible !important; }
.st-key-viewbar { position: relative; z-index: 20; }
.st-key-viewbar [data-testid="stButton"] button::after, .st-key-view::after { bottom: auto; top: calc(100% + 8px); }
.ev-obs { font-size: .86rem; color: var(--ink); padding-top: 6px; }
.ev-here { background: #FFF1CC; border-radius: 6px; padding: 2px 6px; }
.redact-note { background:#EAF7E9; border:1px solid #ACE4AA; color:#2F5A3B; border-radius:10px; padding:8px 12px; font-size:.84rem; }
.footer { margin-top: 26px; padding: 14px 0 4px 0; border-top: 1px solid #F3D7DE; display:flex; justify-content:space-between; align-items:center; color: var(--muted); font-size: .85rem; }
.footer a { color: var(--bright); text-decoration: none; margin-left: 14px; font-weight: 600; }
.footer img { height: 24px; vertical-align: middle; margin-right: 8px; }
div[class*="st-key-crit_"], div[class*="st-key-crit_"] *:not(.tipbox),
div[data-testid="stColumn"]:has(div[class*="st-key-crit_"]),
div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-crit_"]) { overflow: visible !important; }
div[class*="st-key-crit_"] { gap: .45rem !important; padding: 10px 10px 8px 10px !important; }
div[class*="st-key-crit_"] [data-testid="stWidgetLabel"] p { font-size: .72rem; color: var(--muted); }
.tip.cname { display: block; font-size: .88rem; line-height: 1.45; height: 2.9em !important; }
div[class*="st-key-crit_"] [data-testid="stElementContainer"]:has(.tip),
div[class*="st-key-crit_"] [data-testid="stElementContainer"]:has(.tip) *:not(.tipbox):not(.cname) { margin-bottom: 0 !important; height: auto !important; }
div[class*="st-key-crit_"] [data-testid="stElementContainer"]:has(.pill) { padding-bottom: 3px; }
.tip .pill { cursor: help; display: inline-flex; align-items: center; gap: 4px; margin: 4px 0 2px 0; padding: 3px 9px; }
.iicon { display: inline-flex; align-items: center; justify-content: center; width: 13px; height: 13px; flex: 0 0 13px;
         border-radius: 50%; border: 1.4px solid currentColor; font: 700 9px/1 Georgia, 'Times New Roman', serif;
         font-style: italic; box-sizing: border-box; }
.tflag { color: #FFB200; }
.total .n span { font-size: 1.1rem; color: var(--sky); margin-left: 3px; }
.deckhead { display:flex; align-items:center; gap:12px; flex-wrap: nowrap; min-width: 0; }
.deckhead .pill { flex: 0 0 auto; }
/* Streamlit wraps the bar in a box of its own height, so the wrapper is what sticks to the top */
div[data-testid="stLayoutWrapper"]:has(> .st-key-topbar) { position: sticky; top: 3.75rem; z-index: 990;
    background: #FFFFFF; padding: 8px 0; border-bottom: 1px solid #F3D7DE; }
.st-key-topbar [data-testid="stElementContainer"]:has(.deckhead) { flex: 1 1 0 !important; min-width: 0 !important;
    overflow: visible !important; height: auto !important; }
.st-key-topbar [data-testid="stElementContainer"]:has(.deckhead) * { min-width: 0; height: auto; margin-bottom: 0 !important; }
.st-key-topbar .deckhead { padding: 4px 0; line-height: 1.35; }
@media (max-height: 520px) { div[data-testid="stLayoutWrapper"]:has(> .st-key-topbar) { position: static; } }
@media (max-width: 700px) { .deckhead .dn { display: none; } .deckhead { gap: 8px; } }
@media (max-width: 480px) { .deckhead .pill { display: none; } }
.legend { margin: 0 0 18px 0 !important; padding-left: 1.1rem; }
.legend li { color: #CFE3D3 !important; font-size: .8rem !important; line-height: 1.5; margin: 0 !important; padding: 0 !important; }
.citelabel { font-size: .72rem; color: var(--muted); margin: 2px 0 0 0; line-height: 1.2; }
div[data-testid="stElementContainer"]:has(.citelabel), div[data-testid="stElementContainer"]:has(.citelabel) * {
    height: auto !important; margin-bottom: 0 !important; }
div[class*="st-key-cites_"] button { min-height: 1.9rem; padding: 0 .65rem; }
.deckhead .dn { color: var(--muted); font-size: .85rem; font-weight: 600; text-transform: uppercase; letter-spacing: .08em; }
.deckhead .dname { color: var(--navy); font-weight: 700; font-size: clamp(.78rem, 1.35vw, 1.1rem); white-space: nowrap;
                  overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.slideno { color: var(--muted); font-size: .9rem; text-align: center; white-space: nowrap; }
.pbar { height: 8px; background: #284534; border-radius: 99px; overflow: hidden; margin: 2px 0 4px 0; }
.pbar > div { height: 100%; background: var(--sky); }
.pbar-t { font-size: .8rem; color: #CFE3D3 !important; margin-bottom: 8px; }
.pbar.light { background: var(--ice); } .pbar.light > div { background: var(--bright); }
.pbar-t.light { color: var(--muted) !important; }
.st-key-queue { gap: .35rem !important; }
.st-key-queue button { justify-content: flex-start !important; text-align: left; }
.st-key-queue button p { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.gbwrap { overflow-x: auto; }
table.gb { border-collapse: collapse; width: 100%; font-size: .85rem; }
table.gb th { background: var(--navy); color: white; padding: 6px 8px; text-align: left; font-weight: 600; }
table.gb td { padding: 5px 8px; border-bottom: 1px solid #F3D7DE; }
section[data-testid="stSidebar"] { background: var(--navy); }
section[data-testid="stSidebar"] * { color: #F3FAF2 !important; }
section[data-testid="stSidebar"] [data-testid="stSelectbox"] div,
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] { background: #284534 !important; border-color: #4A7058 !important; }
section[data-testid="stSidebar"] button { background:#284534 !important; border-color:#4A7058 !important; }
section[data-testid="stSidebar"] [data-testid="stFileUploader"] div:has(> small),
section[data-testid="stSidebar"] [data-testid="stFileUploader"] li,
section[data-testid="stSidebar"] [data-testid="stFileUploader"] ul > div { background:#284534 !important; }
section[data-testid="stSidebar"] [data-testid="stButtonGroup"] button[aria-checked="true"] { background:#930059 !important; border-color:#930059 !important; font-weight:700; }
section[data-testid="stSidebar"] .st-key-queue [data-testid="stBaseButton-primary"] { background: var(--bright) !important; border-color: var(--sky) !important; }
.st-key-main_upload [data-testid="stFileUploaderDropzone"] { background: var(--ice); border: 2px dashed #E58AA9; border-radius: 14px; padding: 26px; }
/* Streamlit info boxes in brand colors (plum on Miami) instead of the default blue */
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]) { background: var(--ice) !important; color: var(--bright) !important; }
[data-testid="stAlertContentInfo"], [data-testid="stAlertContentInfo"] * { color: var(--bright) !important; }
</style>""", unsafe_allow_html=True)


def password_gate():
    pw = secret("APP_PASSWORD")
    if not pw or st.session_state.get("authed"):
        return
    _, m, _ = st.columns([1, 2, 1])
    with m:
        st.markdown(f"<div style='text-align:center;margin-top:40px'><img src='data:image/png;base64,{img64('ai4all_pill_plum.png')}' height='56' alt='AI4ALL'>"
                    "<h2>Rubric Auto-fill Reviewer</h2><p style='color:#5E7065'>Team access only.</p></div>", unsafe_allow_html=True)
        entered = st.text_input("Team password", type="password", label_visibility="collapsed", placeholder="Team password")
        if st.button("Enter", type="primary", width="stretch"):
            import hmac
            if hmac.compare_digest(entered, pw):
                st.session_state.authed = True
                st.rerun()
            st.error("That password isn't right.")
    st.stop()


password_gate()
S = st.session_state
# A session started by an older version of the app holds data in an older shape: start it fresh.
SESSION_SCHEMA = 3
if S.get("schema") != SESSION_SCHEMA:
    had_work = bool(S.get("subs"))
    for k in list(S.keys()):
        del S[k]
    S.schema = SESSION_SCHEMA
    if had_work:
        S.flash = ("error", "The app was updated while you were working, so your queue was cleared. "
                            "Please add your decks again (download any confirmed grades first next time).")
for k, v in {"subs": [], "cur": 0, "mode": "Free", "user_key": "", "sub_n": 0, "up_n": 0, "skip_warn": False,
             "zoom": 100, "view": "Original", "use_cal": True, "flash": None}.items():
    S.setdefault(k, v)
PRE, INDEX = bundle()


def api_key():
    return secret("ANTHROPIC_API_KEY") or S.user_key


@st.dialog("Switch to API mode")
def key_dialog():
    st.markdown("API mode scores **any** deck live with Claude, including decks the stored scores don't cover. "
                "It needs an Anthropic API key, billed to that key's account (roughly $0.40–0.80 per deck).")
    k = st.text_input("Anthropic API key", type="password", placeholder="sk-ant-...")
    st.caption("Your key is kept only in this browser session and never saved. Get one at platform.claude.com → API Keys. "
               "Only the redacted copy of each deck is sent.")
    c1, c2 = st.columns(2)
    if c1.button("Connect", type="primary", width="stretch"):
        if not k.startswith("sk-ant-"):
            st.error("That doesn't look like an Anthropic API key.")
        else:
            try:
                import anthropic
                anthropic.Anthropic(api_key=k).models.list(limit=1)
                S.user_key, S.mode = k, "API"
                st.rerun()
            except Exception as e:
                st.error(f"Key check failed: {type(e).__name__}")
    if c2.button("Stay in Free mode", width="stretch"):
        S.mode = "Free"
        st.rerun()


HAS_KEY = S.mode == "API" and bool(api_key())


# ── submission model ─────────────────────────────────────────────────────
# Each submission keeps its own scores, so nothing is lost when Streamlit drops off-screen widgets.
def by_key(k):
    return next((s for s in S.subs if s["key"] == k), None)


def add_submission(name: str, data: bytes, drive_id: str | None = None):
    key = rt.file_key(data)
    if any(s["key"] == key for s in S.subs):
        return
    S.sub_n += 1
    pid, how = rt.match_deck(name, len(data), INDEX, drive_id)
    if not pid and PRE:
        try:
            mpid, share = rt.best_content_match(rt.pdf_text(data), profiles())
            if mpid:
                pid, how = mpid, f"content match {round(share * 100)}%"
        except Exception:
            pass
    sub = {"key": key, "name": name, "alias": f"submission-{S.sub_n:03d}.pdf", "data": data, "pid": pid, "match": how,
           "result": None, "source": None, "fill": None, "scores": {c: None for c in CRITERIA},
           "auto": {c: False for c in CRITERIA}, "comments": "", "reviewer": "", "confirmed": None, "page": 0,
           "red": None, "red_terms": "", "redpdf": None, "sel": CRITERIA[0]}
    S.subs.append(sub)
    res = rt.precomputed_result(pid, PRE) if pid else None
    if res:
        set_result(sub, res, "stored study score")


def ingest_uploads(files):
    for f in files:
        b = f.getvalue()
        if f.name.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(b)) as z:
                for n in z.namelist():
                    if n.lower().endswith(".pdf") and not n.startswith("__MACOSX") and ".." not in n:
                        add_submission(Path(n).name, z.read(n))
        elif f.name.lower().endswith(".pdf"):
            add_submission(f.name, b)


def suggestions(sub):
    if not sub["result"]:
        return {c: None for c in CRITERIA}
    return rt.calibrate(sub["result"], cal_table() if S.use_cal else None)


def set_result(sub, result, source):
    """Store an AI result and auto-fill every score the reviewer hasn't set by hand."""
    sub["result"], sub["source"], sub["fill"] = result, source, "ai"
    sug = suggestions(sub)
    for c in CRITERIA:
        if sub["auto"][c] or sub["scores"][c] is None:
            sub["scores"][c] = sug[c]
            sub["auto"][c] = sug[c] is not None


def refresh_autofill(sub):
    """Follow the calibration setting for scores that are still AI-filled."""
    if sub["fill"] != "ai":
        return
    sug = suggestions(sub)
    for c in CRITERIA:
        if sub["auto"][c]:
            sub["scores"][c] = sug[c]


def get_redaction(sub):
    if sub["red"] is None:
        terms = [t.strip() for t in sub["red_terms"].split(",") if t.strip()]
        ph = st.empty()

        def prog(i, n):
            ph.markdown(f"<div class='pbar light'><div style='width:{i / max(n, 1) * 100:.0f}%'></div></div>"
                        f"<div class='pbar-t light'>Removing names, contact details and faces: slide "
                        f"{min(i + 1, n)} of {n}…</div>", unsafe_allow_html=True)

        sub["red"] = R.analyse(sub["data"], terms, progress=prog)
        sub["redpdf"] = None
        ph.empty()
    return sub["red"]


def get_redacted_pdf(sub):
    red = get_redaction(sub)
    if sub["redpdf"] is None:
        with st.spinner("Building the redacted copy…"):
            sub["redpdf"] = R.redacted_pdf(sub["data"], red)
    return sub["redpdf"]


def ai_score_live(sub):
    import anthropic
    red = get_redaction(sub)
    r = rt.score_deck(anthropic.Anthropic(api_key=api_key(), max_retries=4), get_redacted_pdf(sub), sub["alias"],
                      extra_text=red.text(), guard=lambda text: R.leaks(text, red))
    set_result(sub, r, "live AI score (redacted copy)")


def load_reply(text: str, current=None) -> str:
    parsed = rt.parse_pasted(text)
    hits = 0
    for fname, items in parsed.items():
        if fname == "*":
            targets = [current] if current else []
        else:
            nf = rt.norm_title(fname)
            targets = [s for s in S.subs if rt.norm_title(s["alias"]) == nf or rt.norm_title(s["name"]) == nf]
        for t in targets:
            set_result(t, rt.result_from_items(items, "pasted from Claude", "Claude chat"), "pasted from Claude")
            hits += 1
    return f"Loaded AI scores for {hits} deck(s)." if hits else "No deck in the queue matched the filenames in that reply."


# widget callbacks (they run before the page re-renders, so Ctrl+Enter in a text box works too)
def cb_score(k, c):
    sub = by_key(k)
    v = S[f"score_{k}_{c}"]
    sub["scores"][c] = None if v == "—" else int(v)
    sub["auto"][c] = False


def cb_text(k, field):
    by_key(k)[field] = S[f"{field}_{k}"]


def cb_paste(k):
    txt = S.get(f"paste_{k}", "")
    if not txt.strip():
        return
    try:
        msg = load_reply(txt, by_key(k))
        S.flash = ("success" if msg.startswith("Loaded") else "error", msg)
        S[f"paste_{k}"] = ""
        S.dialog_done = S.flash[0] == "success"
    except Exception as e:
        S.flash = ("error", f"Couldn't read that reply: {e}")


def bind(widget_key, value):
    """Seed a widget from the submission before it renders."""
    S[widget_key] = value


def do_confirm(sub):
    sug = suggestions(sub)
    final = dict(sub["scores"])
    base = sub["result"] or rt.result_from_items([], "none")
    sub["confirmed"] = rt.review_record(sub["name"], sub["reviewer"], base, sug, final, {c: "" for c in CRITERIA},
                                        sub["comments"], "ai4all_ignite_B2_2026-11" if S.use_cal else "none")
    sub["confirmed"]["ai_source"] = sub["source"]
    sub["confirmed"]["auto_filled_unchanged"] = [c for c in CRITERIA if sub["auto"][c]]
    S.last_reviewer = sub["reviewer"]
    S.cur = min(S.subs.index(sub) + 1, len(S.subs) - 1)


@st.dialog("Before you confirm", width="medium")
def review_warning(k):
    sub = by_key(k)
    n = sum(sub["auto"].values())
    b, a = st.columns([3, 1], vertical_alignment="center")
    a.markdown(f"<img src='data:image/png;base64,{img64('ai4all_dither_coral.png')}' alt='' "
               "style='width:100%;max-width:150px;display:block;margin-left:auto;image-rendering:pixelated;border-radius:12px'>", unsafe_allow_html=True)
    b.markdown(f"**{n} of 6 scores were filled in automatically and haven't been changed.**\n\n"
               "The AI can miss things: charts it couldn't read, work a team only showed out loud, or an unusual "
               "but valid approach. Before you confirm, make sure each score matches what's on the slides.")
    dont = st.checkbox("Don't show this again for the rest of this session")
    c1, c2 = st.columns(2)
    if c1.button("Back to reviewing", width="stretch"):
        S.skip_warn = dont
        st.rerun()
    if c2.button("I've checked them: confirm", type="primary", width="stretch"):
        S.skip_warn = dont
        do_confirm(sub)
        st.rerun()


for _s in S.subs:
    refresh_autofill(_s)


# ── sidebar: mode, queue, settings ───────────────────────────────────────
def on_cal():
    S.use_cal = S.cal_choice.startswith("Calibrated")


def bar_html(frac, text):
    return (f"<div class='pbar'><div style='width:{frac * 100:.0f}%'></div></div>"
            f"<div class='pbar-t'>{text}</div>")


def go_to(i):
    S.cur = i


with st.sidebar:
    st.markdown(f"<img src='data:image/png;base64,{img64('ai4all_pill_forest.png')}' height='40' alt='AI4ALL'>",
                unsafe_allow_html=True)
    picked_mode = st.segmented_control("Mode", ["Free", "API"], default=S.mode, key="mode_ctl")
    if picked_mode and picked_mode != S.mode:
        if picked_mode == "API" and not api_key():
            key_dialog()
        else:
            S.mode = picked_mode
            st.rerun()
    st.caption("**Free:** stored scores for the AI4ALL study decks; other decks are scored by pasting a prompt "
               "into Claude chat." if S.mode == "Free" else
               "**API:** any deck is redacted here, then scored live by Claude, billed to the connected key.")
    if S.mode == "API" and S.user_key and st.button("Disconnect key", width="stretch"):
        S.user_key, S.mode = "", "Free"
        st.rerun()

    if S.subs:
        n_conf = sum(1 for s in S.subs if s["confirmed"])
        st.header("Queue")
        st.markdown(bar_html(n_conf / len(S.subs), f"{n_conf} of {len(S.subs)} confirmed"), unsafe_allow_html=True)
        with st.container(key="queue"):
            for i, s in enumerate(S.subs):
                icon = "✅" if s["confirmed"] else ("🟣" if s["result"] else "◻️")
                name = s["name"] if len(s["name"]) <= 30 else s["name"][:28] + "…"
                st.button(f"{icon} {name}", key=f"q_{i}", on_click=go_to, args=(i,), width="stretch",
                          type="primary" if i == S.cur else "secondary")
        st.markdown("<ul class='legend'><li>✅ confirmed</li><li>🟣 AI scores ready</li><li>◻️ needs AI scores</li></ul>",
                    unsafe_allow_html=True)
        up = st.file_uploader("Add more decks", type=["pdf", "zip"], accept_multiple_files=True,
                              key=f"up_side_{S.up_n}",
                              help="PDFs or a .zip. In Google Drive, select files or a folder and choose Download.")
        if up:
            with st.spinner(f"Reading {len(up)} file(s)…"):
                ingest_uploads(up)
            S.up_n += 1
            st.rerun()
    if secret("GOOGLE_SERVICE_ACCOUNT_JSON"):
        with st.expander("Browse Google Drive", expanded=False):
            from app_drive import drive_browser  # noqa: E402
            picked = drive_browser(secret("GOOGLE_SERVICE_ACCOUNT_JSON"))
            for name, data, fid in picked:
                add_submission(name, data, fid)
            if picked:
                st.rerun()

    if S.subs and HAS_KEY:
        todo = [x for x in S.subs if not x["result"]]
        if todo and st.button(f"Score {len(todo)} unscored deck(s) with AI", width="stretch"):
            note = st.empty()
            for i, x in enumerate(todo):
                note.markdown(bar_html(i / len(todo), f"Scoring {i + 1} of {len(todo)}…"), unsafe_allow_html=True)
                try:
                    ai_score_live(x)
                except Exception as e:
                    st.error(f"{x['name']}: {e}")
            st.rerun()
    if S.subs and st.button("Clear queue", width="stretch"):
        S.subs, S.cur = [], 0
        st.rerun()
    st.divider()
    st.header("Settings")
    st.radio("AI suggestions", ["Calibrated to AI4ALL grading", "Strict rubric"], key="cal_choice",
             index=0 if S.use_cal else 1, on_change=on_cal)


# ── header (start screen only) ───────────────────────────────────────────
slim = bool(S.subs)
st.markdown("" if slim else f"""
<div class="hero {'slim' if slim else ''}">
  <div>
    <div class="kicker">Strict rubric · Local calibration · Human decision</div>
    <h1>Rubric Auto-fill Reviewer</h1>
    {'' if slim else '<p>AI4ALL Ignite <b>Final Presentation</b> rubric: six criteria, 0–5 each, nomination at 24/30. Upload decks, let the AI fill in evidence-backed scores, then check and confirm every one.</p>'}
  </div>
  <img src="data:image/png;base64,{img64('ai4all_dither_mint.png')}" alt="">
</div>""", unsafe_allow_html=True)

if S.flash:
    kind, msg = S.flash
    (st.success if kind == "success" else st.error)(msg)
    S.flash = None

if not S.subs:
    right = st.container()
    with right:
        s1, s2, s3 = st.columns(3)
        with s1.container(border=True, key="main_upload"):
            st.markdown("<div class='step'><b>01 · Upload</b>Click or drop one or many PDFs, or a .zip of a Drive folder. "
                        "Unredacted decks are OK.</div>", unsafe_allow_html=True)
            up = st.file_uploader("Upload decks", type=["pdf", "zip"], accept_multiple_files=True,
                                  key=f"up_main_{S.up_n}", label_visibility="collapsed")
            if up:
                with st.spinner(f"Reading {len(up)} file(s)…"):
                    ingest_uploads(up)
                S.up_n += 1
                st.rerun()
        with s2.container(border=True):
            st.markdown("<div class='step'><b>02 · Review</b>Slides at the top, the score card below. The AI fills in "
                        "each score; hover a criterion for its rubric, hover the AI score to see why, and click a "
                        "cited slide number to jump to it.</div>", unsafe_allow_html=True)
        with s3.container(border=True):
            st.markdown("<div class='step'><b>03 · Confirm and export</b>Change any score (0 means missing), add "
                        "comments, confirm, and move to the next deck. Then download the gradebook as CSV or JSON."
                        "</div>", unsafe_allow_html=True)
        other = ("In API mode, every other deck is redacted and scored live." if HAS_KEY else
                 "In Free mode, every other deck gets a redacted copy and a ready-made prompt for Claude chat. "
                 "Switch to API mode to score them automatically.")
        if PRE:
            st.info(f"**{len(PRE)} AI4ALL Ignite study decks** have stored AI scores that appear "
                    "instantly, even for an unredacted original. " + other)
        else:
            st.info(other)
    st.stop()


# ── deck header ──────────────────────────────────────────────────────────
S.cur = min(S.cur, len(S.subs) - 1)
sub = S.subs[S.cur]
K = sub["key"]
sug = suggestions(sub)
flags = rt.review_flags(sub["result"], sug) if sub["result"] else {c: [] for c in CRITERIA} | {"deck": []}
def go_rel(d):
    S.cur = max(0, min(len(S.subs) - 1, S.cur + d))


state = ("<span class='pill ok'>Confirmed</span>" if sub["confirmed"] else
         ("<span class='pill'>AI scores ready</span>" if sub["result"] else "<span class='pill none'>Needs AI scores</span>"))
with st.container(key="topbar", horizontal=True, vertical_alignment="center", wrap=False, gap="small"):
    st.button("◀ Previous", key="prevdeck", on_click=go_rel, args=(-1,), disabled=S.cur == 0, width="content")
    st.markdown(f"<div class='deckhead'><span class='dn'>Deck {S.cur + 1} of {len(S.subs)}</span>"
                f"<span class='dname' title='{html.escape(sub['name'])}'>{html.escape(sub['name'])}</span>{state}</div>",
                unsafe_allow_html=True, width="stretch")
    st.button("Next ▶", key="nextdeck", on_click=go_rel, args=(1,), disabled=S.cur >= len(S.subs) - 1, width="content")


# ── "Score with Claude" pop-up (Free mode) ───────────────────────────────
def redaction_summary(s):
    red = get_redaction(s)
    summ = red.summary()
    if not summ:
        return "No names, contact details or faces were found."
    parts = ", ".join(f"{v} {k}{'s' if v > 1 and not k.endswith('s') else ''}" for k, v in summ.items())
    return f"Removed: {parts} (slides {', '.join(str(p) for p in red.pages_hit())})."


@st.dialog("Score with Claude (free)", width="large")
def claude_dialog(k):
    s = by_key(k)
    if S.get("dialog_done"):
        S.dialog_done = False
        st.rerun()
    todo = [x for x in S.subs if not x["result"]]
    scope = st.segmented_control("Score", ["This deck", f"All {len(todo)} unscored decks"], default="This deck",
                                 key="dlg_scope") or "This deck"
    batch = scope != "This deck"
    st.markdown("**1 · Download the redacted copy**" + (" (a .zip)" if batch else ""))
    if batch:
        if st.button(f"Prepare {len(todo)} redacted copies"):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for x in todo:
                    z.writestr(x["alias"], x["data"] if x["pid"] else get_redacted_pdf(x))
            S.batch_zip = buf.getvalue()
        if S.get("batch_zip"):
            st.download_button("⬇ redacted_submissions.zip", S.batch_zip, file_name="redacted_submissions.zip",
                               mime="application/zip", on_click="ignore")
    else:
        if not s["pid"]:
            st.markdown(f"<div class='redact-note'>🛡️ {redaction_summary(s)} Names, contact details and faces are "
                        "blacked out; check with the viewer's <b>Redacted</b> view.</div>", unsafe_allow_html=True)
            extra = st.text_input("Missed a name? Add it (comma-separated)", value=s["red_terms"], key=f"terms_{k}")
            if extra != s["red_terms"]:
                s["red_terms"], s["red"], s["redpdf"] = extra, None, None
                st.rerun(scope="fragment")
        st.download_button(f"⬇ {s['alias']}", s["data"] if s["pid"] else get_redacted_pdf(s), file_name=s["alias"],
                           mime="application/pdf", on_click="ignore")
    st.markdown("**2 · In claude.ai, choose the most capable model, attach it, and paste this prompt**")
    st.code(rt.claude_prompt(batch=batch), language="text", wrap_lines=True, height=160)
    st.markdown("**3 · Paste Claude's reply here, then press Ctrl+Enter**")
    st.text_area("Claude's reply", key=f"paste_{k}", height=110, on_change=cb_paste, args=(k,),
                 label_visibility="collapsed", placeholder='{"scores": [ ... ]}')
    st.button("Load scores", type="primary", on_click=cb_paste, args=(k,))
    if S.flash and S.flash[0] == "error":
        st.error(S.flash[1])
        S.flash = None


def clear_match(k):
    s = by_key(k)
    s["pid"], s["match"], s["result"], s["source"], s["fill"] = None, "no match", None, None, None
    for c in CRITERIA:
        if s["auto"][c]:
            s["scores"][c], s["auto"][c] = None, False


# ── workspace: slide on top, score strip underneath ──────────────────────
# Button tooltips are pure CSS (:hover), not Streamlit's help= popovers. Those popovers live outside the button
# and are orphaned when a click reruns the app and re-renders the button, so several could stay on screen and
# ignore Esc. A CSS bubble exists only while the pointer is over its button, and never takes the pointer itself.
TIPS: dict[str, str] = {}


def hover_tip(key: str, text: str) -> None:
    TIPS[key] = text


def tips_css() -> str:
    def q(t):  # CSS string literal
        return '"' + t.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("<", "\\3C ") + '"'
    rules = [f".st-key-{k} button::after {{ content: {q(t)}; }}" for k, t in TIPS.items()]
    return "<style>" + "\n".join(rules) + "</style>"


def jump_to(k, page_no):
    by_key(k)["page"] = int(page_no) - 1


def step_page(k, d):
    s = by_key(k)
    s["page"] = max(0, s["page"] + d)


def step_zoom(d):
    levels = [100, 150, 200]
    S.zoom = levels[max(0, min(len(levels) - 1, levels.index(S.zoom if S.zoom in levels else 100) + d))]


if not sub["result"] and sub["fill"] != "prefill":
    with st.container(border=True, key="noai"):
        a, b, c = st.columns([4.5, 2, 1.3], vertical_alignment="center")
        a.markdown("**This deck has no AI scores yet.** " + (
            "Score it live with Claude (only a redacted copy is sent)." if HAS_KEY else
            "Score it free in Claude chat with a ready-made prompt, or prefill and grade by hand."))
        if HAS_KEY:
            if b.button("Score with AI now", type="primary", width="stretch"):
                with st.spinner("Redacting, then scoring six criteria…"):
                    try:
                        ai_score_live(sub)
                    except Exception as e:
                        S.flash = ("error", f"Scoring failed: {e}")
                st.rerun()
        elif b.button("Score with Claude (free)…", type="primary", width="stretch"):
            claude_dialog(K)
        hover_tip("prefill5", "Most common historical score. Not an AI judgement.")
        if c.button("Prefill 5s", key="prefill5", width="stretch"):
            for cc in CRITERIA:
                sub["scores"][cc], sub["auto"][cc] = rt.HISTORICAL_MODE[cc], True
            sub["source"], sub["fill"] = "most-common-score prefill (not AI)", "prefill"
            st.rerun()

try:
    if not sub.get("npages"):
        sub["npages"] = pdfsafe.page_count(sub["data"])
    npages = sub["npages"]
    sub["page"] = min(sub["page"], npages - 1)
    with st.container(key="viewbar", horizontal=True, horizontal_alignment="distribute", vertical_alignment="center",
                      wrap=True):
        with st.container(horizontal=True, vertical_alignment="center", wrap=False, width="content", gap="small"):
            hover_tip("pprev", "Previous slide")
            st.button("‹", key="pprev", on_click=step_page, args=(K, -1), disabled=sub["page"] == 0)
            st.markdown(f"<div class='slideno'>Slide {sub['page'] + 1} of {npages}</div>", unsafe_allow_html=True,
                        width="content")
            hover_tip("pnext", "Next slide")
            st.button("›", key="pnext", on_click=step_page, args=(K, 1), disabled=sub["page"] >= npages - 1)
        with st.container(horizontal=True, vertical_alignment="center", wrap=False, width="content", gap="small"):
            st.segmented_control("View", ["Original", "Redacted"], key="view", label_visibility="collapsed")
            hover_tip("zout", "Zoom out")
            st.button("−", key="zout", on_click=step_zoom, args=(-1,), disabled=S.zoom <= 100)
            st.markdown(f"<div class='slideno'>{S.zoom}%</div>", unsafe_allow_html=True, width="content")
            hover_tip("zin", "Zoom in")
            st.button("+", key="zin", on_click=step_zoom, args=(1,), disabled=S.zoom >= 200)
    red_view = S.view == "Redacted"
    red = get_redaction(sub) if red_view else None
    if red_view and S.zoom == 100 and len(red.jpegs) > sub["page"]:
        b64 = base64.b64encode(red.jpegs[sub["page"]]).decode()      # already painted during redaction
    else:
        b64, _ = render_page(K, sub["data"], sub["page"], 1.25 * S.zoom / 100, red_view, sub["red_terms"], _red=red)
    style = "max-width:100%;max-height:50vh;width:auto;" if S.zoom == 100 else f"width:{S.zoom}%;max-width:none;"
    st.markdown(f"<div class='viewer'><img src='data:image/jpeg;base64,{b64}' style='{style}' "
                f"alt='Slide {sub['page'] + 1}'></div>", unsafe_allow_html=True)
    if red_view:
        st.caption("🛡️ Redacted view: this is what Claude sees for a new deck. " + redaction_summary(sub))
except Exception as e:  # unreadable PDF
    st.error(f"This PDF couldn't be displayed ({type(e).__name__}). You can still grade it below.")

# score strip: total + six criteria side by side
strip = st.columns([1.25] + [1] * 6, gap="small")
with strip[0]:
    done = [v for v in sub["scores"].values() if v is not None]
    total = sum(done)
    status = ("meets 24/30" if total >= 24 else "below 24/30") if len(done) == 6 else f"{len(done)} of 6 set"
    src = sub["source"] or "no AI scores yet"
    matched = bool(sub["pid"] and sub["match"] and sub["match"].startswith("content"))
    st.markdown(f"""<div class="total"><div class="l">Total</div><div class="n">{total}<span>/30</span></div></div>""",
                unsafe_allow_html=True)
    if matched:
        st.button("Not this deck?", key=f"unmatch_{K}", on_click=clear_match, args=(K,), type="tertiary")
for i, c in enumerate(CRITERIA):
    cr, lv = criterion(c), criterion(c)["levels"]
    item = (sub["result"] or {}).get("items", {}).get(c) or {}
    s_ = sug.get(c)
    side_cls = "right" if i >= 3 else ""
    levels = "".join(f"<b>{k}</b> {lv[k]}<br>" for k in ["5", "4", "3", "2", "1"]) + "<b>0</b> missing or not submitted"
    with strip[i + 1].container(border=True, key=f"crit_{c}"):
        st.markdown(f"<div class='tip cname'><span class='tname'>{cr['name']}</span><div class='tipbox {side_cls}'>{levels}</div></div>",
                    unsafe_allow_html=True)
        if item:
            why = html.escape(item.get("rationale", "")) or "No rationale given."
            lit = rt.ai_score(item)
            if lit is not None and S.use_cal and lit != s_:
                why = f"<i>Strict rubric {lit} → calibrated {s_}.</i><br>" + why
            for f in flags.get(c, []):
                why += f"<br><span class='tflag'>⚑ {html.escape(f)}</span>"
            label = f"AI {s_}" if s_ is not None else "AI: no score"
            st.markdown(f"<div class='tip'><span class='pill {'' if s_ is not None else 'none'}'>{label}<span class='iicon'>i</span></span>"
                        f"<div class='tipbox {side_cls}'><b>Why the AI chose this</b><br>{why}</div></div>",
                        unsafe_allow_html=True)
        v = sub["scores"][c]
        bind(f"score_{K}_{c}", "—" if v is None else v)
        st.selectbox("Your score", OPTS, key=f"score_{K}_{c}", on_change=cb_score, args=(K, c),
                     label_visibility="collapsed",
                     format_func=lambda x: "— set —" if x == "—" else ("0 · missing" if x == 0 else str(x)))
        notes: dict[int, list[str]] = {}
        for e in item.get("evidence", []):
            obs = e["observation"].strip()
            if obs and obs not in notes.setdefault(int(e["page"]), []):
                notes[int(e["page"])].append(obs)
        if notes:
            st.markdown("<div class='citelabel'>Cited slides</div>", unsafe_allow_html=True)
            with st.container(key=f"cites_{c}", horizontal=True, wrap=True, gap="small"):
                for pg in sorted(notes):
                    hover_tip(f"cite_{K}_{c}_{pg}", f"Slide {pg}: " + " · ".join(notes[pg]))
                    st.button(str(pg), key=f"cite_{K}_{c}_{pg}", on_click=jump_to, args=(K, pg),
                              type="primary" if sub["page"] + 1 == pg else "secondary")

st.html(tips_css())
if flags["deck"]:
    st.markdown("".join(f"<span class='flag'>⚑ {html.escape(f)}</span>" for f in flags["deck"]), unsafe_allow_html=True)
bind(f"comments_{K}", sub["comments"])
st.text_area("Instructor comments", key=f"comments_{K}", height=68, on_change=cb_text, args=(K, "comments"),
             placeholder="Feedback for the team")
f1, f2, f3 = st.columns([1.2, 2, 3.3], vertical_alignment="bottom")
bind(f"reviewer_{K}", sub["reviewer"] or S.get("last_reviewer", ""))
sub["reviewer"] = S[f"reviewer_{K}"]
f1.text_input("Your initials", key=f"reviewer_{K}", on_change=cb_text, args=(K, "reviewer"),
              placeholder="Your initials")
if f2.button("Confirm and next ▶" if not sub["confirmed"] else "Re-confirm and next ▶", type="primary",
             width="stretch", key="confirm"):
    missing = [criterion(c)["name"] for c in CRITERIA if sub["scores"][c] is None]
    if missing:
        f3.warning("Set a score for: " + ", ".join(missing))
    elif not sub["reviewer"].strip():
        f3.warning("Add your initials first.")
    elif any(sub["auto"].values()) and not S.skip_warn:
        review_warning(K)
    else:
        do_confirm(sub)
        st.rerun()
if sub["confirmed"]:
    f3.markdown(f"<span class='pill ok'>Confirmed by {html.escape(sub['confirmed']['reviewer'])} · "
                f"{sub['confirmed']['human_total']}/30</span>", unsafe_allow_html=True)
st.markdown("<div style='height:2.2rem'></div>", unsafe_allow_html=True)
if sub["result"] and not HAS_KEY:
    if st.button("Replace these AI scores with a Claude reply…", type="tertiary", key=f"repl_{K}"):
        claude_dialog(K)


# ── gradebook ────────────────────────────────────────────────────────────
with st.expander(f"Gradebook and export · {sum(1 for s in S.subs if s['confirmed'])} of {len(S.subs)} confirmed"):
    head = "".join(f"<th>{h}</th>" for h in ["#", "Deck", "AI source"] + [criterion(c)["name"] for c in CRITERIA]
                   + ["Total", "Status"])
    body = ""
    for i, s in enumerate(S.subs):
        sc = s["scores"]
        cells = [str(i + 1), html.escape(s["name"]), html.escape(s["source"] or "—")]
        cells += ["—" if sc[c] is None else str(sc[c]) for c in CRITERIA]
        cells += [str(sum(v for v in sc.values() if v is not None)), "confirmed" if s["confirmed"] else "in progress"]
        body += "<tr>" + "".join(f"<td>{x}</td>" for x in cells) + "</tr>"
    st.markdown(f"<div class='gbwrap'><table class='gb'><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>",
                unsafe_allow_html=True)
    conf = [s["confirmed"] for s in S.subs if s["confirmed"]]
    if conf:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["deck", "reviewer", "total", "comments", "ai_source", "criterion", "ai_literal", "ai_suggested",
                    "human_final", "overridden", "auto_filled_unchanged"])
        for rec in conf:
            for r in rec["criteria"]:
                w.writerow([rec["deck"], rec["reviewer"], rec["human_total"], rec["notes"], rec.get("ai_source"),
                            r["criterion"], r["ai_literal"], r["ai_suggested"], r["human_final"], r["overridden"],
                            r["criterion"] in rec.get("auto_filled_unchanged", [])])
        d1, d2, _ = st.columns([1, 1, 3])
        d1.download_button(f"Download {len(conf)} confirmed (CSV)", buf.getvalue(), "gradebook.csv", "text/csv",
                           width="stretch")
        d2.download_button("Download (JSON)", json.dumps(conf, indent=2), "gradebook.json", "application/json",
                           width="stretch")
    st.caption("Grades live only in this browser session. Download before closing the tab.")

with st.expander("About the method, privacy and validation"):
    st.markdown("""
**Three stages.** (1) A strict rubric scorer: page-cited evidence, abstaining when content isn't observable. (2) An optional
calibration layer fitted to how AI4ALL instructors graded. (3) Evaluation on a locked 84-deck test set.

**Results.** The strict scorer is harsher than instructors (Essential Question −1.24). Calibration cut error by 0.24 points
per criterion and removed the total-score bias. Calibrated error is ≈0.53 per criterion, about the same as "always give 5", so
this is **reviewed pre-fill, not autograding**. Turn calibration off to see differences between projects more sharply.

**Redaction.** Before a new deck goes to Claude, this app finds people's names (a language model plus cue words such as
"Presented by"), emails, phone numbers, handles, profile links and faces, paints them out, and sends an image-only copy with
no text layer or metadata, plus the redacted text. Citation authors are kept. A final check blocks the request if a removed
name is still in the text. It is best effort: check the *Redacted* view.

**Stored scores** come from the study's text-only scorer, so Data Visualization is often left for you: the scorer couldn't see the charts.
""")

st.markdown(f"""
<div class="footer">
  <div><img src="data:image/png;base64,{img64('ai4all_mark.png')}" alt="AI4ALL">AI4ALL · built by Jonathan D. Doane · Rubric: <a href="{RUBRIC_URL}" target="_blank" style="margin-left:0">AI4ALL Ignite Rubrics ↗</a> · build {BUILD}</div>
  <div><a href="https://ai-4-all.org" target="_blank">AI4ALL ↗</a></div>
</div>""", unsafe_allow_html=True)

# A queued deck without stored scores will need redaction: load the models now, after this page is drawn,
# so the first redaction is quick and the upload itself is never slowed down.
if any(not s["result"] for s in S.subs):
    warm_models()
