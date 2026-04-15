# app/routes/questions.py
from fastapi import APIRouter, HTTPException, Depends
from app.supabase_client import supabase_db  
from app.dependencies.auth import get_current_user
from datetime import datetime, timezone
from app.schemas.quiz import TopicsRequest
from app.services.irt import select_best_question_per_topic, default_grm_thresholds
from app.schemas.questions import CreateQuestionRequest, BulkDeleteRequest
from app.dependencies.question_validators import VALIDATORS
import json

IRT_DEFAULTS = {
    "easy":   {"irt_a": 1.0, "irt_b": -1.0},
    "medium": {"irt_a": 1.0, "irt_b":  0.0},
    "hard":   {"irt_a": 1.2, "irt_b":  1.0},
}
DIFFICULTY_LABEL = {1: "easy", 2: "easy", 3: "medium", 4: "hard", 5: "hard"}

def get_irt_defaults(difficulty: int) -> dict:
    label = DIFFICULTY_LABEL.get(difficulty or 1, "medium")
    return IRT_DEFAULTS[label]

router = APIRouter()
REVIEW_LIMIT = 1000
NEW_LIMIT = 20

def answers_differ(a, b) -> bool:
    # Normalise both to JSON strings for reliable comparison
    try:
        return json.dumps(a, sort_keys=True) != json.dumps(b, sort_keys=True)
    except Exception:
        return a != b

@router.post("/questions/create")
def create_question(payload: CreateQuestionRequest, user=Depends(get_current_user)):
    # 1. Validate type exists
    if payload.type not in VALIDATORS:
        raise HTTPException(400, "Invalid question type")

    # 2. Run type-specific validation
    VALIDATORS[payload.type](payload)

    irt_defaults = get_irt_defaults(payload.difficulty)

    if payload.type == "MULTI_MCQ":
        if payload.irt_thresholds:
            irt_thresholds = sorted(payload.irt_thresholds)  # enforce ordering
        else:
            # Auto-generate from b value
            b_val = payload.irt_b if payload.irt_b is not None else irt_defaults["irt_b"]
            irt_thresholds = default_grm_thresholds(b_val)
    else:
        irt_thresholds = None  # not applicable for other types

    # 3. Build DB object
    question_data = {
        "topic_id": payload.topic_id,
        "text": payload.text,
        "type": payload.type,
        "options": payload.options,
        "answer": payload.answer,
        "difficulty": payload.difficulty,
        "irt_a": payload.irt_a if payload.irt_a is not None else irt_defaults["irt_a"],
        "irt_b": payload.irt_b if payload.irt_b is not None else irt_defaults["irt_b"],
        "irt_c": payload.irt_c if payload.irt_c is not None else (
            1 / len(payload.options) if payload.type == "MCQ" and payload.options else None
        ),
        "irt_thresholds": irt_thresholds,
        "tolerance": payload.tolerance,
        "keywords": payload.keywords,
        "n_responses": 0,
        "n_correct": 0,
        "is_calibrated": False,
        "created_by": str(user.id)
    }

    # 4. Insert into DB
    res = supabase_db.table("questions").insert(question_data).execute()

    if not res.data:
        raise HTTPException(500, "Failed to create question")

    return {
        "message": "Question created successfully",
        "question": res.data[0]
    }


@router.put("/questions/{question_id}")
def update_question(question_id: int, payload: CreateQuestionRequest, user=Depends(get_current_user)):
    if payload.type not in VALIDATORS:
        raise HTTPException(400, "Invalid question type")
    
    # Check ownership first — also fetch current answer for change detection
    q = supabase_db.table("questions") \
        .select("id, created_by, answer") \
        .eq("id", question_id) \
        .single() \
        .execute()

    if not q.data:
        raise HTTPException(404, "Question not found")

    if str(q.data["created_by"]) != str(user.id):
        raise HTTPException(403, "You can only update your own questions")

    # answer_changed = payload.answer != q.data.get("answer")
    answer_changed = answers_differ(payload.answer, q.data.get("answer"))

    VALIDATORS[payload.type](payload)

    irt_defaults = get_irt_defaults(payload.difficulty)

    if payload.type == "MULTI_MCQ":
        if payload.irt_thresholds:
            irt_thresholds = sorted(payload.irt_thresholds)
        else:
            b_val = payload.irt_b if payload.irt_b is not None else irt_defaults["irt_b"]
            irt_thresholds = default_grm_thresholds(b_val)
    else:
        irt_thresholds = None

    question_data = {
        "topic_id": payload.topic_id,
        "text": payload.text,
        "type": payload.type,
        "options": payload.options,
        "answer": payload.answer,
        "difficulty": payload.difficulty,
        "irt_a": payload.irt_a if payload.irt_a is not None else irt_defaults["irt_a"],
        "irt_b": payload.irt_b if payload.irt_b is not None else irt_defaults["irt_b"],
        "irt_c": payload.irt_c if payload.irt_c is not None else (
            1 / len(payload.options) if payload.type == "MCQ" and payload.options else None
        ),
        "irt_thresholds": irt_thresholds,
        "tolerance": payload.tolerance,
        "keywords": payload.keywords,
    }

    # Reset calibration stats only if the answer itself changed — prior data is now invalid
    if answer_changed:
        question_data["n_responses"] = 0
        question_data["n_correct"] = 0
        question_data["is_calibrated"] = False

        # Only reset FSRS cards if the answer changed — prior scheduling is now invalid
        supabase_db.table("fsrs_cards") \
            .delete() \
            .eq("question_id", question_id) \
            .execute()
    
    res = supabase_db.table("questions") \
        .update(question_data) \
        .eq("id", question_id) \
        .execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="Question not found")

    return {
        "message": "Question updated successfully",
        "question": res.data[0],
    }



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
    now_iso = datetime.now(timezone.utc).isoformat() # Current time in ISO format for comparison

    # -----------------------------
    # 1️⃣  Get per-topic theta for requested topics
    # -----------------------------
    # FIX — you have multiple topics in the request, need theta per topic
    # Fetch all at once then use per question
    theta_resp = supabase_db.table("user_topic_theta") \
        .select("*") \
        .eq("user_id", user_id) \
        .in_("topic_id", topic_ids) \
        .execute()

    # Build a lookup dict
    theta_map = {
        row["topic_id"]: row["theta"] 
        for row in (theta_resp.data or [])
    }
    calibrated_map = {row["topic_id"]: row["is_calibrated"] for row in (theta_resp.data or [])}
    

    # -----------------------------
    # 2️⃣ Fetch FSRS-due questions filtered by topic (single query)
    # -----------------------------
    
    due_resp = supabase_db.table("fsrs_cards") \
        .select("question_id, questions!inner(*)") \
        .eq("user_id", user_id) \
        .lte("due", now_iso) \
        .in_("questions.topic_id", topic_ids) \
        .execute()

    due_questions = [row["questions"] for row in (due_resp.data or [])]

    # -----------------------------
    # 3️⃣ Fetch seen question IDs (for new question exclusion)
    # -----------------------------
    seen_resp = supabase_db.table("fsrs_cards") \
        .select("question_id") \
        .eq("user_id", user_id) \
        .execute()

    seen_ids = [row["question_id"] for row in (seen_resp.data or [])]

    # -----------------------------
    # 4️⃣ Fetch new questions with b-range pre-filter
    # -----------------------------
    avg_theta = sum(theta_map.values()) / len(theta_map) if theta_map else 0.0

    new_query = supabase_db.table("questions") \
        .select("*") \
        .in_("topic_id", topic_ids) \
        .gte("irt_b", avg_theta - 1.5) \
        .lte("irt_b", avg_theta + 1.5) \
        .limit(NEW_LIMIT)

    if seen_ids:
        new_query = new_query.not_.in_("id", seen_ids)

    new_questions = new_query.execute().data or []

    # -----------------------------
    # 5️⃣ Select: prioritise due, fall back to new
    # -----------------------------
    if due_questions:
        pool = due_questions
    elif new_questions:
        pool = new_questions
    else:
        raise HTTPException(404, "No questions available")
    
    # -----------------------------
    # 6️⃣ IRT selection — use Fisher Information if uncalibrated, P=0.7 if calibrated
    # -----------------------------

    any_calibrated = any(calibrated_map.get(t, False) for t in topic_ids)
    target = 0.7 if any_calibrated else None  # None = use Fisher Information

    best_q = select_best_question_per_topic(theta_map, pool, target=target)

    if best_q is None:
        raise HTTPException(status_code=404, detail="No suitable question found")

    best_q.pop("answer", None)
    return best_q
    
@router.get("/questions/overview")
def get_questions_overview(user=Depends(get_current_user)):
    user_id = str(user.id)

    # Fetch all questions
    questions_resp = supabase_db.table("questions") \
    .select("*") \
    .eq("created_by", user_id) \
    .execute()
    questions = questions_resp.data or []

    # Fetch topics
    topics_resp = supabase_db.table("topics").select("*").execute()
    topics_map = {t["id"]: t["name"] for t in (topics_resp.data or [])}

    # Fetch FSRS cards for this user
    cards_resp = supabase_db.table("fsrs_cards") \
        .select("*") \
        .eq("user_id", user_id) \
        .execute()

    cards_map = {c["question_id"]: c for c in (cards_resp.data or [])}

    result = []

    for q in questions:
        card = cards_map.get(q["id"], {})

        q_data = {
            "id": q["id"],
            "topic_id": q.get("topic_id"),
            "text": q["text"],
            "options": q.get("options"),
            "type": q.get("type"),
            "topic_name": topics_map.get(q["topic_id"], "Unknown"),
            "difficulty": q.get("difficulty", 1),
            "created_at": q.get("created_at"),
            "due": card.get("due"),
            "last_review": card.get("last_review"),
            "tolerance": q.get("tolerance"),
            "keywords": q.get("keywords"),
        }
        # Only expose the answer to the question's owner
        if str(q.get("created_by")) == user_id:
            q_data["answer"] = q.get("answer")
        result.append(q_data)

    return result

@router.get("/questions/due/count")
def get_due_count(user=Depends(get_current_user)):
    user_id = str(user.id)
    now_iso = datetime.now(timezone.utc).isoformat() # Current time in ISO format for comparison

    # Count due FSRS cards for this user.
    due_resp = supabase_db.table("fsrs_cards") \
        .select("question_id", count="exact") \
        .eq("user_id", user_id) \
        .lte("due", now_iso) \
        .execute()

    due_count = due_resp.count or 0

    # Count new cards (questions not yet present in this user's fsrs_cards).
    total_resp = supabase_db.table("questions") \
    .select("id", count="exact") \
    .eq("created_by", user_id) \
    .execute()
    seen_count_resp = supabase_db.table("fsrs_cards") \
        .select("question_id", count="exact") \
        .eq("user_id", user_id) \
        .execute()

    new_count = max(0, (total_resp.count or 0) - (seen_count_resp.count or 0))

    return {
        "total_available": due_count + new_count,
         "due_count": due_count,
         "new_count": new_count,
    }


@router.delete("/questions/all/confirm")
def delete_all_questions(user=Depends(get_current_user)):
    """
    Delete all questions owned by the current user and their related fsrs_cards.
    Requires a deliberate endpoint path to prevent accidental calls.
    """
    user_id = str(user.id)

    # Fetch IDs of all questions owned by this user.
    q_resp = supabase_db.table("questions") \
        .select("id") \
        .eq("created_by", user_id) \
        .execute()

    user_question_ids = [row["id"] for row in (q_resp.data or [])]

    if not user_question_ids:
        return {"message": "No questions to delete", "deleted_count": 0}

    # Remove related FSRS cards first.
    supabase_db.table("fsrs_cards") \
        .delete() \
        .in_("question_id", user_question_ids) \
        .execute()

    res = supabase_db.table("questions") \
        .delete() \
        .in_("id", user_question_ids) \
        .execute()

    deleted_count = len(res.data) if res.data else 0

    return {"message": f"All {deleted_count} question(s) deleted", "deleted_count": deleted_count}


@router.delete("/questions")
def delete_questions(request: BulkDeleteRequest, user=Depends(get_current_user)):
    """
    Delete multiple questions by a list of IDs.
    Also removes related fsrs_cards entries.
    """
    if not request.ids:
        raise HTTPException(status_code=400, detail="No question IDs provided")

    user_id = str(user.id)

    # Verify all questions exist and belong to this user.
    q_resp = supabase_db.table("questions") \
        .select("id, created_by") \
        .in_("id", request.ids) \
        .execute()

    found = q_resp.data or []
    found_ids = {row["id"] for row in found}
    missing = [i for i in request.ids if i not in found_ids]
    if missing:
        raise HTTPException(404, f"Questions not found: {missing}")

    not_owned = [row["id"] for row in found if str(row["created_by"]) != user_id]
    if not_owned:
        raise HTTPException(403, "You can only delete your own questions")

    # Remove related FSRS cards first.
    supabase_db.table("fsrs_cards") \
        .delete() \
        .in_("question_id", request.ids) \
        .execute()

    res = supabase_db.table("questions") \
        .delete() \
        .in_("id", request.ids) \
        .execute()

    deleted_count = len(res.data) if res.data else 0

    return {"message": f"{deleted_count} question(s) deleted", "deleted_count": deleted_count}


@router.delete("/questions/{question_id}")
def delete_question(question_id: int, user=Depends(get_current_user)):
    """
    Delete a single question by ID.
    Also removes related fsrs_cards entries.
    """
    # Check ownership first
    q = supabase_db.table("questions") \
        .select("id, created_by") \
        .eq("id", question_id) \
        .single() \
        .execute()
    
    if not q.data:
        raise HTTPException(404, "Question not found")
    
    if str(q.data["created_by"]) != str(user.id):
        raise HTTPException(403, "You can only delete your own questions")

    # Remove related FSRS cards first to avoid orphaned rows.
    supabase_db.table("fsrs_cards") \
        .delete() \
        .eq("question_id", question_id) \
        .execute()

    res = supabase_db.table("questions") \
        .delete() \
        .eq("id", question_id) \
        .execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="Question not found")

    return {"message": f"Question {question_id} deleted successfully"}