# app/routes/quiz.py
from fastapi import APIRouter, HTTPException, Depends
from app.dependencies.auth import get_current_user
from app.supabase_client import supabase_db
from datetime import datetime, timezone
import json
from app.schemas.quiz import SubmitAnswerRequest
from fsrs import Card, Rating, Scheduler, State
from app.services.irt import (
    eap_estimate,
    get_fsrs_rating, 
    score_mcq, 
    score_multi_mcq,
    score_numeric,
    score_short,

)
from app.services.learner_eap import (
    format_response_for_eap,
    load_topic_response_history,
)
from app.utils.quiz_validation import (
    validate_question_exists,
    validate_answer_submitted,
    validate_mcq_selection,
    validate_multi_mcq_selection,
    validate_multi_mcq_db_answer,
    validate_numeric_selection,
    validate_numeric_db_answer,
    validate_numeric_tolerance,
    validate_short_text,
    validate_open_text
)
 

router = APIRouter()
scheduler = Scheduler() #FSRS scheduler


def format_correct_answer(question_type, db_answer, options):
    if question_type == "MCQ":
        key = str(db_answer).strip() if db_answer is not None else ""
        if options and key in options:
            return f"{key}: {options[key]}"
        return key

    if question_type == "MULTI_MCQ":
        if not isinstance(db_answer, list):
            return ""

        labels = []
        for raw_key in db_answer:
            key = str(raw_key).strip()
            if not key:
                continue
            if options and key in options:
                labels.append(f"{key}: {options[key]}")
            else:
                labels.append(key)
        return ", ".join(labels)

    return "" if db_answer is None else str(db_answer)


def _normalize_short_keywords(raw_keywords) -> list[str]:
    if raw_keywords is None:
        return []

    parsed = raw_keywords
    if isinstance(raw_keywords, str):
        try:
            parsed = json.loads(raw_keywords)
        except Exception:
            parsed = [raw_keywords]

    if not isinstance(parsed, list):
        parsed = [parsed]

    normalized = []
    for item in parsed:
        text = str(item).strip().lower()
        if text:
            normalized.append(text)
    return normalized


def _normalize_short_model_answer(raw_answer) -> str:
    if raw_answer is None:
        return ""
    text = str(raw_answer).strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1]
    return text.strip().lower()


def _increment_session_attempt_count(session_id: int, user_id: str):
    session_resp = (
        supabase_db.table("sessions")
        .select("questions_answered")
        .eq("id", session_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not session_resp.data:
        raise HTTPException(status_code=404, detail="Session not found")

    questions_answered = int(session_resp.data[0].get("questions_answered") or 0) + 1
    supabase_db.table("sessions").update({
        "questions_answered": questions_answered,
    }).eq("id", session_id).eq("user_id", user_id).execute()

@router.post("/submit-answer")
def submit_answer(request: SubmitAnswerRequest, user=Depends(get_current_user)):
    """
    Handles a user's answer submission:
    - Updates FSRS card (stability, difficulty, due)
    - Logs the attempt
    - Updates IRT theta (user ability)
    """
    
    user_id = str(user.id) # Convert UUID to string for DB compatibility
    question_id = request.question_id
    selected_option = request.selected_option
    response_time = request.response_time
    self_rating = request.self_rating 
    submitted_text = selected_option if isinstance(selected_option, str) else ""
    score = 0.0
    correct = False

    if request.session_id is not None:
        session_check = (
            supabase_db.table("sessions")
            .select("id")
            .eq("id", request.session_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not session_check.data:
            raise HTTPException(status_code=404, detail="Session not found")


    # -----------------------------
    # 1. Fetch the question from the database
    # -----------------------------
    question_resp = supabase_db.table("questions") \
        .select("*") \
        .eq("id", question_id) \
        .execute()
    
    validate_question_exists(question_resp)
    
    question = question_resp.data[0]
    question_type = question["type"]
    
    # -----------------------------
    # 2. Score the answer per question type:
    #    MCQ/NUMERIC   binary exact/tolerance match
    #    MULTI_MCQ     penalised partial credit
    #    SHORT         fuzzy keyword matching (rapidfuzz)
    #    OPEN          user self-rating (1–4)
    # -----------------------------

    validate_answer_submitted(selected_option)

    db_answer = question["answer"]
    options = question["options"] or {}
    correct_answer = format_correct_answer(question_type, db_answer, options)

    if question_type == "MCQ":
        selected_key = validate_mcq_selection(selected_option, options)

        score = score_mcq(selected_key, db_answer)
        correct = score == 1.0

    elif question_type == "MULTI_MCQ":
        selected_keys = validate_multi_mcq_selection(selected_option, options)
        correct_keys = validate_multi_mcq_db_answer(db_answer)

        selected_set = set(selected_keys)
        correct_set = set(correct_keys)

        score = score_multi_mcq(selected_set, correct_set)
        correct = score == 1.0

    elif question_type == "NUMERIC":
        selected_number = validate_numeric_selection(selected_option)
        correct_number = validate_numeric_db_answer(db_answer)

        tolerance = validate_numeric_tolerance(question.get("tolerance"))

        score = score_numeric(selected_number, correct_number, tolerance)
        correct = score == 1.0

    elif question_type == "SHORT":
        submitted_text = validate_short_text(selected_option)
        model_answer = _normalize_short_model_answer(db_answer)
        normalized_keywords = _normalize_short_keywords(question.get("keywords"))
        correct, score = score_short(submitted_text, normalized_keywords, model_answer)

    elif question_type == "OPEN":
        submitted_text = validate_open_text(selected_option, self_rating, require_rating=False)
        model_answer = str(db_answer).strip() if db_answer is not None else ""
        if self_rating is None:
            return {
                "requires_self_rating": True,
                "correct_answer": model_answer,
            }
        correct = self_rating >= 3 # rely on user's self-assessment for open ended questions
        score = float(self_rating) / 4.0
        
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported question type: {question_type}")
    
    # -----------------------------
    # 3. Fetch existing FSRS card for this user & question (if any) 
    # -----------------------------
    card_resp = supabase_db.table("fsrs_cards") \
        .select("*") \
        .eq("user_id", user_id) \
        .eq("question_id", question_id) \
        .execute()
    
    if card_resp.data:
        db_card = card_resp.data[0]

        card = Card(
            stability=db_card["stability"],
            difficulty=db_card["difficulty"],
            due=datetime.fromisoformat(db_card["due"]).replace(tzinfo=timezone.utc),
            last_review=datetime.fromisoformat(db_card["last_review"]).replace(tzinfo=timezone.utc) if db_card.get("last_review") else None,
            state=State(db_card["state"]),
            step=db_card["step"]
        )
    else:
        card = Card()  # FSRS will default last_review to None


    # -----------------------------
    # 4. Update FSRS card based on user's answer
    # -----------------------------

    response_history_resp = supabase_db.table("review_logs") \
        .select("question_id, response_time, questions!inner(type)") \
        .eq("user_id", user_id) \
        .execute()

    question_response_times = []
    type_response_times = []
    for row in (response_history_resp.data or []):
        response_value = row.get("response_time")
        if not isinstance(response_value, (int, float)):
            continue

        response_value = float(response_value)
        if row.get("question_id") == question_id:
            question_response_times.append(response_value)

        related_question = row.get("questions") or {}
        if related_question.get("type") == question_type:
            type_response_times.append(response_value)

    if question_type == "OPEN":
        rating = Rating(self_rating)
    else:
        rating = get_fsrs_rating(
            question_type,
            correct,
            response_time,
            score=score,
            question_response_times=question_response_times,
            type_response_times=type_response_times,
        )


    # 5. Review card (Scheduler updates intervals/stability/difficulty)
    card, _interval = scheduler.review_card(card, rating)
    
    # 6. Save FSRS card state back to DB
    supabase_db.table("fsrs_cards").upsert({
        "user_id": user_id,
        "question_id": question_id,
        "stability": card.stability,
        "difficulty": card.difficulty,
        "due": card.due.isoformat(),
        "last_review": card.last_review.isoformat() if card.last_review else None,
        "state": card.state.value,
        "step": card.step
    }, on_conflict="user_id,question_id").execute()

    # -----------------------------
    # 5. Update IRT theta (user ability)
    # -----------------------------
    

    topic_id = question["topic_id"]
    theta_resp = supabase_db.table("user_topic_theta") \
        .select("*") \
        .eq("user_id", user_id) \
        .eq("topic_id", topic_id) \
        .execute()

    theta_before = float(theta_resp.data[0].get("theta", 0.0)) if theta_resp.data else 0.0

    # Keep review_logs insertion below this block to avoid double-counting
    # the current response when reconstructing EAP history from review_logs.
    history_responses = load_topic_response_history(supabase_db, user_id, topic_id)
    current_response = format_response_for_eap(question, question_type, score, correct)
    eap_responses = history_responses + [current_response]
    theta_new, posterior_sd = eap_estimate(eap_responses)
    n_responses = len(eap_responses)
    is_calibrated = n_responses >= 10 and posterior_sd < 0.5

    # -----------------------------
    # 6. Log to review_logs table for analytics and future insights
    # -----------------------------

    supabase_db.table("review_logs").insert({
        "user_id": user_id,
        "question_id": question_id,
        "topic_id": topic_id,
        "session_id": request.session_id,
        "selected_option": submitted_text if question_type in ["SHORT", "OPEN"] else selected_option,
        "correct": correct,
        "response_time": response_time,
        "fsrs_rating": rating.value,
        "irt_signal": 1 if correct else 0,
        "theta_before": theta_before,
        "theta_after": theta_new,
        "posterior_sd": posterior_sd,
        "scheduled_days": (card.due - card.last_review).total_seconds() / 86400 if card.last_review else None,
        "stability": card.stability,
        "difficulty": card.difficulty,
        "fsrs_state": card.state.value,
        "created_at": datetime.now(timezone.utc).isoformat()
    }).execute()

    # Only count fully committed answers.
    # OPEN questions have a two-phase flow: first submit returns requires_self_rating=True
    # and does not yet produce a final answer; the second submit (with self_rating) does.
    # We must not increment on the first phase to avoid double counting.
    _answer_is_committed = not (
        question_type == "OPEN" and self_rating is None
    )
    if request.session_id is not None and _answer_is_committed:
        _increment_session_attempt_count(request.session_id, user_id)

    supabase_db.table("user_topic_theta").upsert({
        "user_id": user_id,
        "topic_id": topic_id,
        "theta": theta_new,
        "posterior_sd": posterior_sd,
        "n_responses": n_responses,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "is_calibrated": is_calibrated,
    }, on_conflict="user_id,topic_id").execute()

    # -----------------------------
    # 7. Update question calibration tracking stats
    # -----------------------------
    n_responses_q = question.get("n_responses", 0) + 1
    n_correct_q = question.get("n_correct", 0) + (1 if correct else 0)

    # Track item usage stats only; irt_b is treated as pre-calibrated.
    updates = {
        "n_responses": n_responses_q,
        "n_correct": n_correct_q,
        "is_calibrated": n_responses_q >= 10
    }

    supabase_db.table("questions").update(updates).eq("id", question_id).execute()
    
    # -----------------------------
    # 8. Return response to frontend
    # -----------------------------
    

    return {
        "correct": correct,
        "next_review": card.due.isoformat(),
        "correct_answer": correct_answer,
        "theta_after": theta_new,
    }


