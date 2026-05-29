import re
from typing import Any


def _looks_like_math(expr: str) -> bool:
    value = (expr or "").strip()
    if not value:
        return False

    # Avoid converting common currency-like values such as $20$.
    if re.fullmatch(r"\d+(?:[.,]\d+)?", value):
        return False

    if "\\" in value:
        return True

    if re.search(r"[\^_{}=+\-*/()\[\]<>]", value):
        return True

    # Treat single-letter variables as math.
    if re.fullmatch(r"[A-Za-z]", value):
        return True

    if re.search(r"\d", value) and re.search(r"[A-Za-z]", value):
        return True

    if re.search(r"\b(sin|cos|tan|log|ln|sqrt|frac|alpha|beta|gamma|theta|pi)\b", value, re.IGNORECASE):
        return True

    return False


def normalize_math_delimiters(text: str) -> str:
    r"""
    Canonicalize LaTeX delimiters to:
    - inline: \(...\)
    - block:  \[...\]

    Keeps non-math $...$ content unchanged to reduce false positives.
    """
    if not isinstance(text, str) or not text:
        return text

    normalized = text

    # 1) Convert $$...$$ -> \[...\]
    normalized = re.sub(r"\$\$([\s\S]+?)\$\$", lambda m: f"\\[{m.group(1).strip()}\\]", normalized)

    # 2) Convert likely-math $...$ -> \(...\)
    def replace_inline(match: re.Match[str]) -> str:
        inner = match.group(1)
        if _looks_like_math(inner):
            return f"\\({inner.strip()}\\)"
        return match.group(0)

    normalized = re.sub(r"(?<!\\)\$([^$\n]+?)(?<!\\)\$", replace_inline, normalized)
    return normalized


def normalize_question_math_fields(question_type: str, text: Any, options: Any, answer: Any, explanation: Any):
    normalized_text = normalize_math_delimiters(text) if isinstance(text, str) else text

    normalized_options = options
    if isinstance(options, dict):
        normalized_options = {
            key: normalize_math_delimiters(value) if isinstance(value, str) else value
            for key, value in options.items()
        }

    normalized_answer = answer
    if question_type in {"SHORT", "OPEN"} and isinstance(answer, str):
        normalized_answer = normalize_math_delimiters(answer)

    normalized_explanation = normalize_math_delimiters(explanation) if isinstance(explanation, str) else explanation

    return normalized_text, normalized_options, normalized_answer, normalized_explanation
