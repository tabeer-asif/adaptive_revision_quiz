# app/routes/questions.py
from fastapi import APIRouter, HTTPException, Depends
from app.supabase_client import supabase_db  # ✅ use DB client
from app.dependencies.auth import get_current_user
from datetime import datetime
from app.schemas.quiz import TopicsRequest
from app.services.irt import select_best_question

router = APIRouter()
REVIEW_LIMIT = 1000
NEW_LIMIT = 5

@router.get("/questions")
def get_questions(user = Depends(get_current_user)):
    user_id = str(user.id)  # Convert UUID to string for DB queries
    now_iso = datetime.utcnow().isoformat() # Current time in ISO format for comparison

    # -----------------------------
    # 1️⃣ Get due FSRS questions
    # -----------------------------
    fsrs_resp = supabase_db.table("fsrs_cards") \
        .select("question_id") \
        .eq("user_id", user_id) \
        .lte("due", now_iso) \
        .execute()
    # Extract question IDs from FSRS response
    due_question_ids = [row["question_id"] for row in fsrs_resp.data] if fsrs_resp.data else []

    due_questions = []
    # 2️⃣ Fetch questions
    if due_question_ids:
        res = supabase_db.table("questions") \
            .select("*") \
            .in_("id", due_question_ids) \
            .execute()
        due_questions = res.data

    # -----------------------------
    # 2️⃣ Get NEW questions (not seen before)
    # -----------------------------
    seen_resp = supabase_db.table("fsrs_cards") \
        .select("question_id") \
        .eq("user_id", user_id) \
        .execute()

    seen_ids_list = [row["question_id"] for row in seen_resp.data] if seen_resp.data else []

    new_questions = []
    if seen_ids_list:
        new_resp = supabase_db.table("questions") \
            .select("*") \
            .not_.in_("id", seen_ids_list) \
            .limit(NEW_LIMIT) \
            .execute()
    else:
        # First-time user → all questions are new
        new_resp = supabase_db.table("questions") \
            .select("*") \
            .limit(NEW_LIMIT) \
            .execute()

    new_questions = new_resp.data

    # -----------------------------
    # 3️⃣ Combine (separate limits)
    # -----------------------------
    # Limit review questions
    questions = due_questions[:REVIEW_LIMIT]

    existing_ids = {q["id"] for q in questions}

    # Add new questions up to NEW_LIMIT
    new_added = 0

    for q in new_questions:
        if q["id"] not in existing_ids and new_added < NEW_LIMIT:
            questions.append(q)
            new_added += 1

    if not questions:
        raise HTTPException(status_code=404, detail="No questions available")

    # -----------------------------
    # 4️⃣ Remove answers
    # -----------------------------
    for q in questions:
        q.pop("answer", None)

    return questions



@router.post("/questions/by-topics")
def get_questions_by_topics(
    request: TopicsRequest,
    user=Depends(get_current_user)
):
    """
    Fetch questions filtered by selected topics.
    Optionally, only return FSRS-due questions first.
    """
    topic_ids = request.topics
    user_id = str(user.id)
    now_iso = datetime.utcnow().isoformat()

    # -----------------------------
    # 1️⃣ Due questions (filtered by topics)
    # -----------------------------
    fsrs_resp = supabase_db.table("fsrs_cards") \
        .select("question_id") \
        .eq("user_id", user_id) \
        .lte("due", now_iso) \
        .execute()

    due_question_ids = [row["question_id"] for row in fsrs_resp.data] if fsrs_resp.data else []

    due_questions = []

    if due_question_ids:
        res = supabase_db.table("questions") \
            .select("*") \
            .in_("id", due_question_ids) \
            .in_("topic_id", topic_ids) \
            .execute()
        due_questions = res.data

    # -----------------------------
    # 2️⃣ New questions (filtered by topics)
    # -----------------------------
    seen_resp = supabase_db.table("fsrs_cards") \
        .select("question_id") \
        .eq("user_id", user_id) \
        .execute()

    seen_ids_list = [row["question_id"] for row in seen_resp.data] if seen_resp.data else []

    if seen_ids_list:
        new_resp = supabase_db.table("questions") \
            .select("*") \
            .in_("topic_id", topic_ids) \
            .not_.in_("id", seen_ids_list) \
            .limit(NEW_LIMIT) \
            .execute()
    else:
        new_resp = supabase_db.table("questions") \
            .select("*") \
            .in_("topic_id", topic_ids) \
            .limit(NEW_LIMIT) \
            .execute()

    new_questions = new_resp.data

    # -----------------------------
    # 3️⃣ Combine
    # -----------------------------
    # Limit review questions
    questions = due_questions[:REVIEW_LIMIT]

    existing_ids = {q["id"] for q in questions}

    # Add new questions up to NEW_LIMIT
    new_added = 0

    for q in new_questions:
        if q["id"] not in existing_ids and new_added < NEW_LIMIT:
            questions.append(q)
            new_added += 1

    if not questions:
        raise HTTPException(status_code=404, detail="No questions available")

    # -----------------------------
    # 4️⃣ Remove answers
    # -----------------------------
    for q in questions:
        q.pop("answer", None)

    return questions


@router.get("/questions/irt")
def get_next_question(user=Depends(get_current_user)):
    """
    Selects the next question based on IRT:
    - Picks FSRS-due questions first
    - Then selects the question with P(correct|theta,b) closest to 0.5
    """
    user_id = str(user.id)
    now_iso = datetime.utcnow().isoformat()

    # 1️⃣ Get user ability
    user_resp = supabase_db.table("users") \
        .select("irt_theta") \
        .eq("id", user_id) \
        .single() \
        .execute()

    theta = user_resp.data.get("irt_theta", 0)

    # 2️⃣ Get FSRS due questions
    fsrs_resp = supabase_db.table("fsrs_cards") \
        .select("question_id") \
        .eq("user_id", user_id) \
        .lte("due", now_iso) \
        .execute()

    due_ids = [row["question_id"] for row in fsrs_resp.data] if fsrs_resp.data else []

    # 3️⃣ Fetch due questions
    due_questions = []
    if due_ids:
        res = supabase_db.table("questions") \
            .select("*") \
            .in_("id", due_ids) \
            .execute()
        due_questions = res.data

    # 4️⃣ Get new questions
    seen_resp = supabase_db.table("fsrs_cards") \
        .select("question_id") \
        .eq("user_id", user_id) \
        .execute()

    seen_ids = [row["question_id"] for row in seen_resp.data] if seen_resp.data else []

    if seen_ids:
        new_resp = supabase_db.table("questions") \
            .select("*") \
            .not_.in_("id", seen_ids) \
            .limit(5) \
            .execute()
    else:
        new_resp = supabase_db.table("questions") \
            .select("*") \
            .limit(5) \
            .execute()

    new_questions = new_resp.data

    # 5️⃣ Combine candidates - ensuring no duplicates
    seen_ids_set = set()
    unique_candidates = []

    for q in due_questions + new_questions:
        if q["id"] not in seen_ids_set:
            unique_candidates.append(q)
            seen_ids_set.add(q["id"])

    if not unique_candidates:
        raise HTTPException(status_code=404, detail="No questions available")

    # 6️⃣ Select best question using IRT
    best_q = select_best_question(theta, unique_candidates)

    best_q.pop("answer", None)

    return best_q

@router.post("/questions/irt/by-topics")
def get_next_question_by_topics(
    request: TopicsRequest,
    user=Depends(get_current_user)
):
    """
    Selects the next question based on IRT with topic filtering:
    - Only uses selected topics
    - Prioritises FSRS-due questions
    - Falls back to new questions
    - Returns ONE best question
    """

    user_id = str(user.id)
    topic_ids = request.topics
    now_iso = datetime.utcnow().isoformat()

    # -----------------------------
    # 1️⃣ Get user ability
    # -----------------------------
    user_resp = supabase_db.table("users") \
        .select("irt_theta") \
        .eq("id", user_id) \
        .single() \
        .execute()

    theta = user_resp.data["irt_theta"] if user_resp.data else 0

    # -----------------------------
    # 2️⃣ Get FSRS due questions
    # -----------------------------
    fsrs_resp = supabase_db.table("fsrs_cards") \
        .select("question_id") \
        .eq("user_id", user_id) \
        .lte("due", now_iso) \
        .execute()

    due_ids = [row["question_id"] for row in fsrs_resp.data] if fsrs_resp.data else []

    # -----------------------------
    # 3️⃣ Fetch due questions (filtered by topics)
    # -----------------------------
    due_questions = []
    if due_ids:
        res = supabase_db.table("questions") \
            .select("*") \
            .in_("id", due_ids) \
            .in_("topic_id", topic_ids) \
            .execute()
        due_questions = res.data

    # -----------------------------
    # 4️⃣ Get new questions (filtered)
    # -----------------------------
    seen_resp = supabase_db.table("fsrs_cards") \
        .select("question_id") \
        .eq("user_id", user_id) \
        .execute()

    seen_ids = [row["question_id"] for row in seen_resp.data] if seen_resp.data else []

    if seen_ids:
        new_resp = supabase_db.table("questions") \
            .select("*") \
            .in_("topic_id", topic_ids) \
            .not_.in_("id", seen_ids) \
            .limit(5) \
            .execute()
    else:
        new_resp = supabase_db.table("questions") \
            .select("*") \
            .in_("topic_id", topic_ids) \
            .limit(5) \
            .execute()

    new_questions = new_resp.data

    # -----------------------------
    # 5️⃣ Combine (remove duplicates)
    # -----------------------------
    seen_ids_set = set()
    unique_candidates = []

    for q in due_questions + new_questions:
        if q["id"] not in seen_ids_set:
            unique_candidates.append(q)
            seen_ids_set.add(q["id"])

    if not unique_candidates:
        raise HTTPException(status_code=404, detail="No questions available")

    # -----------------------------
    # 6️⃣ IRT selection
    # -----------------------------
    best_q = select_best_question(theta, unique_candidates)

    best_q.pop("answer", None)

    return best_q

@router.get("/questions/overview")
def get_questions_overview(user=Depends(get_current_user)):
    user_id = str(user.id)

    # Fetch all questions
    questions_resp = supabase_db.table("questions").select("*").execute()
    questions = questions_resp.data or []

    # Fetch topics
    topics_resp = supabase_db.table("topics").select("*").execute()
    topics_map = {t["id"]: t["name"] for t in topics_resp.data}

    # Fetch FSRS cards for this user
    cards_resp = supabase_db.table("fsrs_cards") \
        .select("*") \
        .eq("user_id", user_id) \
        .execute()

    cards_map = {c["question_id"]: c for c in cards_resp.data}

    result = []

    for q in questions:
        card = cards_map.get(q["id"], {})

        result.append({
            "id": q["id"],
            "text": q["text"],
            "options": q.get("options"),
            "answer": q.get("answer"),
            "type": q.get("type"),
            "topic_name": topics_map.get(q["topic_id"], "Unknown"),
            "irt_b": q.get("irt_b", 0),
            "created_at": q.get("created_at"),
            "due": card.get("due"),
            "last_review": card.get("last_review"),
        })

    return result