# app/routes/quiz.py
from fastapi import APIRouter, HTTPException, Depends
from app.dependencies.auth import get_current_user
from app.supabase_client import supabase_db
from datetime import datetime, timezone
from app.schemas.quiz import SubmitAnswerRequest
from fsrs import Card, Rating, Scheduler
from app.services.irt import irt_probability

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

    # -----------------------------
    # 1. Fetch the question from the database
    # -----------------------------
    question_resp = supabase_db.table("questions") \
        .select("*") \
        .eq("id", question_id) \
        .execute()
    
    if not question_resp.data:
        raise HTTPException(status_code=404, detail="Question not found")
    
    question = question_resp.data[0]

    # -----------------------------
    # 2. Check if the selected answer is correct
    # -----------------------------

    if not selected_option:
        raise HTTPException(status_code=400, detail="No option selected")
    selected_key = list(selected_option.keys())[0]
    correct_key = question["answer"]["correct"]
    correct = selected_key == correct_key
    
    # -----------------------------
    # 4. Fetch existing FSRS card for this user & question (if any)
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
            last_review=datetime.fromisoformat(db_card["last_review"]).replace(tzinfo=timezone.utc) if db_card.get("last_review") else None
        )
    else:
        card = Card()  # FSRS will default last_review to None


    # -----------------------------
    # 5. Update FSRS card based on user's answer
    # Replace SM-2 in /app/routes/quiz.py with FSRS (Scheduler)
    # Store/update FSRS cards in fsrs_cards table
    # Log attempts in review_logs table
    # Keep /questions endpoint ready to fetch due questions
    # -----------------------------

    # 4️⃣ Convert user response to FSRS rating
    rating = Rating.Good if correct else Rating.Again

    # 5️⃣ Review card (Scheduler updates intervals/stability/difficulty)
    card, _interval = scheduler.review_card(card, rating)
    

    # 6️⃣ Save FSRS card state back to DB
    supabase_db.table("fsrs_cards").upsert({
        "user_id": user_id,
        "question_id": question_id,
        "stability": card.stability,
        "difficulty": card.difficulty,
        "due": card.due.isoformat(),
        "last_review": card.last_review.isoformat() if card.last_review else None
    }, on_conflict="user_id,question_id").execute()

    # 7️⃣ Log attempt in review_logs
    supabase_db.table("review_logs").insert({
        "user_id": user_id,
        "question_id": question_id,
        "selected_option": selected_option,
        "correct": correct,
        "response_time": response_time
    }).execute()

    # -----------------------------
    # 5. Update IRT theta (user ability)
    # -----------------------------
    user_resp = supabase_db.table("users") \
        .select("irt_theta") \
        .eq("id", user_id) \
        .single() \
        .execute()

    theta = user_resp.data.get("irt_theta", 0)
    a = question.get("irt_a", 1)
    b = question.get("irt_b", 0)

    p = irt_probability(theta, a, b)
    learning_rate_theta = 0.1
    theta_new = theta + learning_rate_theta * ((1 if correct else 0) - p)

    supabase_db.table("users").update({
        "irt_theta": theta_new
    }).eq("id", user_id).execute()

    # -----------------------------
    # 6. Update question difficulty b automatically
    # -----------------------------
    learning_rate_b = 0.05
    # simple adaptive update: move b toward user's ability if correct, away if wrong
    b_new = b + learning_rate_b * ((theta_new - b) if correct else -(theta_new - b))
    # b_new = b + learning_rate_b * ((theta - b) * (1 - p) if correct else -(theta - b) * p) can weight b by p
    '''
    base_lr_b = 0.05
    adaptive_lr_b = base_lr_b / (1 + card.reps)  # smaller updates for repeated questions

    # weighted by IRT probability
    b_change = ((theta_new - b) * (1 - p)) if correct else (-(theta_new - b) * p)
    b_new = b + adaptive_lr_b * b_change
    '''

    supabase_db.table("questions").update({
        "irt_b": b_new
    }).eq("id", question_id).execute()

    # 8️⃣ Return response to frontend
    return {
        "correct": correct,
        "next_review": card.due.isoformat(),
        "stability": card.stability,
        "difficulty": card.difficulty,
        "theta": theta_new,
        "b_new": b_new
    }


    '''

    # -----------------------------
    # 4. SM-2 algorithm to calculate next review interval
    # -----------------------------
    # Quality of response: 5 = correct, 2 = wrong (simplified)
    quality = 5 if correct else 2
    # Update E-Factor based on quality
    efactor = max(1.3, efactor + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))

    # Determine next interval based on repetition count
    if repetition_count == 1:
        interval = 1
    elif repetition_count == 2:
        interval = 6
    else:
        interval = round(interval * efactor)

    # Calculate next review date
    next_review_date = (datetime.utcnow() + timedelta(days=interval)).date()

    # -----------------------------
    # 5. Upsert (insert or update) the user's progress in DB
    # Convert datetime/date fields to ISO format strings for JSON compatibility
    # -----------------------------
    supabase_db.table("user_progress").upsert({
        "user_id": user_id,
        "question_id": question_id,
        "attempt_time": datetime.utcnow().isoformat(),  # UTC timestamp
        "selected_option": selected_option,
        "correct": correct,
        "repetition_count": repetition_count,
        "efactor": efactor,
        "interval": interval,
        "next_review_date": next_review_date.isoformat()  # date as string
    }).execute()

    

    # -----------------------------
    # 6. Return result to frontend
    # -----------------------------
    return {
        "correct": correct,
        "efactor": efactor,
        "interval": interval,
        "next_review_date": str(next_review_date)
    }
    '''