import pytest
from fastapi import HTTPException

from app.dependencies import question_validators as qv
from app.schemas.questions import CreateQuestionRequest


"""Edge-case coverage for every validator guard branch."""

# Convention: tests below follow Arrange / Act / Assert flow.


def _base_payload(q_type, **kwargs):
    # Helper to keep negative-path tests concise.
    base = {
        "topic_id": 1,
        "text": "Question",
        "type": q_type,
        "difficulty": 1,
    }
    base.update(kwargs)
    return CreateQuestionRequest(**base)


def test_internal_text_options_and_key_helpers():
    # Internal helper functions should reject malformed text/options/keys.
    with pytest.raises(HTTPException):
        qv._require_text(" ")

    with pytest.raises(HTTPException):
        qv._require_mcq_options(None)

    with pytest.raises(HTTPException):
        qv._require_mcq_options({" ": "x"})

    with pytest.raises(HTTPException):
        qv._require_mcq_options({"A": " "})

    with pytest.raises(HTTPException):
        qv._ensure_keys_exist(["X"], {"A": "One"}, "MCQ")


def test_internal_image_url_helper():
    # image_url helper accepts None/empty/valid URLs and rejects malformed values.
    qv._validate_image_url(None)
    qv._validate_image_url("")
    qv._validate_image_url("https://cdn.example/img.png")

    with pytest.raises(HTTPException):
        qv._validate_image_url("invalid-url")


def test_validate_mcq_negative_paths(monkeypatch):
    # MCQ-specific invalid combinations and malformed answers.
    monkeypatch.setattr(qv, "check_topic_id", lambda _tid: None)

    with pytest.raises(HTTPException):
        qv.validate_mcq(_base_payload("MCQ", options={"A": "One"}, answer=None))

    with pytest.raises(HTTPException):
        qv.validate_mcq(_base_payload("MCQ", options={"A": "One"}, answer="A", tolerance=0.1))

    with pytest.raises(HTTPException):
        qv.validate_mcq(_base_payload("MCQ", options={"A": "One"}, answer="A", keywords=["k"]))

    with pytest.raises(HTTPException):
        qv.validate_mcq(_base_payload("MCQ", options={"A": "One"}, answer=" "))


def test_validate_multi_mcq_negative_paths(monkeypatch):
    # MULTI_MCQ-specific invalid combinations and malformed answers.
    monkeypatch.setattr(qv, "check_topic_id", lambda _tid: None)

    with pytest.raises(HTTPException):
        qv.validate_multi_mcq(_base_payload("MULTI_MCQ", options={"A": "One"}, answer=None))

    with pytest.raises(HTTPException):
        qv.validate_multi_mcq(_base_payload("MULTI_MCQ", options={"A": "One"}, answer=["A"], tolerance=0.1))

    with pytest.raises(HTTPException):
        qv.validate_multi_mcq(_base_payload("MULTI_MCQ", options={"A": "One"}, answer=["A"], keywords=["k"]))

    with pytest.raises(HTTPException):
        qv.validate_multi_mcq(_base_payload("MULTI_MCQ", options={"A": "One"}, answer="A"))

    with pytest.raises(HTTPException):
        qv.validate_multi_mcq(_base_payload("MULTI_MCQ", options={"A": "One"}, answer=[]))

    with pytest.raises(HTTPException):
        qv.validate_multi_mcq(_base_payload("MULTI_MCQ", options={"A": "One"}, answer=[" "]))

    with pytest.raises(HTTPException):
        qv.validate_multi_mcq(_base_payload("MULTI_MCQ", options={"A": "One"}, answer=["A"], irt_thresholds=[0.8, 0.2]))


def test_validate_numeric_short_open_negative_paths(monkeypatch):
    # Remaining negative branches for NUMERIC, SHORT, and OPEN.
    monkeypatch.setattr(qv, "check_topic_id", lambda _tid: None)

    with pytest.raises(HTTPException):
        qv.validate_numeric(_base_payload("NUMERIC", options={"A": "One"}, answer=1.2, tolerance=0.1))

    with pytest.raises(HTTPException):
        qv.validate_numeric(_base_payload("NUMERIC", answer=None, tolerance=0.1))

    with pytest.raises(HTTPException):
        qv.validate_numeric(_base_payload("NUMERIC", answer=1.2, keywords=["k"], tolerance=0.1))

    with pytest.raises(HTTPException):
        qv.validate_numeric(_base_payload("NUMERIC", answer=1.2, tolerance=None))

    with pytest.raises(HTTPException):
        qv.validate_numeric(_base_payload("NUMERIC", answer="not-a-number", tolerance=0.1))

    with pytest.raises(HTTPException):
        qv.validate_short(_base_payload("SHORT", options={"A": "One"}, answer="x", keywords=["k"]))

    with pytest.raises(HTTPException):
        qv.validate_short(_base_payload("SHORT", answer=None, keywords=["k"]))

    with pytest.raises(HTTPException):
        qv.validate_short(_base_payload("SHORT", answer="x", keywords=["k"], tolerance=0.1))

    with pytest.raises(HTTPException):
        qv.validate_short(_base_payload("SHORT", answer=" ", keywords=["k"]))

    with pytest.raises(HTTPException):
        qv.validate_short(_base_payload("SHORT", answer="x", keywords=["ok", " "]))

    with pytest.raises(HTTPException):
        qv.validate_open(_base_payload("OPEN", options={"A": "One"}, answer="x"))

    with pytest.raises(HTTPException):
        qv.validate_open(_base_payload("OPEN", answer="x", tolerance=0.1))

    with pytest.raises(HTTPException):
        qv.validate_open(_base_payload("OPEN", answer="x", keywords=["k"]))
