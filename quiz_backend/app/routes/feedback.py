import logging

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.dependencies.auth import get_current_user
from app.schemas.feedback import OpenFeedbackRequest, OpenFeedbackResponse
from app.services.ai import generate_open_feedback
from app.supabase_client import supabase_db


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])

OPEN_MIN_ANSWER_LENGTH = 20
OPEN_FEEDBACK_TIMEOUT_SECONDS = 300  


def _extract_model_answer(answer_data: object) -> str:
    if answer_data is None:
        return ""

    if isinstance(answer_data, str):
        return answer_data.strip()

    if isinstance(answer_data, dict):
        for key in ("text", "explanation", "answer"):
            value = answer_data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return str(answer_data).strip()

    return str(answer_data).strip()


@router.post("/open", response_model=OpenFeedbackResponse)
async def get_open_feedback(body: OpenFeedbackRequest, user=Depends(get_current_user)):
    if not settings.AI_ENABLED or not settings.GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="AI features are not enabled.")

    student_answer = body.student_answer
    # Validate minimum answer length (count all characters including spaces)
    if len(student_answer) < OPEN_MIN_ANSWER_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Answer too short to provide meaningful feedback (minimum {OPEN_MIN_ANSWER_LENGTH} characters)",
        )
    # Trim after validation for processing
    student_answer = student_answer.strip()

    question_res = (
        supabase_db.table("questions")
        .select("id, text, type, answer")
        .eq("id", body.question_id)
        .single()
        .execute()
    )

    question = question_res.data
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    if question.get("type") != "OPEN":
        raise HTTPException(status_code=400, detail="Feedback is only available for OPEN questions")

    model_answer = _extract_model_answer(question.get("answer"))
    if not model_answer:
        raise HTTPException(status_code=404, detail="No model answer available for this question")

    try:
        feedback = await generate_open_feedback(
            question_text=str(question.get("text") or ""),
            model_answer=model_answer,
            student_answer=student_answer,
            timeout_seconds=OPEN_FEEDBACK_TIMEOUT_SECONDS,
        )
        logger.info("open_feedback_generated question_id=%s", body.question_id)
    except TimeoutError as exc:
        logger.warning("open_feedback_timeout question_id=%s", body.question_id)
        raise HTTPException(status_code=504, detail="AI feedback took too long. Please try again in a moment.") from exc
    except ValueError as exc:
        logger.warning("open_feedback_parse_error question_id=%s error=%s", body.question_id, str(exc))
        raise HTTPException(status_code=502, detail="Failed to parse AI feedback — please try again") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("open_feedback_generation_failed question_id=%s", body.question_id)
        raise HTTPException(status_code=502, detail="Failed to generate AI feedback — please try again") from exc

    try:
        supabase_db.table("open_answer_feedback").insert({
            "user_id": str(user.id),
            "question_id": body.question_id,
            "student_answer": student_answer,
            "strengths": feedback["strengths"],
            "gaps": feedback["gaps"],
            "hint": feedback["hint"],
            "encouragement": feedback["encouragement"],
        }).execute()
    except Exception:  # noqa: BLE001
        logger.exception("open_feedback_insert_failed question_id=%s", body.question_id)

    return {
        **feedback,
        "model_answer": model_answer,
    }
