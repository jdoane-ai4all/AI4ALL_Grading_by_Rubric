"""Local redaction of personal information in a slide deck, done BEFORE anything is sent to an AI.

What is removed (best effort, so a person should check the redacted view):
  * people's names: spaCy named-entity recognition, plus names after cue words such as
    "Presented by", "Team members" or "Mentor", plus any names the reviewer types in.
    A name found once is removed everywhere else in the deck too.
  * email addresses, phone numbers, @handles and social-profile / GitHub links
  * faces, using OpenCV's YuNet detector, and every photo on a page that lists team names
    (headshot slides)

Output is an image-only PDF: each page is rendered, the boxes are painted black, and the text
layer and document metadata are dropped. A redacted, page-marked text copy is produced too.
Citation authors ("Smith et al.") and names on a References page are kept, because Citations is scored.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from PIL import Image, ImageDraw

import threading

from .pdfsafe import PDF_LOCK, render_rgb

FACE_MODEL = Path(__file__).resolve().parents[2] / "app" / "models" / "face_detection_yunet_2023mar.onnx"

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]\d{4}(?!\d)")
HANDLE = re.compile(r"(?<![\w@.])@[A-Za-z0-9_.]{3,30}")
PROFILE = re.compile(r"(?:https?://)?(?:www\.)?(?:linkedin\.com|github\.com|instagram\.com|twitter\.com|x\.com|"
                     r"tiktok\.com|facebook\.com|youtube\.com/@)[^\s,;)]*", re.I)
CUE = re.compile(r"(?:presented by|created by|made by|prepared by|team members?|group members?|our team|meet the team|"
                 r"members|authors?|names?|students?|contributors?|mentors?|instructors?|teaching assistants?|"
                 r"\bTAs?\b|\b(?:group|team)\s*[\w\-]{0,4}\s*:|\bby)\s*[:\-–—]?\s*(.*)", re.I)
SEPARATORS = r",|&|/|\||;|\band\b|·|•"
REFERENCES_PAGE = re.compile(r"^\W*(references|works cited|bibliography|citations|sources)\b", re.I | re.M)
TECH = {"machine", "learning", "deep", "neural", "network", "regression", "forest", "random", "tree", "trees", "data",
        "model", "models", "analysis", "prediction", "predicting", "classifier", "classification", "vision", "language",
        "processing", "intelligence", "artificial", "presented", "research", "question", "results", "project", "slides",
        "dataset", "accuracy", "training", "testing", "feature", "features", "chart", "graph", "figure", "table"}
NOT_NAMES = {"Data", "Model", "Models", "Results", "Introduction", "Conclusion", "Next Steps", "Thank You", "Questions",
             "Project", "Algorithm", "Dataset", "Python", "Google", "Colab", "Kaggle", "Team", "Group", "AI", "ML",
             "AI4ALL", "Ignite", "Random Forest", "Linear Regression", "Logistic Regression", "Neural Network"}


@dataclass
class Redaction:
    n_pages: int
    page_size: list[tuple[float, float]]                     # (width, height) in PDF points
    boxes: dict[int, list[tuple[float, float, float, float]]] = field(default_factory=dict)  # top-left origin, points
    page_text: list[str] = field(default_factory=list)       # redacted text per page
    found: list[dict] = field(default_factory=list)          # {"page", "kind"} only: no values kept for display
    terms: list[str] = field(default_factory=list)           # removed strings, used only for the leak guard
    jpegs: list[bytes] = field(default_factory=list)         # each page rendered once, boxes painted, as JPEG
    jpeg_scale: float = 1.25

    def summary(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in self.found:
            out[f["kind"]] = out.get(f["kind"], 0) + 1
        return out

    def pages_hit(self) -> list[int]:
        return sorted({f["page"] for f in self.found})

    def text(self) -> str:
        return "\n\n".join(f"[Page {i + 1}]\n{t}" for i, t in enumerate(self.page_text))


_NLP = None
_NLP_FAILED = False
_LOAD_LOCK = threading.Lock()     # load each model once, even if two sessions ask at the same moment
NLP_LOCK = threading.Lock()       # spaCy pipelines are not guaranteed thread-safe
DET_LOCK = threading.Lock()       # an OpenCV DNN detector must not be used by two threads at once


def _nlp():
    global _NLP, _NLP_FAILED
    if _NLP is not None or _NLP_FAILED:
        return _NLP
    with _LOAD_LOCK:
        if _NLP is not None or _NLP_FAILED:
            return _NLP
        try:
            import spacy
            # only the named-entity recogniser is needed: excluding the rest saves memory and CPU
            _NLP = spacy.load("en_core_web_sm", exclude=["parser", "tagger", "attribute_ruler", "lemmatizer",
                                                          "senter"])
        except Exception:
            _NLP_FAILED = True
    return _NLP


def ner_available() -> bool:
    return _nlp() is not None


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\r", " ")).strip(" ,.;:-–—|&/")


def _nameish(part: str) -> bool:
    """1-5 capitalised words in any alphabet (accents, apostrophes and hyphens allowed), not a known non-name."""
    p = _clean(part)
    words = p.split()
    if not (1 <= len(words) <= 5) or len(p) > 60 or p in NOT_NAMES:
        return False
    for w in words:
        core = w.strip(".")
        # "■" / "\ufffd": a letter the PDF's font could not map to text (common for accented names)
        if not core or not (core[0].isupper() or core[0] in "■\ufffd") or \
                not all(ch.isalpha() or ch in "'’-.■\ufffd" for ch in core):
            return False
        if core.lower() in TECH or core in NOT_NAMES:
            return False
    return True


def _parts(text: str) -> list[str]:
    return [_clean(x) for x in re.split(SEPARATORS, text) if _clean(x)]


def _looks_like_names(line: str) -> bool:
    parts = _parts(line)
    return bool(parts) and all(_nameish(x) for x in parts)


def _cue_names(text: str, title_page: bool = False) -> list[str]:
    """Names after cue words ("Presented by", "Group 3C:", "Team members:" ...), following the list onto the
    next lines and rejoining a name that wraps mid-name ("... Thandeka" / "Nkosi, ..."). On title pages, a
    comma-separated list of name-like phrases counts even without a cue."""
    lines = [ln.strip() for ln in text.splitlines()]
    out: list[str] = []
    i = 0
    while i < len(lines):
        m = CUE.search(lines[i])
        listy = title_page and lines[i].count(",") + lines[i].count("&") >= 1 and _looks_like_names(lines[i]) \
            and sum(len(x.split()) >= 2 for x in _parts(lines[i])) >= 2
        if not m and not listy:
            i += 1
            continue
        strong = bool(listy) or not re.match(r"by\b", m.group(0).strip(), re.I)
        buf = lines[i] if listy and not m else m.group(1).strip()
        prev = buf                              # the previous line as written on the slide
        j = i + 1
        while j < len(lines) and lines[j]:
            nxt = lines[j]
            open_end = prev == "" or bool(re.search(r"(,|&|\band)\s*$", prev, re.I))
            if not (open_end or (strong and _looks_like_names(nxt))):
                break
            if open_end:
                buf = f"{buf} {nxt}".strip()
            elif "," in prev or "&" in prev:    # a list line that wrapped mid-name ("... Thandeka" / "Nkosi, ...")
                buf = f"{buf} {nxt}"
            else:                               # one name per line
                buf = f"{buf}, {nxt}"
            prev = nxt
            j += 1
        out += [x for x in _parts(buf) if _nameish(x)]
        i = j
    return out


def _ner_names(text: str) -> list[str]:
    """PERSON entities, found line by line (slide lines are independent fragments)."""
    nlp = _nlp()
    if nlp is None:
        return []
    lines = [ln for ln in text.splitlines() if re.search(r"[A-Z]", ln)]
    out = []
    with NLP_LOCK:
        docs = list(nlp.pipe(lines))
    for ln, doc in zip(lines, docs):
        for e in doc.ents:
            if e.label_ != "PERSON":
                continue
            name = _clean(re.split(r"\s[-–—:(]\s?", e.text)[0])
            after = ln[e.end_char:e.end_char + 10].lower()
            words = name.split()
            if (len(name) < 3 or not re.search(r"[A-Za-z]", name) or name in NOT_NAMES or "et al" in after
                    or name.islower() or len(name) > 40 or any(w in NOT_NAMES or w.lower() in TECH for w in words)):
                continue
            out.append(name)
    return out


def _page_text(tp) -> str:
    return tp.get_text_range().replace("\r\n", "\n").replace("\r", "\n")


def _term_rects(tp, term: str, page_h: float, whole_word: bool = True):
    rects, hits = [], 0
    searcher = tp.search(term, match_case=False, match_whole_word=whole_word)
    while (hit := searcher.get_next()) is not None:
        idx, cnt = hit
        hits += 1
        for i in range(tp.count_rects(idx, cnt)):
            l, b, r, t = tp.get_rect(i)
            rects.append((l - 1.5, page_h - t - 1.5, r + 1.5, page_h - b + 1.5))
    searcher.close()
    return rects, hits


def _faces(img: Image.Image, px_per_pt: float, detector) -> list[tuple[float, float, float, float]]:
    """Faces in a rendered page image. Scans at two sizes, because the detector misses faces that fill much of
    a full-size slide. Boxes are returned in PDF points."""
    import numpy as np
    out = []
    base = 1.0 / px_per_pt                               # scan at about 1 pixel per point (960 px wide slide)
    scan = img.resize((max(1, int(img.width * base)), max(1, int(img.height * base))), Image.Resampling.BILINEAR)
    for factor, src in ((base, scan), (base * 0.35, None)):
        small = src.copy() if src is not None else scan.resize(
            (max(1, int(scan.width * 0.35)), max(1, int(scan.height * 0.35))), Image.Resampling.BILINEAR)
        arr = np.ascontiguousarray(np.array(small)[:, :, ::-1])  # BGR
        small.close()
        with DET_LOCK:
            detector.setInputSize((arr.shape[1], arr.shape[0]))
            _, faces = detector.detect(arr)
        for f in faces if faces is not None else []:
            x, y, w, h = (float(v) / (px_per_pt * factor) for v in f[:4])
            box = (x - 0.35 * w, y - 0.55 * h, x + 1.35 * w, y + 1.3 * h)  # include hair and chin
            if not any(_overlap(box, o) > 0.5 for o in out):
                out.append(box)
    scan.close()
    return out


def _overlap(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return inter / small if small > 0 else 0.0


def _photos(page, page_h: float, page_area: float):
    out = []
    for obj in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE], max_depth=3):
        l, b, r, t = obj.get_bounds()
        if (r - l) * (t - b) < 0.5 * page_area:  # skip full-slide backgrounds
            out.append((l, page_h - t, r, page_h - b))
    return out


_DETECTOR = None


def _face_detector():
    global _DETECTOR
    if _DETECTOR is None:
        with _LOAD_LOCK:
            if _DETECTOR is None:
                try:
                    import cv2
                    _DETECTOR = cv2.FaceDetectorYN.create(str(FACE_MODEL), "", (320, 320), 0.75, 0.3, 50)
                except Exception:
                    return None
    return _DETECTOR


def analyse(pdf_bytes: bytes, extra_terms: list[str] | tuple = (), faces: bool = True, progress=None,
            scale: float = 1.25, quality: int = 82) -> Redaction:
    """Find and paint out personal information. Each page is rendered once; progress(done, total) is optional."""
    with PDF_LOCK:
        pdf = pdfium.PdfDocument(pdf_bytes)
        n = len(pdf)
        sizes, texts = [], []
        for i in range(n):
            pg = pdf[i]
            sizes.append(pg.get_size())
            tp = pg.get_textpage()
            texts.append(_page_text(tp))
            tp.close()
            pg.close()
    red = Redaction(n_pages=n, page_size=sizes)
    full = "\n".join(texts)

    # 1. collect names / identifiers per page
    user = {t.strip() for t in extra_terms if t and len(t.strip()) >= 2}
    names: set[str] = set(user)
    trusted: set[str] = set(user)          # names whose single words may be removed deck-wide
    pattern_hits: list[tuple[int, str, str]] = []
    team_pages: set[int] = set()
    for i, t in enumerate(texts):
        refs = bool(REFERENCES_PAGE.search(t[:300]))
        cue = set(_cue_names(t, title_page=i < 2)) if not refs else set()
        ner = set(_ner_names(t)) if not refs else set()
        if cue or len(ner) >= 2:
            team_pages.add(i)
            trusted |= cue | ner
        names |= cue | ner
        for kind, rx in (("email", EMAIL), ("phone", PHONE), ("profile link", PROFILE), ("handle", HANDLE)):
            for m in rx.finditer(t):
                pattern_hits.append((i, kind, m.group(0).rstrip(".")))
    # a single word of a trusted name is removed everywhere if it never appears in lower case in the deck
    singles = set()
    for nm in trusted:
        for w in re.findall(r"[A-Za-z][A-Za-z'’\-]{2,}", nm):
            if (w not in NOT_NAMES and w.lower() not in TECH and w.lower() not in {"dr", "mr", "ms", "mrs", "prof"}
                    and not re.search(rf"\b{re.escape(w.lower())}\b", full)):
                singles.add(w)
    terms = sorted(names | singles, key=len, reverse=True)
    red.terms = sorted(set(terms) | {h[2] for h in pattern_hits})

    detector = _face_detector() if faces else None
    red.jpeg_scale = scale
    for i in range(n):
        if progress:
            progress(i, n)
        w, h = sizes[i]
        boxes = []
        txt = texts[i]
        with PDF_LOCK:                      # every PDFium call for this page, then release for other users
            img = render_rgb(pdf, i, scale)
            page = pdf[i]
            tp = page.get_textpage()
            for (pg, kind, val) in [p for p in pattern_hits if p[0] == i]:
                rects, _ = _term_rects(tp, val, h, whole_word=False)
                boxes += rects
                red.found.append({"page": i + 1, "kind": kind})
                txt = txt.replace(val, f"[{kind}]")
            for term in terms:
                rects, hits = _term_rects(tp, term, h)
                boxes += rects
            photo_boxes = _photos(page, h, w * h) if i in team_pages else []
            tp.close()
            page.close()
        for term in terms:
            txt, k = re.subn(rf"(?<!\w){re.escape(term)}(?!\w)", "[name]", txt, flags=re.I)
            red.found += [{"page": i + 1, "kind": "name"}] * k
        if detector is not None:
            fb = _faces(img, scale, detector)
            boxes += fb
            red.found += [{"page": i + 1, "kind": "face"}] * len(fb)
        if photo_boxes:
            boxes += photo_boxes
            red.found += [{"page": i + 1, "kind": "photo"}] * len(photo_boxes)
        red.boxes[i] = boxes
        red.page_text.append(txt)
        _paint(img, boxes, scale)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        img.close()
        red.jpegs.append(buf.getvalue())
    with PDF_LOCK:
        pdf.close()
    if progress:
        progress(n, n)
    release_memory()
    return red


def _paint(img: Image.Image, boxes, scale: float, outline: bool = False) -> None:
    d = ImageDraw.Draw(img)
    for (x0, y0, x1, y1) in boxes:
        box = [max(0, x0 * scale), max(0, y0 * scale), x1 * scale, y1 * scale]
        d.rectangle(box, fill=None if outline else (17, 17, 17), outline=(232, 115, 42) if outline else None,
                    width=3 if outline else 0)


def render_redacted(pdf_bytes: bytes, red: Redaction | None, page: int, scale: float, outline: bool = False) -> Image.Image:
    """One page as an image with redaction boxes painted (outline=True draws them in orange for checking)."""
    from .pdfsafe import render_page
    img = render_page(pdf_bytes, page, scale)
    if red:
        _paint(img, red.boxes.get(page, []), scale, outline)
    return img


def release_memory():
    """Hand freed memory back to the OS (glibc keeps it otherwise), so a small host isn't pushed over its limit."""
    import ctypes
    import gc
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


def redacted_pdf(pdf_bytes: bytes, red: Redaction, scale: float = 1.25, quality: int = 82) -> bytes:
    """Image-only PDF with no text layer and no metadata, assembled from the pages analyse() already painted."""
    pages = []
    for i in range(red.n_pages):
        if i < len(red.jpegs):
            pages.append(red.jpegs[i])
        else:                                    # Redaction built elsewhere without page images
            img = render_redacted(pdf_bytes, red, i, scale)
            b = io.BytesIO()
            img.save(b, format="JPEG", quality=quality)
            img.close()
            pages.append(b.getvalue())
    with PDF_LOCK:
        data = _assemble(red, pages)
    release_memory()
    return data


def _assemble(red: Redaction, pages: list[bytes]) -> bytes:
    """Caller holds PDF_LOCK."""
    out = pdfium.PdfDocument.new()
    keep = []                                   # JPEG buffers must stay alive until the document is saved
    for i, data in enumerate(pages):
        buf = io.BytesIO(data)
        keep.append(buf)
        w, h = red.page_size[i]
        page = out.new_page(w, h)
        pim = pdfium.PdfImage.new(out)
        pim.load_jpeg(buf, inline=False, autoclose=False)
        pim.set_matrix(pdfium.PdfMatrix().scale(w, h))
        page.insert_obj(pim)
        page.gen_content()
        page.close()
    res = io.BytesIO()
    out.save(res)
    out.close()
    return res.getvalue()


def leaks(text: str, red: Redaction) -> list[str]:
    """Removed terms that still appear in text about to be sent (should always be empty)."""
    return [t for t in red.terms if re.search(rf"(?<!\w){re.escape(t)}(?!\w)", text, re.I)]
