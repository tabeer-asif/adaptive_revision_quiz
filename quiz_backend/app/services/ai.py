# app/services/ai.py

from google import genai
from google.genai import types
import json
import tempfile
import os
import pathlib
import hashlib
import time
import re
from app.config import settings
import asyncio
import logging
from app.supabase_client import supabase_db
import time

logger = logging.getLogger(__name__)

# ── Initialise client lazily so import succeeds without an API key ──
_client: "genai.Client | None" = None
MODEL = "gemini-3.5-flash"


def _get_client() -> "genai.Client":
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


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
- Base questions ONLY on substantive content found in the document (concepts, facts, processes, principles, calculations)
- Do not invent facts not present in the material
- Spread questions across different sections and topics of the document — do NOT draw all questions from the same passage or page. Cover early, middle, and late portions of the material.
- Each question must test a DIFFERENT concept, fact, or skill — do NOT ask two questions that are essentially the same topic rephrased at different difficulty levels
- Do NOT ask about document metadata: never ask who wrote or authored the document, what the course code or course name is, what institution it belongs to, what year it was published, or anything else that is administrative/bibliographic rather than educational content
- Match the difficulty level strictly
- Write question text as standalone, self contained questions - do NOT use phrases like "according to the document", "based on the material", "from the study material", "in the text", "as mentioned", or any reference to a document/material/resource. The student will not have access to the source material during the quiz.
- For any mathematical expressions, formulas, symbols or units use LaTeX delimiters: \\(...\\) for inline math, \\[...\\] for display/block equations

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
- keywords: array of 3-8 accepted answer aliases only
- Every keyword must be a response that should be marked correct on its own
- Include the exact answer, spelling/spacing/hyphenation variants, abbreviations, and full synonyms only if they are fully acceptable answers
- Include a single-word alias only when that single word alone is sufficient as a correct answer
- Do NOT include context words, topic words, hints, or incomplete fragments that should not pass on their own
- options: null
- tolerance: null
""",
    "NUMERIC": """
- answer must be a number (integer or float) e.g. 9.81
- tolerance: suggest appropriate tolerance as float e.g. 0.1
- options: null
- keywords: null
- Use LaTeX delimiters \\(...\\) for any formulas, symbols, or units in the question text e.g. \\(F = ma\\), \\(9.81\\, \\text{m/s}^2\\)
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


TOPIC_SUGGESTION_PROMPT = """
Given generated quiz question texts and a list of existing topics, choose up to {limit} best-matching topics.

Return ONLY valid JSON as an array with this shape:
[
    {{"topic_id": 12, "confidence": 0.82}},
    {{"topic_id": 4, "confidence": 0.63}}
]

Rules:
- Use ONLY topic IDs from the provided list.
- Confidence must be float between 0.0 and 1.0.
- Sort by confidence descending.
- If nothing matches well, return []

Topics:
{topics_json}

Generated question texts:
{questions_json}
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
                _get_client().files.delete(name=stale_name)
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
            lambda: _get_client().files.get(name=uploaded_file.name),
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
        lambda: _get_client().models.generate_content(
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
                temperature=1.0,
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
            lambda: _get_client().files.upload(
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
                await asyncio.to_thread(_get_client().files.delete, name=uploaded_file_name)
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
            lambda: _get_client().files.upload(
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
            lambda: _get_client().models.generate_content(
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


async def suggest_topics_from_questions(
    question_texts: list[str],
    topics: list[dict],
    limit: int = 3,
) -> list[dict]:
    """
    Suggest matching existing topics for generated questions.
    Returns [{topic_id, topic_name, confidence, source}, ...].
    """
    if not question_texts or not topics:
        return []

    topic_map = {
        int(t["id"]): str(t.get("name") or "")
        for t in topics
        if isinstance(t, dict) and t.get("id") is not None
    }
    if not topic_map:
        return []

    prompt = TOPIC_SUGGESTION_PROMPT.format(
        limit=max(1, min(5, int(limit or 3))),
        topics_json=json.dumps(
            [{"id": tid, "name": name} for tid, name in topic_map.items()],
            ensure_ascii=True,
        ),
        questions_json=json.dumps(question_texts[:20], ensure_ascii=True),
    )

    try:
        response = await run_with_retries(
            lambda: _get_client().models.generate_content(
                model=MODEL,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2,
                ),
            ),
            "topic_suggest_generate",
        )

        raw = str(getattr(response, "text", "") or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            return []

        output = []
        seen = set()
        for item in parsed:
            if not isinstance(item, dict):
                continue
            try:
                topic_id = int(item.get("topic_id"))
            except (TypeError, ValueError):
                continue
            if topic_id not in topic_map or topic_id in seen:
                continue
            seen.add(topic_id)

            try:
                confidence = float(item.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            confidence = max(0.0, min(1.0, confidence))

            output.append(
                {
                    "topic_id": topic_id,
                    "topic_name": topic_map[topic_id],
                    "confidence": round(confidence, 3),
                    "source": "ai",
                }
            )

        output.sort(key=lambda x: x["confidence"], reverse=True)
        return output[: max(1, min(5, int(limit or 3)))]

    except Exception:
        # Safe fallback: lexical overlap on topic-name tokens against question text.
        joined = " ".join(question_texts).lower()
        q_tokens = {t for t in re.findall(r"[a-z0-9]+", joined) if len(t) >= 3}
        scored = []
        for topic_id, name in topic_map.items():
            t_tokens = {t for t in re.findall(r"[a-z0-9]+", name.lower()) if len(t) >= 3}
            if not t_tokens:
                continue
            overlap = len(q_tokens & t_tokens)
            score = overlap / len(t_tokens)
            if score > 0:
                scored.append((score, topic_id, name))

        scored.sort(reverse=True)
        return [
            {
                "topic_id": topic_id,
                "topic_name": name,
                "confidence": round(float(score), 3),
                "source": "lexical",
            }
            for score, topic_id, name in scored[: max(1, min(5, int(limit or 3)))]
        ]


NEW_TOPIC_SUGGESTION_PROMPT = """You are helping a student organise their quiz questions into topics.

Given these quiz question texts, suggest up to {limit} short, descriptive topic names that would work well as category labels.

Rules:
- Each name must be 1-4 words, title-case (e.g. "Cell Biology", "Quantum Mechanics", "The French Revolution")
- Do NOT suggest names identical or very similar to these existing topics: {existing_json}
- Prefer specific names over generic ones ("Photosynthesis" is better than "Biology")
- If questions span multiple distinct subjects, suggest one name per subject
- Return ONLY a valid JSON array of strings, no explanation, no markdown

Question texts:
{questions_json}
"""


async def suggest_new_topic_names(
    question_texts: list[str],
    existing_names: list[str],
    limit: int = 4,
) -> list[str]:
    """
    Ask the AI to propose brand-new topic name strings derived from the question content.
    Returns a list of plain-string topic names (no IDs).
    Falls back to an empty list on any error so the generate endpoint always succeeds.
    """
    if not question_texts:
        return []

    safe_limit = max(1, min(6, int(limit or 4)))
    existing_lower = {n.lower().strip() for n in existing_names if n}

    prompt = NEW_TOPIC_SUGGESTION_PROMPT.format(
        limit=safe_limit,
        existing_json=json.dumps(existing_names or [], ensure_ascii=True),
        questions_json=json.dumps(question_texts[:20], ensure_ascii=True),
    )

    try:
        response = await run_with_retries(
            lambda: _get_client().models.generate_content(
                model=MODEL,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.3,
                ),
            ),
            "new_topic_name_suggest",
        )

        raw = str(getattr(response, "text", "") or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            return []

        output: list[str] = []
        seen: set[str] = set()
        for item in parsed:
            if isinstance(item, str):
                name = item.strip()
            elif isinstance(item, dict):
                name = str(item.get("name", "")).strip()
            else:
                continue

            if not name:
                continue
            lower = name.lower()
            if lower in existing_lower or lower in seen:
                continue
            seen.add(lower)
            output.append(name)
            if len(output) >= safe_limit:
                break

        return output

    except Exception:
        return []


# ------- Post answer explanation -------

EXPLANATION_PROMPT = """You are a patient, expert tutor helping a student understand a quiz answer.

Question: {question_text}
Question type: {question_type}
Correct answer: {correct_answer}
Student's answer: {user_answer}
Student ability level: {ability_description}
Recent accuracy on this topic: {accuracy_description}

{type_specific_context}

Write a concise explanation in bullet points so it is quick to read.

Output rules:
- 3 to 5 bullet points only
- Each bullet must be one short sentence (max about 16 words)
- Start each bullet with "- "
- Keep total response under 90 words
- Mention the student's answer briefly
- Explain WHY the correct answer is right (not just what it is)
- No headings, no intro/outro, no markdown code blocks

Tone: encouraging, not condescending. Specific to THIS question.
"""

_TYPE_SPECIFIC_CONTEXT = {
    "MCQ":      "The student selected one option. Explain why their chosen option is wrong AND why the correct option is right.",
    "MULTI_MCQ":"The student selected multiple options. Address any options they incorrectly included or missed.",
    "NUMERIC":  "The student gave a numeric answer. If possible, explain where their calculation likely went wrong.",
    "SHORT":    "The student gave a short text answer. Explain the key concept they may have missed or misunderstood.",
    "OPEN":     "The student self-rated their answer. Explain the key points a strong answer should include.",
}

_ABILITY_DESCRIPTIONS = [
    (-1.0, "a beginner (theta < -1.0) who is new to this topic - keep explanations simple and concrete"),
    (0.0,  "a developing student (theta -1.0 to 0.0) with some foundational knowledge"),
    (1.0,  "an intermediate student (theta 0.0 to 1.0) with solid foundational knowledge"),
    (float("inf"), "an advanced student (theta > 1.0) - explanations can assume strong prior knowledge"),
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


def format_correct_answer_for_prompt(question: dict) -> str:
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
        correct_answer=format_correct_answer_for_prompt(question),
        user_answer=format_user_answer(question, user_answer),
        ability_description=ability_description(theta),
        accuracy_description=accuracy_description,
        type_specific_context=_TYPE_SPECIFIC_CONTEXT.get(question.get("type", ""), ""),
    )

    response = await run_with_retries(
        lambda: _get_client().models.generate_content(
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


# ------ Contextual chat ------

CHAT_SYSTEM_PROMPT = """You are a patient, knowledgeable tutor helping a student understand a specific question they just answered.

Question context:
  Question: {question_text}
  Correct answer: {correct_answer}
  Student's answer: {user_answer}
  Student level: {ability_description}
{feedback_context}

Your role:
- Answer the student's follow-up questions about THIS question and the concepts it covers
- Keep answers concise — 2 to 4 sentences unless the student asks for more detail
- Use plain language appropriate to the student's level
- If feedback context is present, do not mention it unless the student asks about feedback/hint/gaps/confusion explicitly
- If the student asks something unrelated to this question or topic, gently redirect them back
- Never just give answers to other questions — you are here to help them understand, not to do their work for them
- Respond naturally, like a tutor would in person
"""


OPEN_FEEDBACK_PROMPT_TEMPLATE = """
You are a helpful computer science tutor giving feedback on a student's answer.

Question: {question}

Model Answer: {model_answer}

Student Answer: {student_answer}

Instructions:
- Do NOT score or grade the answer
- Do NOT say whether the answer is correct or incorrect explicitly
- Focus purely on constructive, encouraging feedback
- Compare the student's answer conceptually to the model answer
- Identify key concepts they captured well
- Identify key concepts they missed or explained poorly
- Keep feedback concise (3-5 sentences max)
- Use simple, friendly language appropriate for a student
- Do NOT reveal the full model answer

Respond in this exact JSON format:
{{
    "strengths": "<what the student explained well, be specific>",
    "gaps": "<key concepts missing or incorrectly explained>",
    "hint": "<a nudge towards what they missed, without giving it away>",
    "encouragement": "<one short motivational sentence>"
}}
"""


def build_open_feedback_prompt(question: str, model_answer: str, student_answer: str) -> str:
    return OPEN_FEEDBACK_PROMPT_TEMPLATE.format(
        question=question,
        model_answer=model_answer,
        student_answer=student_answer,
    )


def _strip_json_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        while lines and lines[-1].strip() == "```":
            lines.pop()
        text = "\n".join(lines).strip()

    if text.lower().startswith("json"):
        text = text[4:].strip()

    return text


SESSION_FEEDBACK_PROMPT_TEMPLATE = """
You are a helpful tutor writing a short post-session summary for a student.
Use the current session and historical context below to describe progress in plain language.

CURRENT SESSION
- Questions answered: {questions_answered}
- Accuracy: {accuracy}
- Again ratings: {again_ratings}
- Final ability estimate: {final_theta}
- Termination reason: {termination_reason}

HISTORICAL CONTEXT
- Prior sessions on this topic: {prior_sessions}
- Overall ability trend: {theta_trend}
- Ability change across prior sessions: {theta_delta_total}
- Calibration status: {calibration_status}
- Persistent weak questions:
{weak_questions}

Instructions:
- Write a concise, encouraging summary
- Mention what improved or stayed strong this session
- Reference the historical trend when useful
- Mention persistent weaknesses without sounding negative
- End with one specific action for next session
- Do not use technical terms like theta, FSRS, posterior_sd, or calibration

Return only valid JSON with this exact shape:
{{
    "headline": "<one sentence summary>",
    "strengths": "<what went well, referencing history if relevant>",
    "weaknesses": "<persistent or new weak areas>",
    "trend": "<overall progress narrative across sessions>",
    "action": "<one specific thing to focus on next>"
}}
"""


SESSION_FEEDBACK_MAX_HISTORY_SESSIONS = 5
SESSION_FEEDBACK_MAX_WEAK_QUESTIONS = 3
SESSION_FEEDBACK_TIMEOUT_SECONDS = 300  


def _safe_text(value: object) -> str:
    return str(value or "").strip()


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _format_ratio(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.0%}"


def _format_number(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int):
        return str(value)
    return f"{value:.2f}"


def _build_session_feedback_context(
    session_row: dict,
    review_logs: list[dict],
    history_rows: list[dict],
    weak_questions: list[dict],
    theta_row: dict | None,
) -> dict:
    accuracies = [1.0 if bool(row.get("correct")) else 0.0 for row in review_logs]
    again_ratings = sum(1 for row in review_logs if row.get("fsrs_rating") == 1)
    response_times = [float(row["response_time"]) for row in review_logs if isinstance(row.get("response_time"), (int, float))]

    current_accuracy = _mean(accuracies)
    current_avg_response_time = _mean(response_times)

    theta_values = [float(row["final_theta"]) for row in history_rows if isinstance(row.get("final_theta"), (int, float))]
    theta_delta_total = None
    theta_trend = "stable"
    if theta_values:
        theta_delta_total = theta_values[-1] - theta_values[0] if len(theta_values) > 1 else theta_values[0]
        if theta_delta_total > 0.1:
            theta_trend = "improving"
        elif theta_delta_total < -0.1:
            theta_trend = "declining"

    calibration_status = "unknown"
    if isinstance(theta_row, dict):
        if theta_row.get("is_calibrated"):
            calibration_status = "calibrated"
        else:
            calibration_status = "still calibrating"

    weak_question_lines = []
    for question in weak_questions[:SESSION_FEEDBACK_MAX_WEAK_QUESTIONS]:
        weak_question_lines.append(
            f'- {question.get("text") or "Question"} (accuracy: {_format_ratio(question.get("accuracy"))}, seen in {question.get("sessions_seen_in", 0)} sessions)'
        )
    if not weak_question_lines:
        weak_question_lines = ["- None identified yet"]

    history_summary_lines = []
    for row in history_rows[:SESSION_FEEDBACK_MAX_HISTORY_SESSIONS]:
        history_summary_lines.append(
            f'- session {row.get("id")}: accuracy {_format_ratio(row.get("accuracy"))}, final ability {_format_number(row.get("final_theta"))}, questions {row.get("questions_answered", 0)}'
        )
    if not history_summary_lines:
        history_summary_lines = ["- This is the first recorded session for this topic."]

    return {
        "questions_answered": len(review_logs) if review_logs else int(session_row.get("questions_answered") or 0),
        "accuracy": _format_ratio(current_accuracy),
        "avg_response_time": _format_number(current_avg_response_time),
        "again_ratings": again_ratings,
        "final_theta": _format_number(session_row.get("final_theta")),
        "termination_reason": _safe_text(session_row.get("termination_reason")) or "unknown",
        "prior_sessions": "\n".join(history_summary_lines),
        "theta_trend": theta_trend,
        "theta_delta_total": _format_number(theta_delta_total),
        "calibration_status": calibration_status,
        "weak_questions": "\n".join(weak_question_lines),
    }


def _format_weak_question_stats(question_id: int | None, rows: list[dict], question_lookup: dict[int, dict]) -> dict:
    attempts = len(rows)
    if attempts == 0 or question_id is None:
        return {}

    correct_count = sum(1 for row in rows if bool(row.get("correct")))
    session_ids = {row.get("session_id") for row in rows if row.get("session_id") is not None}
    return {
        "question_id": question_id,
        "text": _safe_text(question_lookup.get(question_id, {}).get("text") or question_lookup.get(question_id, {}).get("question_text") or f"Question {question_id}"),
        "type": _safe_text(question_lookup.get(question_id, {}).get("type")),
        "attempts": attempts,
        "accuracy": correct_count / attempts,
        "sessions_seen_in": len(session_ids),
        "again_ratings": sum(1 for row in rows if row.get("fsrs_rating") == 1),
        "last_attempted": rows[-1].get("created_at"),
    }


async def generate_session_feedback(
    session_row: dict,
    user_id: str,
    timeout_seconds: float = SESSION_FEEDBACK_TIMEOUT_SECONDS,
) -> dict[str, str] | None:

    session_id = session_row.get("id")
    topic_id = session_row.get("topic_id")

    review_logs_res = (
        supabase_db.table("review_logs")
        .select("session_id,question_id,correct,response_time,fsrs_rating,created_at")
        .eq("user_id", user_id)
        .eq("session_id", session_id)
        .order("created_at")
        .execute()
    )
    review_logs = review_logs_res.data or []

    theta_row = None
    if topic_id is not None:
        theta_res = (
            supabase_db.table("user_topic_theta")
            .select("theta,posterior_sd,n_responses,is_calibrated,last_updated")
            .eq("user_id", user_id)
            .eq("topic_id", topic_id)
            .execute()
        )
        theta_row = theta_res.data[0] if theta_res.data else None

    history_rows = []
    history_query_builder = (
        supabase_db.table("sessions")
        .select("id,topic_id,started_at,ended_at,final_theta,questions_answered,termination_reason")
        .eq("user_id", user_id)
        .order("started_at", desc=True)
        .limit(20)
    )
    if topic_id is not None:
        history_query_builder = history_query_builder.eq("topic_id", topic_id)

    history_query = history_query_builder.execute()
    for row in (history_query.data or []):
        if row.get("id") == session_id:
            continue
        history_rows.append(row)
        if len(history_rows) >= SESSION_FEEDBACK_MAX_HISTORY_SESSIONS:
            break

    weak_questions: list[dict] = []
    if topic_id is not None:
        topic_logs_res = (
            supabase_db.table("review_logs")
            .select("question_id,session_id,correct,fsrs_rating,created_at")
            .eq("user_id", user_id)
            .eq("topic_id", topic_id)
            .order("created_at")
            .execute()
        )
        topic_logs = topic_logs_res.data or []
        grouped_logs: dict[int, list[dict]] = {}
        for row in topic_logs:
            question_id = row.get("question_id")
            if question_id is None:
                continue
            grouped_logs.setdefault(int(question_id), []).append(row)

        question_ids = list(grouped_logs.keys())
        question_lookup: dict[int, dict] = {}
        if question_ids:
            questions_res = (
                supabase_db.table("questions")
                .select("id,text,type")
                .in_("id", question_ids)
                .execute()
            )
            question_lookup = {
                int(row["id"]): row
                for row in (questions_res.data or [])
                if row.get("id") is not None
            }

        for question_id, rows in grouped_logs.items():
            attempts = len(rows)
            if attempts < 2:
                continue
            correct_count = sum(1 for row in rows if bool(row.get("correct")))
            accuracy = correct_count / attempts if attempts else 0.0
            if accuracy >= 0.5:
                continue
            stats = _format_weak_question_stats(question_id, rows, question_lookup)
            if stats:
                weak_questions.append(stats)

        weak_questions.sort(key=lambda row: (row["accuracy"], row["attempts"], row["sessions_seen_in"]))

    context = _build_session_feedback_context(
        session_row=session_row,
        review_logs=review_logs,
        history_rows=history_rows,
        weak_questions=weak_questions,
        theta_row=theta_row,
    )

    prompt = SESSION_FEEDBACK_PROMPT_TEMPLATE.format(**context)

    try:
        response = await asyncio.wait_for(
            run_with_retries(
                lambda: _get_client().models.generate_content(
                    model=MODEL,
                    contents=[prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.4,
                        thinking_config=types.ThinkingConfig(thinking_level="low"),
                    ),
                ),
                "session_feedback_generate",
            ),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        logger.warning("gemini_session_feedback_timeout session_id=%s elapsed=%.1fs timeout=%.1fs", session_id, elapsed, timeout_seconds)
        raise TimeoutError("AI session feedback generation timed out") from exc

    raw = str(getattr(response, "text", "") or "").strip()
    cleaned = _strip_json_fence(raw)
    parsed = json.loads(cleaned)

    if not isinstance(parsed, dict):
        raise ValueError("AI did not return a JSON object")

    feedback = {
        "headline": _safe_text(parsed.get("headline")),
        "strengths": _safe_text(parsed.get("strengths")),
        "weaknesses": _safe_text(parsed.get("weaknesses")),
        "trend": _safe_text(parsed.get("trend")),
        "action": _safe_text(parsed.get("action")),
    }

    if not all(feedback.values()):
        raise ValueError("AI session feedback JSON missing required fields")

    return feedback


async def generate_open_feedback(
    question_text: str,
    model_answer: str,
    student_answer: str,
    timeout_seconds: float = 30.0,
) -> dict[str, str]:
    start_time = time.time()
    
    prompt = build_open_feedback_prompt(
        question=question_text,
        model_answer=model_answer,
        student_answer=student_answer,
    )

    try:
        response = await asyncio.wait_for(
            run_with_retries(
                lambda: _get_client().models.generate_content(
                    model=MODEL,
                    contents=[prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.4,
                        thinking_config=types.ThinkingConfig(thinking_level="low"),
                    ),
                ),
                "open_feedback_generate",
            ),
            timeout=timeout_seconds,
        )
        elapsed = time.time() - start_time
        logger.info("gemini_open_feedback_success elapsed=%.1fs", elapsed)
    except asyncio.TimeoutError as exc:
        elapsed = time.time() - start_time
        logger.warning("gemini_open_feedback_timeout elapsed=%.1fs timeout=%.1fs", elapsed, timeout_seconds)
        raise TimeoutError("AI feedback generation timed out") from exc

    raw = str(getattr(response, "text", "") or "").strip()
    cleaned = _strip_json_fence(raw)
    parsed = json.loads(cleaned)

    if not isinstance(parsed, dict):
        raise ValueError("AI did not return a JSON object")

    def _to_text(key: str) -> str:
        value = parsed.get(key)
        if value is None:
            return ""
        return str(value).strip()

    feedback = {
        "strengths": _to_text("strengths"),
        "gaps": _to_text("gaps"),
        "hint": _to_text("hint"),
        "encouragement": _to_text("encouragement"),
    }

    if not all(feedback.values()):
        raise ValueError("AI feedback JSON missing required fields")

    return feedback


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
    open_feedback = user_answer.get("open_feedback") if isinstance(user_answer, dict) else None
    feedback_context = ""
    if isinstance(open_feedback, dict):
        strengths = str(open_feedback.get("strengths") or "").strip()
        gaps = str(open_feedback.get("gaps") or "").strip()
        hint = str(open_feedback.get("hint") or "").strip()
        encouragement = str(open_feedback.get("encouragement") or "").strip()

        if strengths or gaps or hint or encouragement:
            feedback_context = (
                "  Feedback given to student:\n"
                f"    strengths: {strengths}\n"
                f"    gaps: {gaps}\n"
                f"    hint: {hint}\n"
                f"    encouragement: {encouragement}"
            )

    system_prompt = CHAT_SYSTEM_PROMPT.format(
        question_text=question.get("text", ""),
        correct_answer=format_correct_answer_for_prompt(question),
        user_answer=format_user_answer(question, user_answer),
        ability_description=ability_description(theta),
        feedback_context=feedback_context,
    )

    # Build alternating turn prompt 
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
        lambda: _get_client().models.generate_content(
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