"""Thread-safe access to PDFium.

PDFium is not thread-safe: two threads must never call it at the same time, not even on different
documents. Streamlit runs every browser session in its own thread, so two users (or two tabs) rendering
slides at once could hang or crash the app. Every PDFium call in this project therefore goes through
PDF_LOCK, and every PDFium object is closed explicitly while the lock is held (otherwise Python's garbage
collector could close it later from another thread).
"""
from __future__ import annotations

import sys
import threading

import pypdfium2 as pdfium
from PIL import Image

# One lock per process, kept on the sys module so it survives the app reloading this module after a code
# update: old and new code running side by side during an update must still take turns.
if not hasattr(sys, "_rubric_scoring_pdf_lock"):
    sys._rubric_scoring_pdf_lock = threading.RLock()
PDF_LOCK = sys._rubric_scoring_pdf_lock


def page_count(data: bytes) -> int:
    with PDF_LOCK:
        doc = pdfium.PdfDocument(data)
        try:
            return len(doc)
        finally:
            doc.close()


def render_rgb(doc: "pdfium.PdfDocument", index: int, scale: float) -> Image.Image:
    """Render one page of an open document to an independent RGB image. Caller must hold PDF_LOCK."""
    page = doc[index]
    bitmap = page.render(scale=scale)
    img = bitmap.to_pil().convert("RGB")     # convert() copies, so the bitmap can be freed now
    bitmap.close()
    page.close()
    return img


def render_page(data: bytes, index: int, scale: float) -> Image.Image:
    with PDF_LOCK:
        doc = pdfium.PdfDocument(data)
        try:
            return render_rgb(doc, min(index, len(doc) - 1), scale)
        finally:
            doc.close()


def page_texts(data: bytes) -> list[str]:
    with PDF_LOCK:
        doc = pdfium.PdfDocument(data)
        try:
            out = []
            for i in range(len(doc)):
                page = doc[i]
                tp = page.get_textpage()
                out.append(tp.get_text_range())
                tp.close()
                page.close()
            return out
        finally:
            doc.close()
