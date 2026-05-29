from app.utils.math_text import normalize_math_delimiters, normalize_question_math_fields


def test_normalize_math_delimiters_prefers_explicit_delimiters():
    text = "Compute $x+1$ and $$y=mx+b$$. Price is $20$."
    out = normalize_math_delimiters(text)

    assert "\\(x+1\\)" in out
    assert "\\[y=mx+b\\]" in out
    # Currency-like value should not be converted.
    assert "$20$" in out


def test_normalize_question_math_fields_applies_to_strings_only():
    text, options, answer, explanation = normalize_question_math_fields(
        "SHORT",
        "Find $x$.",
        {"A": "Use $x+1$", "B": "No math"},
        "$x$",
        "Because $$x=2$$",
    )

    assert text == "Find \\(x\\)."
    assert options["A"] == "Use \\(x+1\\)"
    assert options["B"] == "No math"
    assert answer == "\\(x\\)"
    assert explanation == "Because \\[x=2\\]"
