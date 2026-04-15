from typing import Mapping
import logging

from fastapi import HTTPException


logger = logging.getLogger(__name__)

def validate_question_exists(question_resp):
    if not question_resp.data:
        raise HTTPException(status_code=404, detail="Question not found")

def validate_answer_submitted(selected_option) -> None:
    if selected_option is None or selected_option == "" or selected_option == [] or selected_option == {}:
        raise HTTPException(status_code=400, detail="No answer submitted")


def validate_mcq_selection(selected_option, options: Mapping) -> str:
    if not isinstance(selected_option, str):
        raise HTTPException(status_code=400, detail="MCQ answer must be a string option key")

    selected_key = selected_option.strip()
    if not selected_key:
        raise HTTPException(status_code=400, detail="MCQ answer key is required")

    if options and selected_key not in options:
        raise HTTPException(status_code=400, detail="Selected MCQ key does not exist in options")

    return selected_key


def validate_multi_mcq_selection(selected_option, options: Mapping) -> list[str]:
    if not isinstance(selected_option, list):
        raise HTTPException(status_code=400, detail="MULTI_MCQ answer must be a list of option keys")

    selected_keys = sorted({str(key).strip() for key in selected_option if str(key).strip()})
    if not selected_keys:
        raise HTTPException(status_code=400, detail="MULTI_MCQ requires at least one selected key")

    if options:
        invalid = [key for key in selected_keys if key not in options]
        if invalid:
            raise HTTPException(status_code=400, detail=f"Invalid MULTI_MCQ key(s): {invalid}")

    return selected_keys


def validate_multi_mcq_db_answer(db_answer) -> list[str]:
    if not isinstance(db_answer, list):
        raise HTTPException(status_code=500, detail="Stored MULTI_MCQ answer is invalid")

    return sorted({str(key).strip() for key in db_answer if str(key).strip()})


def validate_numeric_selection(selected_option) -> float:
    if isinstance(selected_option, bool) or not isinstance(selected_option, (int, float)):
        raise HTTPException(status_code=400, detail="NUMERIC answer must be a number")

    return float(selected_option)


def validate_numeric_db_answer(db_answer) -> float:
    try:
        return float(db_answer)
    except (TypeError, ValueError):
        raise HTTPException(status_code=500, detail="Stored NUMERIC answer is invalid")


def validate_numeric_tolerance(tolerance) -> float:
    if tolerance is None:
        logger.warning("NUMERIC question missing tolerance; defaulting to exact match (0.0).")
        return 0.0
    return float(tolerance)


def validate_short_text(selected_option) -> str:
    if not isinstance(selected_option, str):
        raise HTTPException(status_code=400, detail="SHORT answer must be a string")

    submitted_text = selected_option.strip().lower()
    if not submitted_text:
        raise HTTPException(status_code=400, detail="SHORT answer text is required")

    return submitted_text


def validate_open_text(selected_option, self_rating) -> str:
    if not isinstance(selected_option, str):
        raise HTTPException(status_code=400, detail="OPEN answer must be a string")

    submitted_text = selected_option.strip()
    if not submitted_text:
        raise HTTPException(status_code=400, detail="OPEN answer text is required")

    if self_rating is None or self_rating not in [1, 2, 3, 4]:
        raise HTTPException(
            status_code=400,
            detail="OPEN questions require a self_rating between 1 and 4"
        )

    return submitted_text


