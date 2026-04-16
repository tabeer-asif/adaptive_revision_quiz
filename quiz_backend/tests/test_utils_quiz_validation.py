import pytest
from fastapi import HTTPException

from app.utils import quiz_validation as qv


"""Unit tests for request-answer validation helpers in quiz flow."""

# Convention: tests below follow Arrange / Act / Assert flow.


class Resp:
    # Minimal response object matching `question_resp.data` shape.
    def __init__(self, data):
        self.data = data


def test_validate_question_exists():
    # Missing question should raise 404; existing question should pass.
    with pytest.raises(HTTPException) as exc:
        qv.validate_question_exists(Resp([]))
    assert exc.value.status_code == 404

    qv.validate_question_exists(Resp([{"id": 1}]))


def test_validate_answer_submitted():
    # Empty/blank answer forms should be rejected consistently.
    for invalid in [None, "", [], {}]:
        with pytest.raises(HTTPException):
            qv.validate_answer_submitted(invalid)

    qv.validate_answer_submitted("A")


def test_mcq_and_multi_mcq_selection_validation():
    # Option-key validation across MCQ and MULTI_MCQ answer formats.
    assert qv.validate_mcq_selection(" A ", {"A": "One"}) == "A"

    with pytest.raises(HTTPException):
        qv.validate_mcq_selection(1, {"A": "One"})

    with pytest.raises(HTTPException):
        qv.validate_mcq_selection("   ", {"A": "One"})

    with pytest.raises(HTTPException):
        qv.validate_mcq_selection("B", {"A": "One"})

    keys = qv.validate_multi_mcq_selection(["B", "A", "A"], {"A": "One", "B": "Two"})
    assert keys == ["A", "B"]

    with pytest.raises(HTTPException):
        qv.validate_multi_mcq_selection("A", {"A": "One"})

    with pytest.raises(HTTPException):
        qv.validate_multi_mcq_selection([], {"A": "One"})

    with pytest.raises(HTTPException):
        qv.validate_multi_mcq_selection(["X"], {"A": "One"})


def test_multi_mcq_db_and_numeric_validation():
    # Numeric and stored-answer normalization/validation behavior.
    assert qv.validate_multi_mcq_db_answer(["A", "A", "B"]) == ["A", "B"]

    with pytest.raises(HTTPException):
        qv.validate_multi_mcq_db_answer("A")

    assert qv.validate_numeric_selection(10) == 10.0
    with pytest.raises(HTTPException):
        qv.validate_numeric_selection(True)

    assert qv.validate_numeric_db_answer("3.14") == 3.14
    with pytest.raises(HTTPException):
        qv.validate_numeric_db_answer("abc")

    assert qv.validate_numeric_tolerance(None) == 0.0
    assert qv.validate_numeric_tolerance(0.2) == 0.2


def test_short_and_open_text_validation():
    # Text and self-rating validation for SHORT/OPEN question types.
    assert qv.validate_short_text(" Hello ") == "hello"
    with pytest.raises(HTTPException):
        qv.validate_short_text(5)
    with pytest.raises(HTTPException):
        qv.validate_short_text("   ")

    assert qv.validate_open_text("answer", 3) == "answer"
    with pytest.raises(HTTPException):
        qv.validate_open_text(1, 3)
    with pytest.raises(HTTPException):
        qv.validate_open_text(" ", 3)
    with pytest.raises(HTTPException):
        qv.validate_open_text("text", 5)
