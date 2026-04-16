import pytest
from fastapi import HTTPException

from app.dependencies import question_validators as qv
from app.schemas.questions import CreateQuestionRequest
from tests.conftest import StubSupabaseDB


"""Validator tests for normal and representative failure paths."""

# Convention: tests below follow Arrange / Act / Assert flow.


def test_check_topic_id(monkeypatch):
    # Existing topic id passes; missing topic id fails.
    db = StubSupabaseDB({("topics", "select"): [{"data": [{"id": 1}]}]})
    monkeypatch.setattr(qv, "supabase_db", db)
    qv.check_topic_id(1)

    db2 = StubSupabaseDB({("topics", "select"): [{"data": []}]})
    monkeypatch.setattr(qv, "supabase_db", db2)
    with pytest.raises(HTTPException):
        qv.check_topic_id(999)


def test_validate_mcq(monkeypatch):
    # MCQ payload validation should pass for valid option key.
    db = StubSupabaseDB({("topics", "select"): [{"data": [{"id": 1}]}]})
    monkeypatch.setattr(qv, "supabase_db", db)

    payload = CreateQuestionRequest(
        topic_id=1,
        text="Q",
        type="MCQ",
        options={"A": "1", "B": "2"},
        answer="A",
        difficulty=1,
        image_url="https://cdn.example/image.png",
    )
    qv.validate_mcq(payload)

    bad = payload.model_copy(update={"answer": "X"})
    with pytest.raises(HTTPException):
        qv.validate_mcq(bad)


def test_validate_multi_mcq(monkeypatch):
    # MULTI_MCQ validates list answers and threshold shape/order.
    db = StubSupabaseDB({("topics", "select"): [{"data": [{"id": 1}]}, {"data": [{"id": 1}]}, {"data": [{"id": 1}]}]})
    monkeypatch.setattr(qv, "supabase_db", db)

    payload = CreateQuestionRequest(
        topic_id=1,
        text="Q",
        type="MULTI_MCQ",
        options={"A": "1", "B": "2"},
        answer=["A", "B"],
        difficulty=2,
        irt_thresholds=[-0.5, 0.5],
    )
    qv.validate_multi_mcq(payload)

    dup = payload.model_copy(update={"answer": ["A", "A"]})
    with pytest.raises(HTTPException):
        qv.validate_multi_mcq(dup)

    bad_thresholds = payload.model_copy(update={"irt_thresholds": [0.5]})
    with pytest.raises(HTTPException):
        qv.validate_multi_mcq(bad_thresholds)


def test_validate_numeric_short_open(monkeypatch):
    # Cover core validation behavior for NUMERIC/SHORT/OPEN types.
    db = StubSupabaseDB({("topics", "select"): [
        {"data": [{"id": 1}]},
        {"data": [{"id": 1}]},
        {"data": [{"id": 1}]},
        {"data": [{"id": 1}]},
        {"data": [{"id": 1}]},
        {"data": [{"id": 1}]},
    ]})
    monkeypatch.setattr(qv, "supabase_db", db)

    numeric = CreateQuestionRequest(
        topic_id=1,
        text="Q",
        type="NUMERIC",
        answer=4.2,
        tolerance=0.1,
    )
    qv.validate_numeric(numeric)

    with pytest.raises(HTTPException):
        qv.validate_numeric(numeric.model_copy(update={"tolerance": -1.0}))

    short = CreateQuestionRequest(
        topic_id=1,
        text="Q",
        type="SHORT",
        answer="photosynthesis",
        keywords=["sunlight", "chlorophyll"],
    )
    qv.validate_short(short)

    with pytest.raises(HTTPException):
        qv.validate_short(short.model_copy(update={"keywords": []}))

    open_q = CreateQuestionRequest(
        topic_id=1,
        text="Q",
        type="OPEN",
        answer="Model answer",
        image_url="https://cdn.example/open.png",
    )
    qv.validate_open(open_q)

    with pytest.raises(HTTPException):
        qv.validate_open(open_q.model_copy(update={"answer": "  "}))

    with pytest.raises(HTTPException):
        qv.validate_open(open_q.model_copy(update={"image_url": "not-a-url"}))
