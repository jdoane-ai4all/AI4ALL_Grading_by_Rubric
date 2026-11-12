"""Redaction runs on a synthetic deck with made-up names (no real participant data)."""
import io

import pytest

reportlab = pytest.importorskip("reportlab")
from reportlab.pdfgen import canvas  # noqa: E402

from rubric_scoring import redact as R  # noqa: E402


def _deck() -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(960, 540))
    c.setAuthor("Testy Person")
    for lines in (["Predicting Crop Yields with Machine Learning", "Presented by Maria Gonzalez, Wei Chen & DeShawn Jackson",
                   "Contact: maria.g@example.com | (555) 123-4567"],
                  ["Project Description", "Maria tuned the random forest model."],
                  ["References", "Smith, J. et al. (2020). Crop models. Nature Food."]):
        y = 480
        for ln in lines:
            c.setFont("Helvetica", 20)
            c.drawString(60, y, ln)
            y -= 44
        c.showPage()
    c.save()
    return buf.getvalue()


def test_names_contacts_removed_and_content_kept():
    red = R.analyse(_deck(), faces=False)
    text = red.text()
    for pii in ["Maria", "Gonzalez", "Wei Chen", "DeShawn", "Jackson", "maria.g@example.com", "555"]:
        assert pii not in text
    for kept in ["Machine Learning", "random forest", "Smith, J. et al.", "Project Description"]:
        assert kept in text
    assert R.leaks(text, red) == []
    assert red.summary()["email"] == 1 and red.summary()["phone"] == 1
    assert red.boxes[0] and red.boxes[1]          # name on slide 2 is also blacked out


def test_reviewer_terms_and_image_only_output():
    import pypdfium2 as pdfium
    red = R.analyse(_deck(), extra_terms=["Crop Yields"], faces=False)
    assert "Crop Yields" not in red.page_text[0]
    out = pdfium.PdfDocument(R.redacted_pdf(_deck(), red, scale=1.0))
    assert len(out) == 3
    assert out[0].get_textpage().get_text_range().strip() == ""   # no text layer
    assert "Testy" not in str(out.get_metadata_dict())             # no metadata carried over


def test_leak_guard_blocks_request():
    from rubric_scoring import review_tool as rt
    red = R.analyse(_deck(), faces=False)

    class NeverCalled:
        class messages:  # noqa: N801
            @staticmethod
            def create(**_):
                raise AssertionError("request should have been blocked")

    with pytest.raises(RuntimeError, match="Redaction check failed"):
        rt.score_deck(NeverCalled, R.redacted_pdf(_deck(), red, scale=1.0), "submission-001.pdf",
                      extra_text="Maria Gonzalez did the model", guard=lambda t: R.leaks(t, red))


def test_concurrent_use_is_safe():
    """PDFium is not thread-safe; Streamlit runs sessions in threads. Without pdfsafe.PDF_LOCK this crashes
    the whole process (segfault) within a few rounds."""
    import threading
    from rubric_scoring import pdfsafe, review_tool as rt
    deck = _deck()
    expected = str(R.analyse(deck, faces=False).summary())
    errors, results = [], []

    def worker():
        try:
            for _ in range(4):
                red = R.analyse(deck, faces=False)
                R.redacted_pdf(deck, red, scale=1.0)
                pdfsafe.render_page(deck, 1, 1.0)
                rt.pdf_text(deck)
                results.append(str(red.summary()))
        except Exception as e:  # pragma: no cover - only on failure
            errors.append(repr(e))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    assert not any(t.is_alive() for t in threads) and not errors
    assert len(results) == 32 and set(results) == {expected}


def _pdf(pages: list[list[str]]) -> bytes:
    """Unicode font when available (as real decks embed), else Helvetica (accented letters become "■")."""
    from pathlib import Path
    font = "Helvetica"
    ttf = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    if ttf.exists():
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        pdfmetrics.registerFont(TTFont("DejaVu", str(ttf)))
        font = "DejaVu"
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(960, 540))
    for lines in pages:
        y = 480
        for ln in lines:
            c.setFont(font, 20)
            c.drawString(60, y, ln)
            y -= 30
        c.showPage()
    c.save()
    return buf.getvalue()


def test_diverse_names_split_across_lines():
    """Made-up names in the layout real title slides use: a group cue, names wrapped mid-name across lines."""
    deck = _pdf([
        ["DEEPFAKE", "FINAL PROJECT", "", "Group 4B: Amara Okafor, Thandeka", "Nkosi, Luis Ortega Villanueva,",
         "Keisha Brown, Farah Siddiqui"],
        ["Team members:", "Oluwaseun Adeyemi", "Nguyễn Thị Lan", "Aiyana Redcloud"],
        ["By Xochitl Hernández & Tavita Faleolo"],
        ["Results", "Our CNN detects deepfakes with 91% accuracy.", "Amara tuned the learning rate."],
        ["References", "Rossler, A. et al. (2019). FaceForensics++. ICCV."],
    ])
    red = R.analyse(deck, faces=False)
    text = red.text()
    for name in ["Amara", "Okafor", "Thandeka", "Nkosi", "Luis", "Ortega", "Villanueva", "Keisha", "Brown",
                 "Farah", "Siddiqui", "Oluwaseun", "Adeyemi", "Nguyễn", "Lan", "Aiyana", "Redcloud", "Xochitl",
                 "Hernández", "Tavita", "Faleolo"]:
        assert name not in text, name
    for kept in ["DEEPFAKE", "FINAL PROJECT", "Group 4B", "Team members", "Our CNN detects deepfakes",
                 "learning rate", "Rossler, A. et al.", "FaceForensics++"]:
        assert kept in text, kept
