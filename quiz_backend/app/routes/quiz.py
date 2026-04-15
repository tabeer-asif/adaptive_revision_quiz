# app/routes/quiz.py
from fastapi import APIRouter, HTTPException, Depends
from app.dependencies.auth import get_current_user
from app.supabase_client import supabase_db
from datetime import datetime, timezone
import math
from app.schemas.quiz import SubmitAnswerRequest
from fsrs import Card, Rating, Scheduler, State
from app.services.irt import (
    get_fsrs_rating, 
    score_mcq, 
    score_multi_mcq, 
    score_numeric,
    score_short,
    update_theta_2pl,
    update_theta_3pl,
    update_theta_grm,

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

@router.post("/submit-answer")
def submit_answer(request: SubmitAnswerRequest, user=Depends(get_current_user)):
    """
    Handles a user's answer submission:
    - Updates FSRS card (stability, difficulty, due)
    - Logs the attempt
    - Updates IRT theta (user ability)
    - Updates question difficulty b automatically
    """
    
    user_id = str(user.id) # Convert UUID to string for DB compatibility
    question_id = request.question_id
    selected_option = request.selected_option
    response_time = request.response_time
    self_rating = request.self_rating 
    submitted_text = selected_option if isinstance(selected_option, str) else ""
    score = 0.0
    correct = False


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
    #    MCQ/NUMERIC  → binary exact/tolerance match
    #    MULTI_MCQ    → penalised partial credit
    #    SHORT        → fuzzy keyword matching (rapidfuzz)
    #    OPEN         → user self-rating (1–4)
    # -----------------------------

    validate_answer_submitted(selected_option)

    db_answer = question["answer"]
    options = question["options"] or {}

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
        model_answer = str(db_answer).strip().lower() if db_answer is not None else ""
        keywords = question.get("keywords") or []
        normalized_keywords = [str(keyword).strip().lower() for keyword in keywords if str(keyword).strip()]
        correct, score = score_short(submitted_text, normalized_keywords, model_answer)

    elif question_type == "OPEN":
        submitted_text = validate_open_text(selected_option, self_rating)
        model_answer = str(db_answer).strip() if db_answer is not None else ""
        correct = self_rating >= 3 # rely on user's self-assessment for open-ended questions
        score = float(self_rating) / 4.0
        
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported question type: {question_type}")
    
    # -----------------------------
    # 3. Fetch existing FSRS card for this user & question (if any) FINE
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

   
    
    # rating = Rating.Good if correct else Rating.Again
    if question_type == "OPEN":
        rating = Rating(self_rating)  # convert int → Rating enum
    else:
        rating = get_fsrs_rating(question_type, correct, response_time, score=score)


    # 5️⃣ Review card (Scheduler updates intervals/stability/difficulty)
    card, _interval = scheduler.review_card(card, rating)
    
    # 6️⃣ Save FSRS card state back to DB
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

    a = question.get("irt_a", 1.0)
    b = question.get("irt_b", 0.0)

    if theta_resp.data:
        theta = theta_resp.data[0]["theta"]
        theta_variance = theta_resp.data[0]["theta_variance"]
        n_responses = theta_resp.data[0]["n_responses"]
        is_calibrated = theta_resp.data[0].get("is_calibrated")
    else:
        # Cold start — first time user sees this topic
        theta = 0.0
        theta_variance = 1.0
        n_responses = 0
        is_calibrated = False


    if question_type == "MULTI_MCQ":
        irt_signal = 1 if score >= 0.7 else 0 # use partial credit score for multi-MCQ
    elif question_type == "OPEN":
        irt_signal = 1 if (self_rating is not None and self_rating >= 3) else 0
    else:
        irt_signal = 1 if correct else 0 # binary signal for IRT (MCQ, NUMERIC, OPEN)

    
    learning_rate = max(0.1, 0.5 - 0.05 * n_responses)  # decaying rate
    
    if question_type == "MCQ":
        c = question.get("irt_c")  # guessing parameter for MCQ
        theta_new = update_theta_3pl(theta, a, b, c, irt_signal, learning_rate)
    
    elif question_type == "MULTI_MCQ":
        b_thresholds = question.get("irt_thresholds")  # your jsonb column
        if not b_thresholds:
            # fallback to 2PL binary if no thresholds stored yet
            theta_new = update_theta_2pl(theta, a, b, irt_signal, learning_rate)
        else:
            # GRM expects ordinal category not binary signal
            if score == 1.0:   grm_category = 2
            elif score >= 0.5: grm_category = 1
            else:              grm_category = 0
            theta_new = update_theta_grm(theta, a, b_thresholds, grm_category, learning_rate)
    
    elif question_type in ["NUMERIC", "SHORT"]:
        theta_new = update_theta_2pl(theta, a, b, irt_signal, learning_rate)
    
    elif question_type == "OPEN":
        # For open-ended questions, we might want to update theta less aggressively since correctness is subjective

        theta_new = update_theta_2pl(theta, a, b, irt_signal, learning_rate * 0.5)
    
    else:  # pragma: no cover - unreachable due to earlier type guard
        # Fallback — should never reach here given type validation above
        theta_new = theta  # no update, safe default

    
    # -----------------------------
    # 6. Log to review_logs table for analytics and future insights after UPDATE THETA
    # -----------------------------

    supabase_db.table("review_logs").insert({
        "user_id": user_id,
        "question_id": question_id,
        "topic_id": topic_id,
        #session_id: request.session_id if you have sessions implemented
        "selected_option": submitted_text if question_type in ["SHORT", "OPEN"] else selected_option,
        "correct": correct,
        "response_time": response_time,
        "fsrs_rating": rating.value,
        "irt_signal": irt_signal,
        "theta_before": theta,
        "theta_after": theta_new,
        "created_at": datetime.now(timezone.utc).isoformat()
    }).execute()

    supabase_db.table("user_topic_theta").upsert({
        "user_id": user_id,
        "topic_id": topic_id,
        "theta": theta_new,
        "theta_variance": max(0.1, theta_variance * 0.95),  # optional: decrease variance as we get more data
        "n_responses": n_responses + 1,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        # FIX — mark calibrated after enough responses
        "is_calibrated": is_calibrated or ((n_responses + 1) >= 15)
    }, on_conflict="user_id,topic_id").execute()

    # -----------------------------
    # 7. Update question calibration tracking stats
    # -----------------------------
    '''
    learning_rate_b = 0.05
    adaptive_lr_b = learning_rate_b  
    error = (1 if correct else 0) - p
    b_new = b - adaptive_lr_b * a * error
    

    supabase_db.table("questions").update({
        "irt_b": b_new
    }).eq("id", question_id).execute()
    '''
    
    
    n_responses_q = question.get("n_responses", 0) + 1
    n_correct_q = question.get("n_correct", 0) + (1 if correct else 0)
    pass_rate = n_correct_q / n_responses_q

    # Only update b once we have enough data
    updates = {
        "n_responses": n_responses_q,
        "n_correct": n_correct_q,
        "is_calibrated": n_responses_q >= 10
    }

    if n_responses_q >= 10:
        # Data-driven b update from pass rate
        if 0.05 < pass_rate < 0.95:
            logit = math.log(pass_rate / (1 - pass_rate))
            updates["irt_b"] = -logit  # higher pass rate → easier → lower b

    supabase_db.table("questions").update(updates).eq("id", question_id).execute()
    
    # -----------------------------
    # 8. Return response to frontend
    # -----------------------------
    

    return {
        "correct": correct,
        "next_review": card.due.isoformat()
    }


