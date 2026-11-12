"""Build the synthetic decks the browser tests use (made-up names; public-domain NASA photo from scikit-image).

    python tests/e2e/make_fixtures.py <out_dir>

The suite also needs "Original Unredacted Version.pdf": a study deck's text with fake names added, to test
content matching. It is built from a private deck text, so it is never committed: make it locally
(see tests/e2e/README.md).
"""
import io
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from rubric_scoring.rubric import CRITERIA  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "e2e_fixtures")
out.mkdir(parents=True, exist_ok=True)
try:
    from skimage import data
    face = Image.fromarray(data.astronaut())
except Exception:
    face = Image.new("RGB", (512, 512), (200, 160, 140))  # no face: face checks will not apply
face.save(out / "face.png")


def deck(path, slides, img=None, chart_on=None):
    c = canvas.Canvas(str(path), pagesize=(960, 540))
    c.setAuthor("Maria Gonzalez")
    for k, lines in enumerate(slides):
        y = 480
        for i, ln in enumerate(lines):
            c.setFont("Helvetica-Bold" if i == 0 else "Helvetica", 30 if i == 0 else 20)
            c.drawString(60, y, ln)
            y -= 44
        if img and k == 1:
            c.drawImage(ImageReader(img), 600, 120, 260, 260)
        if chart_on == k:
            for j, v in enumerate([120, 200, 160, 260]):
                c.rect(560 + j * 70, 100, 50, v, fill=1)
        c.showPage()
    c.save()


deck(out / "Fake_Unredacted_Deck.pdf", [
    ["Predicting Crop Yields with Machine Learning", "Presented by Maria Gonzalez, Wei Chen & DeShawn Jackson",
     "Contact: maria.g@example.com  |  (555) 123-4567"],
    ["Meet the Team", "Maria Gonzalez - data cleaning", "Wei Chen - modeling", "DeShawn Jackson - slides",
     "linkedin.com/in/wei-chen-demo   @deshawn_codes"],
    ["Project Description", "Research question: can weather data predict corn yield?",
     "Maria tuned the random forest model; we changed from linear regression."],
    ["Results", "Random forest R^2 = 0.81 on held-out counties", "Feature importance chart at right"],
    ["References", "Smith, J. et al. (2020). Crop models. Nature Food."]], img=out / "face.png", chart_on=3)
deck(out / "Unmatched Example.pdf", [["Unmatched example deck", "slide 1"], ["Slide 2"], ["Slide 3"]])
deck(out / "Synthetic Test Deck.pdf", [["Synthetic test deck", "slide 1"], ["Slide 2"]])

rng = np.random.default_rng(0)
c = canvas.Canvas(str(out / "Heavy Deck.pdf"), pagesize=(960, 540))
for i in range(17):
    noise = Image.fromarray((rng.random((900, 1600, 3)) * 255).astype("uint8"))
    bg = Image.blend(noise, face.resize((1600, 900)), 0.6)
    b = io.BytesIO()
    bg.save(b, "JPEG", quality=92)
    c.drawImage(ImageReader(io.BytesIO(b.getvalue())), 0, 0, 960, 540)
    c.drawImage(ImageReader(face), 600, 150, 250, 250)
    c.setFont("Helvetica-Bold", 28)
    c.drawString(40, 480, f"Slide {i + 1}: Deepfake detection with CNNs")
    c.setFont("Helvetica", 16)
    c.drawString(40, 440, "Presented by Maria Gonzalez and Wei Chen" if i == 0 else "Accuracy, precision and recall")
    c.showPage()
c.save()

with zipfile.ZipFile(out / "two_decks.zip", "w") as z:
    z.write(out / "Unmatched Example.pdf", "Unmatched Example.pdf")
    z.write(out / "Synthetic Test Deck.pdf", "Synthetic Test Deck.pdf")

items = [{"criterion": c, "score": "5" if c != "citations" else "4", "abstention_reason": "none",
          "rationale": "Test rationale for " + c,
          "evidence": [{"page": 3, "observation": "Research question stated clearly on this slide"},
                       {"page": 3, "observation": "Research question stated clearly on this slide"},
                       {"page": 4, "observation": "Chart of feature importance"}],
          "checklist": [], "counted_items": 0, "limiting_factors": [], "extraction_issues": []} for c in CRITERIA]
(out / "reply.json").write_text("Here is the scoring:\n```json\n" + json.dumps({"scores": items}) + "\n```")
print("fixtures written to", out)
