# app/routes/ai.py

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from app.dependencies.auth import get_current_user
from app.supabase_client import supabase_db
from app.config import settings
import pathlib
import logging
import re
import nltk
from nltk.corpus import stopwords

logger = logging.getLogger(__name__)

# Download stopwords corpus on first import (cached after first run)
try:
    stopwords.words('english')
except LookupError:
    nltk.download('stopwords')

STOP_WORDS_EN = set(stopwords.words('english'))

router = APIRouter(prefix="/ai", tags=["ai"])

TYPE_ORDER = ["MCQ", "MULTI_MCQ", "NUMERIC", "SHORT", "OPEN"]

# Bloom aligned weights by difficulty (1-5). Higher weight means more questions allocated.
TYPE_DIFFICULTY_WEIGHTS = {
    "MCQ": [1.8, 1.6, 1.2, 0.9, 0.7],
    "SHORT": [1.6, 1.4, 1.1, 0.9, 0.8],
    "NUMERIC": [0.9, 1.1, 1.4, 1.2, 1.0],
    "MULTI_MCQ": [0.8, 1.0, 1.2, 1.4, 1.5],
    "OPEN": [0.4, 0.6, 1.0, 1.5, 1.8],
}

SHORT_KEYWORD_STOPWORDS = STOP_WORDS_EN


def get_ai_service_components():
    try:
        from app.services.ai import (
            generate_questions_from_file,
            generate_all_questions,
            score_document_feasibility,
            SUPPORTED_MIME_TYPES,
            MAX_FILE_SIZE_BYTES,
        )
        return (
            generate_questions_from_file,
            generate_all_questions,
            score_document_feasibility,
            SUPPORTED_MIME_TYPES,
            MAX_FILE_SIZE_BYTES,
        )
    except ImportError as exc:
        raise HTTPException(503, f"AI dependency error: {exc}")


def normalise_generated_questions(questions, question_type: str, difficulty: int, expected_count: int):
    warnings = []

    if not isinstance(questions, list):
        raise ValueError("AI did not return a question list")

    if len(questions) < expected_count:
        raise ValueError(f"AI returned {len(questions)} questions - expected at least {expected_count}")
    if len(questions) > expected_count:
        warnings.append(
            f"AI returned {len(questions)} questions - only the first {expected_count} were kept."
        )
        questions = questions[:expected_count]

    def clean_options(item, idx):
        options = item.get("options")
        if question_type in {"MCQ", "MULTI_MCQ"}:
            if not isinstance(options, dict):
                raise ValueError(f"Question {idx}: options must be an object")

            normalised_options = {str(k).strip().upper(): v for k, v in options.items()}
            expected_keys = {"A", "B", "C", "D"}
            available_keys = set(normalised_options.keys())
            if not expected_keys.issubset(available_keys):
                raise ValueError(f"Question {idx}: options must include keys A, B, C, D")
            if available_keys != expected_keys:
                warnings.append(f"Question {idx}: extra option keys were dropped, only A-D were kept")

            for key in expected_keys:
                value = normalised_options.get(key)
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"Question {idx}: option {key} must be non-empty text")

            if set(options.keys()) != expected_keys:
                warnings.append(f"Question {idx}: option keys were normalised to uppercase A-D")

            return {k: normalised_options[k].strip() for k in ["A", "B", "C", "D"]}
        return None

    normalised = []
    for idx, item in enumerate(questions, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Question {idx}: each item must be an object")

        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Question {idx}: text is required")

        q_type = item.get("type")
        if isinstance(q_type, str) and q_type.strip().upper() == question_type:
            if q_type != question_type:
                warnings.append(f"Question {idx}: type value was normalised to '{question_type}'")
        elif q_type != question_type:
            raise ValueError(f"Question {idx}: type must be '{question_type}'")

        answer = item.get("answer")
        options = clean_options(item, idx)
        keywords = None
        tolerance = None

        if question_type == "MCQ":
            if not isinstance(answer, str):
                raise ValueError(f"Question {idx}: MCQ answer must be one of A/B/C/D")
            answer = answer.strip().upper()
            if answer not in {"A", "B", "C", "D"}:
                raise ValueError(f"Question {idx}: MCQ answer must be one of A/B/C/D")

        elif question_type == "MULTI_MCQ":
            if not isinstance(answer, list):
                raise ValueError(f"Question {idx}: MULTI_MCQ answer must be an array")
            cleaned = sorted({str(a).strip().upper() for a in answer if str(a).strip()})
            if len(cleaned) < 1 or any(a not in {"A", "B", "C", "D"} for a in cleaned):
                raise ValueError(f"Question {idx}: MULTI_MCQ answer must contain at least 1 key from A/B/C/D")
            answer = cleaned

        elif question_type == "SHORT":
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError(f"Question {idx}: SHORT answer must be non-empty text")
            raw_keywords = item.get("keywords")
            if not isinstance(raw_keywords, list):
                raw_keywords = []
                warnings.append(f"Question {idx}: SHORT keywords missing/invalid; auto-generated keywords were used")

            # Keep unique non empty keywords (like no hard minimum like 3 terms).
            seen_keywords = set()
            keywords = []
            for raw in raw_keywords:
                k = str(raw).strip()
                if not k:
                    continue
                key = k.lower()
                if key in seen_keywords:
                    continue
                seen_keywords.add(key)
                keywords.append(k)

            # If no useful keywords are provided, derive one meaningful keyword from answer/text.
            if not keywords:
                source_tokens = []
                for token in re.findall(r"[A-Za-z0-9]+", f"{answer} {text}"):
                    clean = token.strip().lower()
                    if len(clean) >= 4 and clean not in SHORT_KEYWORD_STOPWORDS:
                        source_tokens.append(clean)

                if source_tokens:
                    keywords = [source_tokens[0]]
                else:
                    # Last resort fallback, first non-empty word from answer.
                    fallback = next((w for w in answer.strip().split() if w.strip()), "concept")
                    keywords = [fallback]

                warnings.append(
                    f"Question {idx}: SHORT keywords were auto-derived for relevance"
                )
            answer = answer.strip()

        elif question_type == "NUMERIC":
            try:
                answer = float(answer)
            except (TypeError, ValueError):
                raise ValueError(f"Question {idx}: NUMERIC answer must be a number")
            raw_tol = item.get("tolerance", 0.0)
            try:
                tolerance = float(raw_tol)
            except (TypeError, ValueError):
                raise ValueError(f"Question {idx}: NUMERIC tolerance must be a number")
            if tolerance < 0:
                raise ValueError(f"Question {idx}: NUMERIC tolerance cannot be negative")
            if "tolerance" not in item:
                warnings.append(f"Question {idx}: tolerance was missing and defaulted to 0.0")

        elif question_type == "OPEN":
            if not isinstance(answer, str) or len(answer.strip()) < 10:
                raise ValueError(f"Question {idx}: OPEN answer must be a meaningful model answer")
            answer = answer.strip()

        explanation = item.get("explanation")
        if explanation is not None and not isinstance(explanation, str):
            warnings.append(f"Question {idx}: explanation was converted to text")
            explanation = str(explanation)

        normalised.append({
            "text": text.strip(),
            "type": question_type,
            "options": options,
            "answer": answer,
            "keywords": keywords,
            "tolerance": tolerance,
            "difficulty": difficulty,
            "explanation": explanation.strip() if isinstance(explanation, str) else "",
        })

    return normalised, warnings


def allocate_type_counts(selected_types, count: int, difficulty: int):
    ordered = [t for t in TYPE_ORDER if t in selected_types]
    if not ordered:
        return {}

    # If count is enough, guarantee at least one per selected type.
    counts = {t: 0 for t in ordered}
    guaranteed = len(ordered) if count >= len(ordered) else 0
    if guaranteed:
        for t in ordered:
            counts[t] = 1

    remaining = count - guaranteed
    if remaining <= 0:
        return counts

    diff_idx = max(0, min(4, difficulty - 1))
    weights = {t: TYPE_DIFFICULTY_WEIGHTS.get(t, [1, 1, 1, 1, 1])[diff_idx] for t in ordered}
    weight_sum = sum(weights.values()) or float(len(ordered))

    raw_alloc = {t: remaining * (weights[t] / weight_sum) for t in ordered}
    floored = {t: int(raw_alloc[t]) for t in ordered}

    for t in ordered:
        counts[t] += floored[t]

    leftovers = remaining - sum(floored.values())
    if leftovers > 0:
        ranked = sorted(
            ordered,
            key=lambda t: (raw_alloc[t] - floored[t], -TYPE_ORDER.index(t)),
            reverse=True,
        )
        for t in ranked[:leftovers]:
            counts[t] += 1

    return counts


def text_tokens(value: str):
    parts = re.findall(r"[a-z0-9]+", (value or "").lower())
    return {p for p in parts if len(p) > 2}


def is_near_duplicate(text_a: str, text_b: str, threshold: float = 0.85):
    a = " ".join((text_a or "").lower().split())
    b = " ".join((text_b or "").lower().split())
    if not a or not b:
        return False
    if a == b:
        return True

    tokens_a = text_tokens(a)
    tokens_b = text_tokens(b)
    if not tokens_a or not tokens_b:
        return False

    overlap = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    if union == 0:
        return False

    return (overlap / union) >= threshold


def prune_near_duplicates(questions):
    kept = []
    dropped = 0

    for candidate in questions:
        candidate_text = candidate.get("text", "")
        candidate_type = candidate.get("type")
        duplicate = False
        for existing in kept:
            # Only de-duplicate within the same question type.
            if existing.get("type") != candidate_type:
                continue
            if is_near_duplicate(existing.get("text", ""), candidate_text):
                duplicate = True
                break
        if duplicate:
            dropped += 1
            continue
        kept.append(candidate)

    return kept, dropped


@router.post("/feasibility")
async def score_feasibility(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """
    Scores how suitable a document is for each question type.
    Returns {"MCQ": 0.9, "NUMERIC": 0.1, ...} with values 0.0-1.0.
    """
    _, _, score_document_feasibility, SUPPORTED_MIME_TYPES, MAX_FILE_SIZE_BYTES = get_ai_service_components()

    suffix = pathlib.Path(file.filename or "").suffix.lower()
    mime_type = SUPPORTED_MIME_TYPES.get(suffix)
    if not mime_type:
        raise HTTPException(400, f"Unsupported file type: {suffix or '(none)'}")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(413, f"File too large. Maximum size is {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB.")

    scores = await score_document_feasibility(file_bytes, file.filename or "upload", mime_type)
    return {"scores": scores}


@router.post("/generate-questions")
async def generate_questions(
    file: UploadFile = File(...),
    topic_id: int = Form(...),
    question_type: str = Form(None),
    question_types: str = Form(None),
    difficulty: int = Form(...),
    count: int = Form(5),
    user=Depends(get_current_user),
):
    # Feature flag check
    if not settings.AI_ENABLED or not settings.GEMINI_API_KEY:
        raise HTTPException(503, "AI features are not enabled.")

    _, generate_all_questions, _, SUPPORTED_MIME_TYPES, MAX_FILE_SIZE_BYTES = get_ai_service_components()

    # Validate question type
    valid_types = {"MCQ", "MULTI_MCQ", "SHORT", "NUMERIC", "OPEN"}
    
    # Support both old single type and new multitype parameters
    if question_types:
        selected_types = [t.strip().upper() for t in question_types.split(",")]
        selected_types = [t for t in selected_types if t]
    elif question_type:
        selected_types = [question_type.upper()]
    else:
        raise HTTPException(422, "question_type or question_types is required")
    
    for qtype in selected_types:
        if qtype not in valid_types:
            raise HTTPException(422, f"Invalid question type: '{qtype}', Valid types: {valid_types}")
    
    if not selected_types:
        raise HTTPException(422, "At least one question type must be selected")

    #  Validate difficulty
    if not 1 <= difficulty <= 5:
        raise HTTPException(422, "difficulty must be between 1 and 5")

    #Cap count
    count = min(max(count, 1), 15)
    logger.info(
        "ai_generate_questions_request user_id=%s topic_id=%s question_type=%s difficulty=%s count=%s",
        str(user.id), topic_id, question_type, difficulty, count,
    )

    # 4 Validate file extension
    if not file.filename:
        raise HTTPException(400, "Uploaded file is missing a filename.")

    suffix = pathlib.Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_MIME_TYPES:
        raise HTTPException(
            415,
            f"Unsupported file type '{suffix}'. "
            f"Supported: {', '.join(SUPPORTED_MIME_TYPES.keys())}"
        )

    expected_mime = SUPPORTED_MIME_TYPES[suffix]
    if file.content_type and file.content_type not in {expected_mime, "application/octet-stream"}:
        raise HTTPException(
            415,
            f"MIME type '{file.content_type}' does not match extension '{suffix}'"
        )

    # Validate file size
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(413, f"File too large. Maximum size is 20MB.")

    if not file_bytes:
        raise HTTPException(400, "Uploaded file is empty.")

    #  Validate topic exists
    topic_res = (
        supabase_db.table("topics")
        .select("id, name")
        .eq("id", topic_id)
        .single()
        .execute()
    )

    if not topic_res.data:
        raise HTTPException(404, "Topic not found.")

    topic_name = topic_res.data["name"]
    mime_type = expected_mime

    #  Generate questions for each selected type (single upload, concurrent slices)
    type_counts = allocate_type_counts(selected_types, count, difficulty)
    generation_requests = []
    for qtype in selected_types:
        requested_for_type = type_counts.get(qtype, 0)
        if requested_for_type > 0:
            generation_requests.append(
                {
                    "type": qtype,
                    "difficulty": difficulty,
                    "count": requested_for_type,
                }
            )

    if not generation_requests:
        raise HTTPException(422, "No questions to generate after allocation.")

    all_questions = []
    all_warnings = []

    try:
        results = await generate_all_questions(
            file_bytes=file_bytes,
            filename=file.filename,
            mime_type=mime_type,
            topic_name=topic_name,
            requests=generation_requests,
        )

        for req, result in zip(generation_requests, results):
            if isinstance(result, Exception):
                all_warnings.append(
                    f"{req['type']} (difficulty {req['difficulty']}): generation failed - {str(result)}"
                )
                logger.warning(
                    "ai_slice_failed topic_id=%s type=%s difficulty=%s error=%s",
                    topic_id,
                    req["type"],
                    req["difficulty"],
                    str(result),
                )
                continue

            questions, warnings = normalise_generated_questions(
                result,
                question_type=req["type"],
                difficulty=req["difficulty"],
                expected_count=req["count"],
            )
            all_questions.extend(questions)
            all_warnings.extend(warnings)

        if not all_questions:
            raise HTTPException(422, "All generation slices failed. Please try again.")
    except ValueError as e:
        logger.warning("ai_generate_questions_validation_error topic_id=%s error=%s", topic_id, str(e))
        raise HTTPException(422, str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("ai_generate_questions_unhandled_error topic_id=%s", topic_id)
        raise HTTPException(500, f"Generation failed: {str(e)}")

    all_questions, dropped_duplicates = prune_near_duplicates(all_questions)
    if dropped_duplicates:
        all_warnings.append(
            f"{dropped_duplicates} near-duplicate question(s) were removed to improve variety."
        )

    logger.info(
        "ai_generate_questions_success user_id=%s topic_id=%s types=%s type_counts=%s generated_count=%s",
        str(user.id),
        topic_id,
        selected_types,
        type_counts,
        len(all_questions),
    )

    #  Return for user review — NOT been saved yet
    # Frontend shows preview, user edits&approves, then calls POST /questions
    return {
        "generated": all_questions,
        "count": len(all_questions),
        "validation_warnings": all_warnings,
        "topic_id": topic_id,
        "question_types": selected_types,
        "type_counts": type_counts,
        "message": "Review and edit questions before saving. "
                   "Call POST /questions for each one you approve."
    }