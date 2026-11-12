import json
from types import SimpleNamespace

import pytest

from rubric_scoring import review_tool as rt
from rubric_scoring.rubric import CRITERIA


class Fake:
    def __init__(self):
        self.messages = self
        self.calls = []

    def create(self, **p):
        self.calls.append(p)
        task = p["messages"][0]["content"][-1]["text"]
        ck = next(c for c in CRITERIA if f"'{__import__('rubric_scoring.rubric', fromlist=['x']).criterion(c)['name']}'" in task)
        out = {"criterion": ck, "score": "ABSTAIN" if ck == "citations" else "4",
               "abstention_reason": "redacted_or_missing_content" if ck == "citations" else "none",
               "rationale": "r", "evidence": [{"page": 2, "observation": "o"}], "checklist": [], "counted_items": 0,
               "limiting_factors": [], "extraction_issues": []}
        return SimpleNamespace(stop_reason="end_turn", model=p["model"], id="m",
                               content=[SimpleNamespace(type="text", text=json.dumps(out))],
                               usage=SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0,
                                                     cache_creation_input_tokens=0))


def test_score_calibrate_flag_and_export():
    fake = Fake()
    res = rt.score_deck(fake, b"=== PAGE 001 ===\nhello", "deck.txt")
    assert len(fake.calls) == 6 and res["modality"] == "text"
    assert all("project-" not in json.dumps(c) for c in fake.calls)  # no identifiers sent
    sug = rt.calibrate(res, rt.load_calibration())
    assert sug["citations"] is None and sug["next_steps"] == 4 and sug["algorithm"] == 5
    flags = rt.review_flags(res, sug)
    assert any("abstained" in f for f in flags["citations"])
    with pytest.raises(ValueError):
        rt.review_record("d1", "JD", res, sug, sug, {})  # citations unconfirmed -> refused
    final = {**sug, "citations": 3}
    rec = rt.review_record("d1", "JD", res, sug, final, {"citations": "refs visible in PDF"})
    assert rec["human_total"] == sum(final.values())
    assert [r for r in rec["criteria"] if r["criterion"] == "Citations"][0]["overridden"]


def test_reviewer_required_and_demo():
    d = rt.demo_result()
    sug = rt.calibrate(d, None)
    with pytest.raises(ValueError):
        rt.review_record("d", " ", d, sug, {c: 3 for c in CRITERIA}, {})


# ---- v2 grading-workspace helpers ----

def test_norm_title_handles_downloads_and_accents():
    assert rt.norm_title("Crème Brûlée — Model (1).pdf") == "creme brulee model"
    assert rt.norm_title("  My_Deck.PDF ") == rt.norm_title("my deck")


def test_match_deck_precedence():
    index = {"title": {"alpha": ["p1"], "dup": ["p2", "p3"]}, "drive_id": {"XYZ": "p9"},
             "size": {100: ["p1"], 200: ["p3"], 300: ["p4"]}}
    assert rt.match_deck("anything.pdf", 1, index, drive_id="XYZ") == ("p9", "Drive file")
    assert rt.match_deck("Dup.pdf", 200, index) == ("p3", "filename + size")
    assert rt.match_deck("Alpha (1).pdf", 5, index) == ("p1", "filename")
    assert rt.match_deck("renamed.pdf", 300, index) == ("p4", "file size")
    assert rt.match_deck("Dup.pdf", 5, index)[0] is None          # ambiguous title, no size match
    assert rt.match_deck("other.pdf", 5, index) == (None, "no match")


def _item(c, s="4"):
    return {"criterion": c, "score": s, "abstention_reason": "none", "rationale": "r",
            "evidence": [{"page": 1, "observation": "o"}], "checklist": [], "counted_items": 0,
            "limiting_factors": [], "extraction_issues": []}


def test_parse_pasted_single_and_batch():
    one = "Here you go:\n```json\n" + json.dumps({"scores": [_item(c) for c in CRITERIA]}) + "\n```"
    out = rt.parse_pasted(one)
    assert list(out) == ["*"] and len(out["*"]) == len(CRITERIA)
    many = json.dumps({"decks": [{"file": "a.pdf", "scores": [_item(c, "3") for c in CRITERIA]},
                                 {"file": "b.pdf", "scores": [_item(c, "5") for c in CRITERIA]}]})
    out = rt.parse_pasted(many)
    assert set(out) == {"a.pdf", "b.pdf"}
    with pytest.raises(Exception):
        rt.parse_pasted("no json here")


def test_claude_prompt_and_precomputed():
    single, batch = rt.claude_prompt(False), rt.claude_prompt(True)
    assert "one student slide-deck" in single and '"decks"' in batch
    pre = {"p1": {"items": {c: _item(c) for c in CRITERIA}, "prompt_version": "v1-free.2", "input": "text"}}
    r = rt.precomputed_result("p1", pre)
    assert r["source"] == "precomputed" and set(r["items"]) == set(CRITERIA)
    assert rt.precomputed_result("nope", pre) is None


def test_content_match_finds_deck_despite_names_and_rejects_unknown():
    def deck(words):
        return {"items": {c: {**_item(c), "rationale": " ".join(words),
                              "evidence": [{"page": 1, "observation": " ".join(words)}]} for c in CRITERIA}}
    pre = {"p1": deck("bitcoin lstm volatility candlestick support resistance halving exchanges".split()),
           "p2": deck("deepfake detection faces generative adversarial forensic watermark".split()),
           "p3": deck("asthma inhaler pollution sensors wildfire smoke counties".split())}
    prof = rt.content_profiles(pre, max_df=0.5)
    upload = "Presented by Maria Gonzalez. Our LSTM predicts bitcoin volatility using candlestick support and resistance."
    pid, share = rt.best_content_match(upload, prof)
    assert pid == "p1" and share >= 0.5
    assert rt.best_content_match("a recipe for banana bread with walnuts", prof)[0] is None
