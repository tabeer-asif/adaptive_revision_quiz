# app/routes/explanations.py
from fastapi import APIRouter, Depends, HTTPException
from app.dependencies.auth import get_current_user
from app.supabase_client import supabase_db
from app.config import settings
from app.schemas.explanations import (
    ExplanationRequest,
    ExplanationResponse,
    ChatRequest,
    ChatResponse,
)

router = APIRouter(prefix="/explanations", tags=["explanations"])


@router.post("/explain", response_model=ExplanationResponse)
async def explain_answer(body: ExplanationRequest, user=Depends(get_current_user)):
    """
    On-demand post-answer explanation.
    Called when the user clicks "Explain this" after submitting an answer.
    Personalised to their ability level (theta) and recent accuracy.
    """
    if not settings.AI_ENABLED or not settings.GEMINI_API_KEY:
        raise HTTPException(503, "AI features are not enabled.")

    # ── 1. Fetch question ──────────────────────────────────────────────
    q_res = supabase_db.table("questions") \
        .select("text, type, options, answer, keywords, topic_id") \
        .eq("id", body.question_id) \
        .single() \
        .execute()

    if not q_res.data:
        raise HTTPException(404, "Question not found.")

    question = q_res.data

    # ── 2. Verify topic is consistent (prevent cross-topic smuggling) ──
    if question.get("topic_id") != body.topic_id:
        raise HTTPException(400, "topic_id does not match the question's topic.")

    # ── 3. Fetch user theta for this topic ─────────────────────────────
    theta_res = supabase_db.table("user_topic_theta") \
        .select("theta, n_responses") \
        .eq("user_id", str(user.id)) \
        .eq("topic_id", body.topic_id) \
        .execute()

    theta = theta_res.data[0]["theta"] if theta_res.data else 0.0

    # ── 4. Compute recent accuracy from review_logs ────────────────────
    history_res = supabase_db.table("review_logs") \
        .select("correct") \
        .eq("user_id", str(user.id)) \
        .eq("topic_id", body.topic_id) \
        .order("created_at", desc=True) \
        .limit(10) \
        .execute()

    recent_accuracy: float | None = None
    if history_res.data:
        recent_accuracy = sum(1 for r in history_res.data if r["correct"]) / len(history_res.data)

    # ── 5. Build user_answer dict for the service ──────────────────────
    user_answer = {
        "selected_option": body.selected_option,
        "self_rating": body.self_rating,
    }

    # ── 6. Generate explanation ────────────────────────────────────────
    try:
        from app.services.ai import generate_explanation
        result = await generate_explanation(
            question=question,
            user_answer=user_answer,
            theta=theta,
            recent_accuracy=recent_accuracy,
        )
    except Exception as exc:
        raise HTTPException(500, f"Explanation generation failed: {exc}")

    return result


@router.post("/chat", response_model=ChatResponse)
async def chat_about_question(body: ChatRequest, user=Depends(get_current_user)):
    """
    Contextual AI chat scoped to a single answered question.
    Only available after the student has submitted their answer.
    """
    if not settings.AI_ENABLED or not settings.GEMINI_API_KEY:
        raise HTTPException(503, "AI features are not enabled.")

    # ── 1. Fetch question ──────────────────────────────────────────────
    q_res = supabase_db.table("questions") \
        .select("text, type, options, answer, keywords, topic_id") \
        .eq("id", body.question_id) \
        .single() \
        .execute()

    if not q_res.data:
        raise HTTPException(404, "Question not found.")

    question = q_res.data

    # ── 2. Verify topic consistency ────────────────────────────────────
    if question.get("topic_id") != body.topic_id:
        raise HTTPException(400, "topic_id does not match the question's topic.")

    # ── 3. Fetch theta for personalisation ─────────────────────────────
    theta_res = supabase_db.table("user_topic_theta") \
        .select("theta") \
        .eq("user_id", str(user.id)) \
        .eq("topic_id", body.topic_id) \
        .execute()

    theta = theta_res.data[0]["theta"] if theta_res.data else 0.0

    # ── 4. Generate reply ──────────────────────────────────────────────
    try:
        from app.services.ai import generate_chat_reply
        reply = await generate_chat_reply(
            question=question,
            user_answer=body.user_answer,
            theta=theta,
            history=[msg.model_dump() for msg in body.history],
            new_message=body.message,
        )
    except Exception as exc:
        raise HTTPException(500, f"Chat failed: {exc}")

    return {"reply": reply}
