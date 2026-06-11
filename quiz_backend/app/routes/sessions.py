from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies.auth import get_current_user
from app.schemas.sessions import EndSessionRequest, StartSessionRequest
from app.services.ai import generate_session_feedback
from app.supabase_client import supabase_db


router = APIRouter(prefix="/sessions")
logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: object) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        if " " in text and "T" not in text:
            text = text.replace(" ", "T", 1)
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"

        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def _to_utc_iso(value: object) -> str | None:
    dt = _parse_timestamp(value)
    if dt is None:
        return None
    return dt.isoformat().replace("+00:00", "Z")


def _timestamps_drifted(a: object, b: object, threshold_seconds: float = 1.0) -> bool:
    dt_a = _parse_timestamp(a)
    dt_b = _parse_timestamp(b)
    if dt_a is None or dt_b is None:
        return False
    return abs((dt_a - dt_b).total_seconds()) > threshold_seconds


def _normalize_topic_ids(value: object) -> list[int]:
    if value is None:
        return []

    if isinstance(value, list):
        raw_ids = value
    else:
        raw_ids = [value]

    seen: set[int] = set()
    out: list[int] = []
    for raw in raw_ids:
        try:
            topic_id = int(raw)
        except (TypeError, ValueError):
            continue
        if topic_id <= 0 or topic_id in seen:
            continue
        seen.add(topic_id)
        out.append(topic_id)
    return out


def _serialize_session(row: dict) -> dict:
    started_at_raw = row.get("started_at")
    ended_at_raw = row.get("ended_at")
    started_at = _to_utc_iso(started_at_raw) or started_at_raw
    ended_at = _to_utc_iso(ended_at_raw) or ended_at_raw

    # Use a pre-computed duration when the caller already knows the exact value
    # (e.g. end_session computes it from in-memory datetimes to avoid DB round-trip issues).
    if "_computed_duration" in row:
        duration_seconds = row["_computed_duration"]
    else:
        started_dt = _parse_timestamp(started_at_raw)
        ended_dt = _parse_timestamp(ended_at_raw)
        duration_seconds = None
        if started_dt and ended_dt:
            duration_seconds = max(0.0, (ended_dt - started_dt).total_seconds())

    topic_ids = _normalize_topic_ids(row.get("topic_ids"))
    fallback_topic_id = row.get("topic_id")
    if not topic_ids and fallback_topic_id is not None:
        topic_ids = _normalize_topic_ids([fallback_topic_id])

    return {
        "id": row.get("id"),
        "user_id": row.get("user_id"),
        "topic_id": row.get("topic_id"),
        "topic_ids": topic_ids,
        "started_at": started_at,
        "ended_at": ended_at,
        "questions_answered": row.get("questions_answered", 0),
        "final_theta": row.get("final_theta"),
        "termination_reason": row.get("termination_reason"),
        "feedback": row.get("feedback"),
        "duration_seconds": duration_seconds,
        "is_active": ended_at_raw is None,
    }


@router.post("/start")
def start_session(payload: StartSessionRequest | None = None, user=Depends(get_current_user)):
    user_id = str(user.id)
    payload = payload or StartSessionRequest()

    payload_topic_ids = _normalize_topic_ids(payload.topic_ids)
    if not payload_topic_ids and payload.topic_id is not None:
        payload_topic_ids = _normalize_topic_ids([payload.topic_id])

    topic_id = payload_topic_ids[0] if payload_topic_ids else payload.topic_id

    response = supabase_db.table("sessions").insert({
        "user_id": user_id,
        "topic_id": topic_id,
        "topic_ids": payload_topic_ids if payload_topic_ids else None,
        "started_at": _utc_now_iso(),
        "questions_answered": 0,
    }).execute()

    if not response.data:
        raise HTTPException(status_code=500, detail="Failed to create session")

    return _serialize_session(response.data[0])


@router.post("/{session_id}/end")
async def end_session(session_id: int, payload: EndSessionRequest | None = None, user=Depends(get_current_user)):
    user_id = str(user.id)
    payload = payload or EndSessionRequest()

    session_res = (
        supabase_db.table("sessions")
        .select("*")
        .eq("id", session_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not session_res.data:
        raise HTTPException(status_code=404, detail="Session not found")

    session_row = session_res.data[0]
    # Keep the first end timestamp to avoid duration drift from duplicate end calls,
    # but allow missing metadata (final_theta/termination_reason) to be backfilled.
    if session_row.get("ended_at") is not None:
        metadata_update_payload = {}
        if payload.final_theta is not None and session_row.get("final_theta") is None:
            metadata_update_payload["final_theta"] = payload.final_theta
        if payload.termination_reason is not None and session_row.get("termination_reason") is None:
            metadata_update_payload["termination_reason"] = payload.termination_reason

        feedback_payload = None
        if session_row.get("feedback") is None:
            try:
                logger.info("session_feedback_generation_attempt session_id=%s", session_id)
                feedback_payload = await generate_session_feedback(
                    {**session_row, **metadata_update_payload},
                    user_id=user_id,
                )
                if feedback_payload:
                    logger.info("session_feedback_generation_stored session_id=%s", session_id)
            except Exception:  # noqa: BLE001
                logger.exception("session_feedback_generation_failed session_id=%s", session_id)

        if feedback_payload is not None:
            metadata_update_payload["feedback"] = feedback_payload

        if not metadata_update_payload:
            return _serialize_session(session_row)

        updated_metadata = (
            supabase_db.table("sessions")
            .update(metadata_update_payload)
            .eq("id", session_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not updated_metadata.data:
            raise HTTPException(status_code=500, detail="Failed to update ended session metadata")
        return _serialize_session(updated_metadata.data[0])

    now_dt = datetime.now(timezone.utc)
    ended_at_str = now_dt.isoformat().replace("+00:00", "Z")

    # Compute duration here while we have both timestamps available in memory,
    # avoiding any reliance on the DB round-tripping timestamps back correctly.
    started_dt = _parse_timestamp(session_row.get("started_at"))
    computed_duration = (
        max(0.0, (now_dt - started_dt).total_seconds()) if started_dt else None
    )

    update_payload = {
        "ended_at": ended_at_str,
        # Preserve original start time in case DB-side logic mutates it on UPDATE.
        "started_at": session_row.get("started_at"),
    }
    if payload.final_theta is not None:
        update_payload["final_theta"] = payload.final_theta
    if payload.termination_reason is not None:
        update_payload["termination_reason"] = payload.termination_reason

    updated = (
        supabase_db.table("sessions")
        .update(update_payload)
        .eq("id", session_id)
        .eq("user_id", user_id)
        .execute()
    )

    if not updated.data:
        raise HTTPException(status_code=500, detail="Failed to end session")

    updated_row = updated.data[0]
    if _timestamps_drifted(updated_row.get("started_at"), session_row.get("started_at")):
        corrected = (
            supabase_db.table("sessions")
            .update({"started_at": session_row.get("started_at")})
            .eq("id", session_id)
            .eq("user_id", user_id)
            .execute()
        )
        if corrected.data:
            updated_row = corrected.data[0]

    feedback_payload = None
    try:
        logger.info("session_feedback_generation_attempt session_id=%s", session_id)
        feedback_payload = await generate_session_feedback(
            {**updated_row, "started_at": session_row.get("started_at")},
            user_id=user_id,
        )
        if feedback_payload:
            logger.info("session_feedback_generation_stored session_id=%s", session_id)
    except Exception:  # noqa: BLE001
        logger.exception("session_feedback_generation_failed session_id=%s", session_id)

    if feedback_payload is not None:
        feedback_updated = (
            supabase_db.table("sessions")
            .update({"feedback": feedback_payload})
            .eq("id", session_id)
            .eq("user_id", user_id)
            .execute()
        )
        if feedback_updated.data:
            updated_row = feedback_updated.data[0]

    # Merge the known started_at and computed duration into the response row
    # so _serialize_session doesn't need to re-parse DB timestamps.
    response_row = {
        **updated_row,
        "started_at": session_row.get("started_at"),
        "_computed_duration": computed_duration,
    }
    return _serialize_session(response_row)


@router.get("/history")
def get_session_history(
    limit: int = Query(default=50, ge=1, le=200),
    user=Depends(get_current_user),
):
    user_id = str(user.id)

    sessions_res = (
        supabase_db.table("sessions")
        .select("*")
        .eq("user_id", user_id)
        .order("started_at", desc=True)
        .limit(limit)
        .execute()
    )

    sessions = sessions_res.data or []
    all_topic_ids: set[int] = set()
    for row in sessions:
        for topic_id in _normalize_topic_ids(row.get("topic_ids")):
            all_topic_ids.add(topic_id)
        if row.get("topic_id") is not None:
            all_topic_ids.update(_normalize_topic_ids([row.get("topic_id")]))

    topic_name_map: dict[int, str] = {}
    if all_topic_ids:
        topics_res = (
            supabase_db.table("topics")
            .select("id,name")
            .in_("id", sorted(all_topic_ids))
            .execute()
        )
        topic_name_map = {
            row["id"]: row.get("name", f"Topic {row['id']}")
            for row in (topics_res.data or [])
            if row.get("id") is not None
        }

    def _topic_fields_for_session(row: dict) -> dict:
        session_topic_ids = _normalize_topic_ids(row.get("topic_ids"))
        if not session_topic_ids and row.get("topic_id") is not None:
            session_topic_ids = _normalize_topic_ids([row.get("topic_id")])

        topic_names = [topic_name_map.get(tid, f"Topic {tid}") for tid in session_topic_ids]

        topic_summary = None
        if topic_names:
            if len(topic_names) == 1:
                topic_summary = topic_names[0]
            else:
                topic_summary = f"{topic_names[0]} + {len(topic_names) - 1} more"

        return {
            "topic_ids": session_topic_ids,
            "topic_names": topic_names,
            "topic_name": topic_names[0] if len(topic_names) == 1 else None,
            "topic_summary": topic_summary,
            "topic_count": len(topic_names),
        }

    return {
        "sessions": [
            {
                **_serialize_session(row),
                **_topic_fields_for_session(row),
            }
            for row in sessions
        ]
    }


@router.get("/{session_id}/answers")
def get_session_answers(session_id: int, user=Depends(get_current_user)):
    user_id = str(user.id)

    session_res = (
        supabase_db.table("sessions")
        .select("id,user_id")
        .eq("id", session_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not session_res.data:
        raise HTTPException(status_code=404, detail="Session not found")

    logs_res = (
        supabase_db.table("review_logs")
        .select("question_id,correct,selected_option,response_time,fsrs_rating,created_at")
        .eq("user_id", user_id)
        .eq("session_id", session_id)
        .order("created_at")
        .execute()
    )

    logs = logs_res.data or []
    question_ids = sorted({row.get("question_id") for row in logs if row.get("question_id") is not None})

    question_map: dict[int, dict] = {}
    if question_ids:
        questions_res = (
            supabase_db.table("questions")
            .select("id,text,type")
            .in_("id", question_ids)
            .execute()
        )
        question_map = {
            int(row["id"]): row
            for row in (questions_res.data or [])
            if row.get("id") is not None
        }

    answers = []
    for index, row in enumerate(logs, start=1):
        q_id = row.get("question_id")
        q_ref = question_map.get(int(q_id), {}) if q_id is not None else {}
        answers.append(
            {
                "index": index,
                "question_id": q_id,
                "question_text": q_ref.get("text") or f"Question {q_id}",
                "question_type": q_ref.get("type"),
                "correct": bool(row.get("correct")),
                "selected_option": row.get("selected_option"),
                "response_time": row.get("response_time"),
                "fsrs_rating": row.get("fsrs_rating"),
                "created_at": _to_utc_iso(row.get("created_at")) or row.get("created_at"),
            }
        )

    return {
        "session_id": session_id,
        "answers": answers,
    }