"""Scorer tests with a fake client. No network calls."""
import json
from types import SimpleNamespace

import pytest

from rubric_scoring import scorer
from rubric_scoring.inputs import Artifact, assert_no_leakage
from rubric_scoring.prompts import SYSTEM_PROMPT, output_schema


def _artifact(tmp_path):
    t = tmp_path / "presentation.txt"
    t.write_text("[Page 1]\nPredicting crop yield with random forests\n[Page 9]\nReferences: ...")
    return Artifact("project-xyz", None, t)


class FakeClient:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.requests = []
        self.messages = self

    def create(self, **params):
        self.requests.append(params)
        text, stop = self.outputs.pop(0)
        return SimpleNamespace(
            model=params["model"], stop_reason=stop, id="msg_fake", stop_details=None,
            content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
            usage=SimpleNamespace(input_tokens=100, output_tokens=50, cache_read_input_tokens=900,
                                  cache_creation_input_tokens=0))


def _ok(crit, score="5"):
    return json.dumps({"criterion": crit, "score": score, "abstention_reason": "none", "rationale": "x",
                       "evidence": [{"page": 1, "observation": "y"}], "checklist": [], "counted_items": 0,
                       "limiting_factors": [], "extraction_issues": []})


def test_request_contains_no_project_id_or_labels(tmp_path, config):
    a = _artifact(tmp_path)
    cond = config["scoring"]["conditions"]["C3_evidence_text_only"]
    params, meta = scorer.build_params(a, cond, config["scoring"], "citations")
    blob = json.dumps(params)
    assert "project-xyz" not in blob
    assert params["system"][0]["text"] == SYSTEM_PROMPT
    assert params["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert "fallbacks" not in params  # a silent model switch would confound the study
    assert len(meta["input_sha256"]) == 64


def test_leakage_guard():
    with pytest.raises(AssertionError):
        assert_no_leakage({"messages": [{"cohort": "SU25"}]})
    with pytest.raises(AssertionError):
        assert_no_leakage({"messages": ["Jane Q. Student"]}, ["Jane Q. Student"])


def test_invalid_then_valid_retry_and_logging(tmp_path, config):
    from rubric_scoring.rubric import CRITERIA
    outs = [("not json", "end_turn"), (_ok(CRITERIA[0]), "end_turn")] + [(_ok(c), "end_turn") for c in CRITERIA[1:]]
    client = FakeClient(outs)
    log = tmp_path / "log.jsonl"
    scorer.run_condition([_artifact(tmp_path)], "C3_evidence_text_only", config, log, client=client)
    recs = [json.loads(x) for x in log.read_text().splitlines()]
    assert [r["status"] for r in recs].count("invalid_output") == 1
    assert [r["status"] for r in recs].count("valid") == 6
    rows = scorer.predictions_table(log)
    assert len(rows) == 6 and all(r["score"] == 5 for r in rows)
    # resume: nothing re-scored
    scorer.run_condition([_artifact(tmp_path)], "C3_evidence_text_only", config, log, client=FakeClient([]))


def test_refusal_and_abstain_stay_in_denominators(tmp_path, config):
    from rubric_scoring.rubric import CRITERIA
    abst = json.dumps({"criterion": CRITERIA[5], "score": "ABSTAIN", "abstention_reason": "redacted_or_missing_content",
                       "rationale": "refs redacted", "evidence": [], "checklist": [], "counted_items": 0,
                       "limiting_factors": ["possible_redaction"], "extraction_issues": []})
    outs = [("", "refusal")] + [(_ok(c), "end_turn") for c in CRITERIA[1:5]] + [(abst, "end_turn")]
    log = tmp_path / "log.jsonl"
    scorer.run_condition([_artifact(tmp_path)], "C3_evidence_text_only", config, log, client=FakeClient(outs))
    rows = {r["criterion"]: r for r in scorer.predictions_table(log)}
    assert rows[CRITERIA[0]]["status"] == "failed" and rows[CRITERIA[0]]["final_status"] == "refusal"
    assert rows[CRITERIA[5]]["status"] == "abstain" and rows[CRITERIA[5]]["score"] is None


def test_joint_schema_shape():
    s = output_schema("evidence", "joint")
    assert s["properties"]["scores"]["type"] == "array"
