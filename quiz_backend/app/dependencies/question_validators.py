from fastapi import HTTPException
from urllib.parse import urlparse
from app.supabase_client import supabase_db
from app.schemas.questions import CreateQuestionRequest

def check_topic_id(topic_id: int):
    '''topic id must exist in topics table'''
    resp = supabase_db.table("topics") \
        .select("id") \
        .eq("id", topic_id) \
        .limit(1) \
        .execute()

    if not resp.data:
        raise HTTPException(400, f"Invalid topic_id: {topic_id}")


def _require_text(text: str):
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(400, "Question text is required")


def _require_mcq_options(options):
    if not isinstance(options, dict) or not options:
        raise HTTPException(400, "MCQ requires non-empty options")

    # Keys and values must be meaningful strings.
    for key, value in options.items():
        if not isinstance(key, str) or not key.strip():
            raise HTTPException(400, "Option keys must be non-empty strings")
        if not isinstance(value, str) or not value.strip():
            raise HTTPException(400, "Option values must be non-empty strings")


def _ensure_keys_exist(keys, options, question_type: str):
    invalid_keys = [k for k in keys if k not in options]
    if invalid_keys:
        raise HTTPException(
            400,
            f"{question_type} answer keys must exist in options: {invalid_keys}",
        )


def _validate_image_url(image_url):
    # Allow None/empty so update flows can clear an existing image.
    if image_url is None or image_url == "":
        return

    if not isinstance(image_url, str):
        raise HTTPException(400, "image_url must be a string")

    parsed = urlparse(image_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(400, "image_url must be a valid http/https URL")
    

def validate_mcq(data: CreateQuestionRequest):
    check_topic_id(data.topic_id)
    _require_text(data.text)
    _validate_image_url(data.image_url)
    if data.answer is None:
        raise HTTPException(400, "Answer is required for MCQ")
    _require_mcq_options(data.options)
    if data.tolerance is not None:
        raise HTTPException(400, "MCQ should not have tolerance")
    if data.keywords is not None:
        raise HTTPException(400, "MCQ should not have keywords")

    if not isinstance(data.answer, str) or not data.answer.strip():
        raise HTTPException(400, "MCQ answer must be a non-empty option key")

    answer_key = data.answer.strip()
    _ensure_keys_exist([answer_key], data.options, "MCQ")
    

    
def validate_multi_mcq(data: CreateQuestionRequest):
    check_topic_id(data.topic_id)
    _require_text(data.text)
    _validate_image_url(data.image_url)
    if data.answer is None:
        raise HTTPException(400, "Answer is required for MULTI_MCQ")
    _require_mcq_options(data.options)
    if data.tolerance is not None:
        raise HTTPException(400, "MULTI_MCQ should not have tolerance")
    if data.keywords is not None:
        raise HTTPException(400, "MULTI_MCQ should not have keywords")

    if not isinstance(data.answer, list):
        raise HTTPException(400, "MULTI_MCQ answer must be a list of keys (e.g. ['A','C'])")

    if not data.answer:
        raise HTTPException(400, "MULTI_MCQ answer list cannot be empty")

    if any(not isinstance(k, str) or not k.strip() for k in data.answer):
        raise HTTPException(400, "MULTI_MCQ answer keys must be non-empty strings")

    normalized_keys = [k.strip() for k in data.answer]
    if len(normalized_keys) != len(set(normalized_keys)):
        raise HTTPException(400, "MULTI_MCQ answer keys must be unique")

    _ensure_keys_exist(normalized_keys, data.options, "MULTI_MCQ")

    if data.irt_thresholds is not None:
        if len(data.irt_thresholds) < 2:
            raise HTTPException(400, "MULTI_MCQ irt_thresholds must have at least 2 values")
        if any(a > b for a, b in zip(data.irt_thresholds, data.irt_thresholds[1:])):
            raise HTTPException(400, "MULTI_MCQ irt_thresholds must be in ascending order")
    
def validate_numeric(data: CreateQuestionRequest):
    check_topic_id(data.topic_id)

    _require_text(data.text)
    _validate_image_url(data.image_url)
    if data.options is not None:
        raise HTTPException(400, "NUMERIC should not have options")
    if data.answer is None:
        raise HTTPException(400, "Answer is required for NUMERIC")
    if data.keywords is not None:
        raise HTTPException(400, "NUMERIC should not have keywords")
    if data.tolerance is None:
        raise HTTPException(400, "NUMERIC requires tolerance")

    if isinstance(data.answer, bool) or not isinstance(data.answer, (int, float)):
        raise HTTPException(400, "NUMERIC answer must be a number")

    if data.tolerance < 0:
        raise HTTPException(400, "NUMERIC tolerance must be >= 0")
    
def validate_short(data: CreateQuestionRequest):
    check_topic_id(data.topic_id)
    _require_text(data.text)
    _validate_image_url(data.image_url)
    if data.options is not None:
        raise HTTPException(400, "SHORT should not have options")
    if data.answer is None:
        raise HTTPException(400, "Answer is required for SHORT")
    if data.tolerance is not None:
        raise HTTPException(400, "SHORT should not have tolerance")
    if not data.keywords:
        raise HTTPException(400, "SHORT requires keywords list")

    if not isinstance(data.answer, str) or not data.answer.strip():
        raise HTTPException(400, "SHORT answer must be a string")

    if any(not isinstance(k, str) or not k.strip() for k in data.keywords):
        raise HTTPException(400, "SHORT keywords must be non-empty strings")

def validate_open(data: CreateQuestionRequest):
    # OPEN is flexible — optional model answer allowed
    check_topic_id(data.topic_id)
    _require_text(data.text)
    _validate_image_url(data.image_url)
    if data.options is not None:
        raise HTTPException(400, "OPEN should not have options")
    if data.tolerance is not None:
        raise HTTPException(400, "OPEN should not have tolerance")
    if data.keywords is not None:
        raise HTTPException(400, "OPEN should not have keywords")

    if data.answer is not None and (not isinstance(data.answer, str) or not data.answer.strip()):
        raise HTTPException(400, "OPEN answer should be a string or null")
    

VALIDATORS = {
    "MCQ": validate_mcq,
    "MULTI_MCQ": validate_multi_mcq,
    "NUMERIC": validate_numeric,
    "SHORT": validate_short,
    "OPEN": validate_open,
}