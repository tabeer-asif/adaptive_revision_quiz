from app.services.irt import default_grm_thresholds
from app.services.irt import score_multi_mcq


def coerce_to_string_set(value):
    if value is None:
        return set()

    if isinstance(value, (list, tuple, set)):
        return {str(item).strip() for item in value if str(item).strip()}

    cleaned = str(value).strip()
    return {cleaned} if cleaned else set()


def format_response_for_eap(question, question_type, score, correct):
    a = float(question.get("irt_a") or 1.0)
    b = float(question.get("irt_b") or 0.0)

    if question_type == "MCQ":
        return {
            "item_type": "3pl",
            "correct": bool(correct),
            "a": a,
            "b": b,
            "c": float(question.get("irt_c") or 0.25),
        }

    if question_type == "MULTI_MCQ":
        thresholds = question.get("irt_thresholds") or default_grm_thresholds(b)
        category = 2 if score == 1.0 else 1 if score >= 0.5 else 0
        return {
            "item_type": "grm",
            "score": category,
            "a": a,
            "b_list": list(thresholds),
        }

    return {
        "item_type": "2pl",
        "correct": bool(correct),
        "a": a,
        "b": b,
    }


def load_topic_response_history(db, user_id: str, topic_id: int) -> list[dict]:
    logs_resp = db.table("review_logs") \
        .select("question_id, selected_option, correct, created_at") \
        .eq("user_id", user_id) \
        .eq("topic_id", topic_id) \
        .order("created_at") \
        .execute()

    logs = logs_resp.data or []
    if not logs:
        return []

    question_ids = [row["question_id"] for row in logs if row.get("question_id") is not None]
    if not question_ids:
        return []

    questions_resp = db.table("questions") \
        .select("id, type, answer, irt_a, irt_b, irt_c, irt_thresholds") \
        .in_("id", question_ids) \
        .execute()

    question_map = {row["id"]: row for row in (questions_resp.data or []) if row.get("id") is not None}

    responses = []
    for row in logs:
        question = question_map.get(row.get("question_id"))
        if not question:
            continue

        question_type = question.get("type")
        if question_type == "MCQ":
            responses.append({
                "item_type": "3pl",
                "correct": bool(row.get("correct")),
                "a": float(question.get("irt_a") or 1.0),
                "b": float(question.get("irt_b") or 0.0),
                "c": float(question.get("irt_c") or 0.25),
            })
        elif question_type == "MULTI_MCQ":
            selected_set = coerce_to_string_set(row.get("selected_option"))
            correct_set = coerce_to_string_set(question.get("answer"))
            score = score_multi_mcq(selected_set, correct_set)
            category = 2 if score == 1.0 else 1 if score >= 0.5 else 0
            thresholds = question.get("irt_thresholds") or default_grm_thresholds(float(question.get("irt_b") or 0.0))
            responses.append({
                "item_type": "grm",
                "score": category,
                "a": float(question.get("irt_a") or 1.0),
                "b_list": list(thresholds),
            })
        else:
            responses.append({
                "item_type": "2pl",
                "correct": bool(row.get("correct")),
                "a": float(question.get("irt_a") or 1.0),
                "b": float(question.get("irt_b") or 0.0),
            })

    return responses