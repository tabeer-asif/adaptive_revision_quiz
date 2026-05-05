# app/services/ai.py

from google import genai
from google.genai import types
import json
import tempfile
import os
import pathlib
import hashlib
import time
from app.config import settings
import asyncio
import logging

logger = logging.getLogger(__name__)

# ── Initialise client once ──────────────────────────────────────────
client = genai.Client(api_key=settings.GEMINI_API_KEY)
MODEL = "gemini-3-flash-preview"   # ← updated model


# ── Supported file types ────────────────────────────────────────────
SUPPORTED_MIME_TYPES = {
    ".pdf":  "application/pdf",
    ".txt":  "text/plain",
    ".md":   "text/markdown",
    ".doc":  "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

MAX_FILE_SIZE_MB = 20
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_RETRIES = 3
RETRY_BASE_SECONDS = 1.0
FILE_URI_CACHE_TTL_SECONDS = 600

# In memory cache for feasibility -> generation URI reuse.
# Keyed by SHA-256 hash of file bytes.

file_uri_cache: dict[str, dict] = {}


# ── Prompts ─────────────────────────────────────────────────────────
QUESTION_GENERATION_PROMPT = """
You are an expert educator creating quiz questions from study material.

Generate exactly {n} questions of type **{q_type}** from the uploaded document.

Topic context: {topic_name}
Difficulty level: {difficulty}/5 ({difficulty_label})

Question type rules:
{type_rules}

Bloom taxonomy intent for this type:
{bloom_guidance}

IMPORTANT:
- Base questions ONLY on content found in the document
- Do not invent facts not present in the material
- Vary which parts of the document you draw from
- Match the difficulty level strictly
- Write question text as standalone, self contained questions - do NOT use phrases like "according to the document", "based on the material", "from the study material", "in the text", "as mentioned", or any reference to a document/material/resource. The student will not have access to the source material during the quiz.

Return ONLY a valid JSON array, no markdown, no explanation:
[
  {{
    "text": "the question text",
    "type": "{q_type}",
    "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}} or null,
    "answer": "...",
    "keywords": ["keyword1", "keyword2"] or null,
    "tolerance": null,
    "difficulty": {difficulty},
    "explanation": "brief explanation of why this is correct"
  }}
]
"""

TYPE_RULES = {
    "MCQ": """
- Provide exactly 4 options labelled A, B, C, D
- answer must be a single key string e.g. "A"
- One correct answer, three plausible distractors
- options field: {"A": "...", "B": "...", "C": "...", "D": "..."}
- keywords: null
- tolerance: null
""",
    "MULTI_MCQ": """
- Provide exactly 4 options labelled A, B, C, D
- answer must be a JSON array of correct keys e.g. ["A", "C"]
- At least 1 correct answer, the rest can be distractors but avoid making all 4 correct
- options field: {"A": "...", "B": "...", "C": "...", "D": "..."}
- keywords: null
- tolerance: null
""",
    "SHORT": """
- answer is a concise string (1-5 words ideally)
- keywords: array of 1-5 concise, relevant key terms (avoid filler words)
- options: null
- tolerance: null
""",
    "NUMERIC": """
- answer must be a number (integer or float) e.g. 9.81
- tolerance: suggest appropriate tolerance as float e.g. 0.1
- options: null
- keywords: null
""",
    "OPEN": """
- answer is a model answer paragraph (2-4 sentences)
- options: null
- keywords: null
- tolerance: null
""",
}

TYPE_BLOOM_GUIDANCE = {
    "MCQ": "Remember/Understand: prioritise recognition, identification, and basic interpretation.",
    "MULTI_MCQ": "Understand/Analyse: require evaluating each option and distinguishing related concepts.",
    "NUMERIC": "Apply: require procedure/formula execution, not just recalling a formula.",
    "SHORT": "Remember/Understand: require recall or concise concept explanation without options.",
    "OPEN": "Evaluate/Create: require justification, critique, or synthesis in a structured response.",
}

DIFFICULTY_LABELS = {
    1: "very easy — basic recall",
    2: "easy — straightforward understanding",
    3: "medium — application of concepts",
    4: "hard — analysis and synthesis",
    5: "very hard — evaluation and complex reasoning",
}

DIFFICULTY_TO_THINKING_LEVEL = {
    1: "low",
    2: "low",
    3: "medium",
    4: "high",
    5: "high",
}

FEASIBILITY_PROMPT = """Analyse this document and score (0.0-1.0) how suitable it is for generating each question type.

Scoring criteria:
- MCQ: factual statements with clear right/wrong answers, named concepts, definitions
- NUMERIC: contains numbers, formulas, measurements, calculations, statistics
- SHORT: key terms, definitions, named concepts suitable for short recall answers
- MULTI_MCQ: topics with multiple related correct facts or properties that can be enumerated
- OPEN: arguments, processes, explanations, comparisons requiring synthesis or evaluation

Return ONLY a valid JSON object, no markdown, no explanation:
{{"MCQ": 0.0, "NUMERIC": 0.0, "SHORT": 0.0, "MULTI_MCQ": 0.0, "OPEN": 0.0}}

Each value must be a float between 0.0 and 1.0.
"""


def is_retriable_error(exc: Exception) -> bool:
    message = str(exc).lower()
    retriable_markers = [
        "timeout",
        "temporar",
        "rate limit",
        "429",
        "503",
        "connection",
        "unavailable",
    ]
    return any(marker in message for marker in retriable_markers)


def hash_file(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def get_cached_uri(file_bytes: bytes) -> dict | None:
    key = hash_file(file_bytes)
    entry = file_uri_cache.get(key)
    if not entry:
        return None

    if time.time() > entry["expires"]:
        # cleanup of stale gemini files.
        stale_name = entry.get("name")
        file_uri_cache.pop(key, None)
        if stale_name:
            try:
                client.files.delete(name=stale_name)
                logger.info("gemini_cached_file_deleted_on_expiry name=%s", stale_name)
            except Exception:
                pass
        logger.info("gemini_uri_cache_expired key=%s", key[:12])
        return None

    return entry


def cache_uri(file_bytes: bytes, uri: str, name: str, mime: str) -> None:
    key = hash_file(file_bytes)
    file_uri_cache[key] = {
        "uri": uri,
        "name": name,
        "mime": mime,
        "expires": time.time() + FILE_URI_CACHE_TTL_SECONDS,
    }
    logger.info("gemini_uri_cached key=%s uri=%s", key[:12], uri)


def invalidate_cache(file_bytes: bytes) -> None:
    key = hash_file(file_bytes)
    file_uri_cache.pop(key, None)


async def run_with_retries(fn, operation_name: str):
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await asyncio.to_thread(fn)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= MAX_RETRIES or not is_retriable_error(exc):
                break
            sleep_seconds = RETRY_BASE_SECONDS * (2 ** (attempt - 1))
            logger.warning(
                "gemini_%s_retry attempt=%s/%s delay=%.1fs error=%s",
                operation_name,
                attempt,
                MAX_RETRIES,
                sleep_seconds,
                str(exc),
            )
            await asyncio.sleep(sleep_seconds)

    raise last_exc


async def wait_for_file_ready(uploaded_file, *, operation_prefix: str = "file"):
    max_polls = 15
    for _ in range(max_polls):
        if uploaded_file.state.name != "PROCESSING":
            break
        logger.info("gemini_%s_processing name=%s", operation_prefix, uploaded_file.name)
        await asyncio.sleep(1)
        uploaded_file = await run_with_retries(
            lambda: client.files.get(name=uploaded_file.name),
            f"{operation_prefix}_get",
        )

    if uploaded_file.state.name == "FAILED":
        raise ValueError("File processing failed on Gemini side.")

    return uploaded_file


async def generate_from_uri(
    file_uri: str,
    mime_type: str,
    topic_name: str,
    question_type: str,
    difficulty: int,
    count: int,
) -> list[dict]:
    prompt = QUESTION_GENERATION_PROMPT.format(
        n=count,
        q_type=question_type,
        topic_name=topic_name,
        difficulty=difficulty,
        difficulty_label=DIFFICULTY_LABELS.get(difficulty, "medium"),
        type_rules=TYPE_RULES.get(question_type, TYPE_RULES["MCQ"]),
        bloom_guidance=TYPE_BLOOM_GUIDANCE.get(question_type, TYPE_BLOOM_GUIDANCE["MCQ"]),
    )

    thinking_level = DIFFICULTY_TO_THINKING_LEVEL.get(difficulty, "medium")

    response = await run_with_retries(
        lambda: client.models.generate_content(
            model=MODEL,
            contents=[
                types.Part.from_uri(
                    file_uri=file_uri,
                    mime_type=mime_type,
                ),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.4,
                thinking_config=types.ThinkingConfig(thinking_level=thinking_level),
            ),
        ),
        "generate_content",
    )

    raw_text = getattr(response, "text", None)
    if not raw_text or not str(raw_text).strip():
        raise ValueError(f"AI returned an empty response for {question_type} d{difficulty}")

    raw = str(raw_text).strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    questions = json.loads(raw)
    if isinstance(questions, dict) and "questions" in questions:
        questions = questions["questions"]
    if not isinstance(questions, list):
        raise ValueError("AI did not return a JSON array")

    return questions


async def generate_all_questions(
    file_bytes: bytes,
    filename: str,
    mime_type: str,
    topic_name: str,
    requests: list[dict],
) -> list:
    """
    Upload file once, then execute all generation slices concurrently.
    Returns results aligned to requests (each item is list[dict] or Exception).
    """
    suffix = pathlib.Path(filename).suffix.lower()
    tmp_path = None
    uploaded_file_name = None
    used_cached_uri = False

    cached = get_cached_uri(file_bytes)
    if cached:
        logger.info("gemini_generation_cache_hit uri=%s", cached["uri"])
        file_uri = cached["uri"]
        uploaded_file_name = cached["name"]
        mime_type = cached["mime"]
        used_cached_uri = True
    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        uploaded_file = await run_with_retries(
            lambda: client.files.upload(
                file=tmp_path,
                config=types.UploadFileConfig(
                    mime_type=mime_type,
                    display_name=filename,
                ),
            ),
            "upload",
        )
        logger.info("gemini_file_uploaded name=%s uri=%s", uploaded_file.name, uploaded_file.uri)

        uploaded_file = await wait_for_file_ready(uploaded_file, operation_prefix="file")
        file_uri = uploaded_file.uri
        uploaded_file_name = uploaded_file.name

    try:
        async def generate_one(req: dict):
            return await generate_from_uri(
                file_uri=file_uri,
                mime_type=mime_type,
                topic_name=topic_name,
                question_type=req["type"],
                difficulty=req["difficulty"],
                count=req["count"],
            )

        return await asyncio.gather(
            *[generate_one(req) for req in requests],
            return_exceptions=True,
        )

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

        if uploaded_file_name and not used_cached_uri:
            invalidate_cache(file_bytes)
            try:
                await asyncio.to_thread(client.files.delete, name=uploaded_file_name)
                logger.info("gemini_file_deleted name=%s", uploaded_file_name)
            except Exception:
                pass


# ── Main generation function ─────────────────────────────────────────
async def generate_questions_from_file(
    file_bytes: bytes,
    filename: str,
    mime_type: str,
    topic_name: str,
    question_type: str,
    difficulty: int,
    count: int,
) -> list[dict]:
    """
    Uploads file to Gemini Files API and generates questions from it.
    Returns parsed list of question dicts ready for frontend review.
    """

    results = await generate_all_questions(
        file_bytes=file_bytes,
        filename=filename,
        mime_type=mime_type,
        topic_name=topic_name,
        requests=[
            {
                "type": question_type,
                "difficulty": difficulty,
                "count": count,
            }
        ],
    )

    result = results[0] if results else []
    if isinstance(result, Exception):
        raise result
    return result


# ── Feasibility scoring function ─────────────────────────────────────
async def score_document_feasibility(
    file_bytes: bytes,
    filename: str,
    mime_type: str,
) -> dict[str, float]:
    """
    Uploads file to Gemini and returns suitability scores (0.0-1.0) per question type.
    Falls back to neutral scores (0.5) on any error.
    """
    FALLBACK = {"MCQ": 0.5, "NUMERIC": 0.5, "SHORT": 0.5, "MULTI_MCQ": 0.5, "OPEN": 0.5}
    VALID_KEYS = {"MCQ", "NUMERIC", "SHORT", "MULTI_MCQ", "OPEN"}

    suffix = pathlib.Path(filename).suffix.lower()
    uploaded_file = None
    tmp_path = None

    cached = get_cached_uri(file_bytes)
    if cached:
        logger.info("gemini_feasibility_cache_hit uri=%s", cached["uri"])
        file_uri = cached["uri"]
        mime_type = cached["mime"]
    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        uploaded_file = await run_with_retries(
            lambda: client.files.upload(
                file=tmp_path,
                config=types.UploadFileConfig(mime_type=mime_type, display_name=filename),
            ),
            "feasibility_upload",
        )

        uploaded_file = await wait_for_file_ready(uploaded_file, operation_prefix="feasibility")
        file_uri = uploaded_file.uri
        cache_uri(file_bytes, uploaded_file.uri, uploaded_file.name, mime_type)

    try:
        response = await run_with_retries(
            lambda: client.models.generate_content(
                model=MODEL,
                contents=[
                    types.Part.from_uri(file_uri=file_uri, mime_type=mime_type),
                    FEASIBILITY_PROMPT,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0,
                ),
            ),
            "feasibility_generate",
        )

        raw = str(getattr(response, "text", "") or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        scores = json.loads(raw)
        if not isinstance(scores, dict) or not VALID_KEYS.issubset(scores.keys()):
            return FALLBACK

        # Clamp all values to [0.0, 1.0]
        return {k: float(max(0.0, min(1.0, scores[k]))) for k in VALID_KEYS}

    except Exception as exc:
        logger.warning("feasibility_scoring_failed error=%s", str(exc))
        return FALLBACK

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ── Post answer explanation ──────────────────────────────────────────

EXPLANATION_PROMPT = """You are a patient, expert tutor helping a student understand a quiz answer.

Question: {question_text}
Question type: {question_type}
Correct answer: {correct_answer}
Student's answer: {user_answer}
Student ability level: {ability_description}
Recent accuracy on this topic: {accuracy_description}

{type_specific_context}

Write a clear, detailed explanation of why the correct answer is right. Reference the student's specific answer to make it personal. Explain the underlying concept thoroughly enough that the student genuinely understands — not just what the answer is, but why.

Tone: encouraging, not condescending. Specific to THIS question. Do not just repeat the correct answer — explain WHY it is correct. Plain prose only, no bullet points or section headers.
"""

_TYPE_SPECIFIC_CONTEXT = {
    "MCQ":      "The student selected one option. Explain why their chosen option is wrong AND why the correct option is right.",
    "MULTI_MCQ":"The student selected multiple options. Address any options they incorrectly included or missed.",
    "NUMERIC":  "The student gave a numeric answer. If possible, explain where their calculation likely went wrong.",
    "SHORT":    "The student gave a short text answer. Explain the key concept they may have missed or misunderstood.",
    "OPEN":     "The student self-rated their answer. Explain the key points a strong answer should include.",
}

_ABILITY_DESCRIPTIONS = [
    (-1.0, "a beginner (theta < -1.0) who is new to this topic — keep explanations simple and concrete"),
    (0.0,  "a developing student (theta -1.0 to 0.0) with some foundational knowledge"),
    (1.0,  "an intermediate student (theta 0.0 to 1.0) with solid foundational knowledge"),
    (float("inf"), "an advanced student (theta > 1.0) — explanations can assume strong prior knowledge"),
]


def ability_description(theta: float) -> str:
    for threshold, label in _ABILITY_DESCRIPTIONS:
        if theta < threshold:
            return label
    return _ABILITY_DESCRIPTIONS[-1][1]


def format_user_answer(question: dict, user_answer: dict) -> str:
    q_type = question.get("type", "")
    options = question.get("options") or {}

    if q_type == "MCQ":
        key = str(user_answer.get("selected_option", "")).strip()
        value = options.get(key, "")
        return f"'{key}: {value}'" if value else f"'{key}'"

    if q_type == "MULTI_MCQ":
        keys = user_answer.get("selected_option") or []
        if isinstance(keys, str):
            keys = [keys]
        parts = [f"{k}: {options.get(k, '')}" for k in keys if k]
        return ", ".join(parts) or "No options selected"

    if q_type == "NUMERIC":
        return str(user_answer.get("selected_option", "No answer given"))

    if q_type in ("SHORT", "OPEN"):
        text = str(user_answer.get("selected_option", "")).strip()
        rating = user_answer.get("self_rating")
        if q_type == "OPEN" and rating is not None:
            return f"Self-rated {rating}/4. Answer: \"{text}\"" if text else f"Self-rated {rating}/4"
        return f'"{text}"' if text else "No answer given"

    return str(user_answer)


def format_correct_answer(question: dict) -> str:
    q_type = question.get("type", "")
    answer = question.get("answer")
    options = question.get("options") or {}

    if q_type == "MCQ" and options:
        key = str(answer or "").strip()
        return f"'{key}: {options.get(key, '')}'"

    if q_type == "MULTI_MCQ" and options and isinstance(answer, list):
        return ", ".join(f"{k}: {options.get(k, '')}" for k in answer)

    if q_type == "SHORT":
        keywords = question.get("keywords") or []
        kw_str = ", ".join(keywords) if keywords else ""
        return f'"{answer}" (key concepts: {kw_str})' if kw_str else f'"{answer}"'

    return "" if answer is None else str(answer)


async def generate_explanation(
    question: dict,
    user_answer: dict,
    theta: float,
    recent_accuracy: float | None,
) -> dict:
    """
    Generates a personalised explanation for why an answer is correct/incorrect.
    Returns a dict with key: explanation.
    """
    accuracy_description = (
        f"{round(recent_accuracy * 100)}% correct on recent questions in this topic"
        if recent_accuracy is not None
        else "first few attempts on this topic"
    )

    prompt = EXPLANATION_PROMPT.format(
        question_text=question.get("text", ""),
        question_type=question.get("type", ""),
        correct_answer=format_correct_answer(question),
        user_answer=format_user_answer(question, user_answer),
        ability_description=ability_description(theta),
        accuracy_description=accuracy_description,
        type_specific_context=_TYPE_SPECIFIC_CONTEXT.get(question.get("type", ""), ""),
    )

    response = await run_with_retries(
        lambda: client.models.generate_content(
            model=MODEL,
            contents=[prompt],
            config=types.GenerateContentConfig(
                temperature=0.5,
                thinking_config=types.ThinkingConfig(),
            ),
        ),
        "explanation_generate",
    )

    text = str(getattr(response, "text", "") or "").strip()
    return {"explanation": text or "No explanation available."}


# ── Contextual chat ──────────────────────────────────────────────────

CHAT_SYSTEM_PROMPT = """You are a patient, knowledgeable tutor helping a student understand a specific question they just answered.

Question context:
  Question: {question_text}
  Correct answer: {correct_answer}
  Student's answer: {user_answer}
  Student level: {ability_description}

Your role:
- Answer the student's follow-up questions about THIS question and the concepts it covers
- Keep answers concise — 2 to 4 sentences unless the student asks for more detail
- Use plain language appropriate to the student's level
- If the student asks something unrelated to this question or topic, gently redirect them back
- Never just give answers to other questions — you are here to help them understand, not to do their work for them
- Respond naturally, like a tutor would in person
"""


async def generate_chat_reply(
    question: dict,
    user_answer: dict,
    theta: float,
    history: list[dict],
    new_message: str,
) -> str:
    """
    Generates a conversational reply in the context of a specific question.
    Maintains full conversation history for coherent multi-turn dialogue.
    """
    system_prompt = CHAT_SYSTEM_PROMPT.format(
        question_text=question.get("text", ""),
        correct_answer=format_correct_answer(question),
        user_answer=format_user_answer(question, user_answer),
        ability_description=ability_description(theta),
    )

    # Build alternating-turn prompt for Gemini
    parts = [system_prompt]
    for msg in history:
        if msg["role"] == "user":
            parts.append(f"Student: {msg['content']}")
        else:
            parts.append(f"Tutor: {msg['content']}")
    parts.append(f"Student: {new_message}")
    parts.append("Tutor:")

    full_prompt = "\n\n".join(parts)

    response = await run_with_retries(
        lambda: client.models.generate_content(
            model=MODEL,
            contents=[full_prompt],
            config=types.GenerateContentConfig(
                temperature=0.6,
                thinking_config=types.ThinkingConfig(thinking_level="low"),
            ),
        ),
        "chat_generate",
    )

    reply = str(getattr(response, "text", "") or "").strip()
    if reply.lower().startswith("tutor:"):
        reply = reply[6:].strip()

    return reply if reply else "I'm not sure about that — could you rephrase?"