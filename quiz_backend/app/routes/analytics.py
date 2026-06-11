from collections import defaultdict
from datetime import datetime, timedelta, timezone
from math import log

from fastapi import APIRouter, Depends, Query

from app.dependencies.auth import get_current_user
from app.supabase_client import supabase_db


router = APIRouter(prefix="/analytics")


def _iso_utc_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _to_day(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def _safe_logit_from_pass_rate(pass_rate: float) -> float:
    clamped = min(0.99, max(0.01, pass_rate))
    return log(clamped / (1.0 - clamped))


@router.get("/theta-progression")
def get_theta_progression(
    topic_id: int | None = Query(default=None),
    days: int = Query(default=90, ge=1, le=3650),
    user=Depends(get_current_user),
):
    user_id = str(user.id)

    query = (
        supabase_db.table("review_logs")
        .select("topic_id,theta_before,theta_after,posterior_sd,created_at")
        .eq("user_id", user_id)
        .gte("created_at", _iso_utc_days_ago(days))
        .order("created_at")
    )
    if topic_id is not None:
        query = query.eq("topic_id", topic_id)

    logs = query.execute().data or []

    topic_ids = sorted({row.get("topic_id") for row in logs if row.get("topic_id") is not None})
    topic_name_map: dict[int, str] = {}
    if topic_ids:
        topics = (
            supabase_db.table("topics")
            .select("id,name")
            .in_("id", topic_ids)
            .execute()
            .data
            or []
        )
        topic_name_map = {row["id"]: row.get("name", f"Topic {row['id']}") for row in topics if row.get("id") is not None}

    grouped: dict[int, list[dict]] = defaultdict(list)
    for row in logs:
        t_id = row.get("topic_id")
        if t_id is None:
            continue
        grouped[t_id].append(
            {
                "created_at": row.get("created_at"),
                "theta_before": row.get("theta_before"),
                "theta_after": row.get("theta_after"),
                "posterior_sd": row.get("posterior_sd"),
            }
        )

    series = [
        {
            "topic_id": t_id,
            "topic_name": topic_name_map.get(t_id, f"Topic {t_id}"),
            "points": points,
        }
        for t_id, points in grouped.items()
    ]

    return {
        "window_days": days,
        "series": series,
    }


@router.get("/topic-summary")
def get_topic_summary(user=Depends(get_current_user)):
    user_id = str(user.id)

    theta_rows = (
        supabase_db.table("user_topic_theta")
        .select("topic_id,theta,n_responses,posterior_sd,is_calibrated,last_updated")
        .eq("user_id", user_id)
        .order("topic_id")
        .execute()
        .data
        or []
    )

    topic_ids = [row["topic_id"] for row in theta_rows if row.get("topic_id") is not None]
    topic_name_map: dict[int, str] = {}
    if topic_ids:
        topics = (
            supabase_db.table("topics")
            .select("id,name")
            .in_("id", topic_ids)
            .execute()
            .data
            or []
        )
        topic_name_map = {row["id"]: row.get("name", f"Topic {row['id']}") for row in topics if row.get("id") is not None}

    summary = [
        {
            "topic_id": row.get("topic_id"),
            "topic_name": topic_name_map.get(row.get("topic_id"), f"Topic {row.get('topic_id')}"),
            "theta": row.get("theta"),
            "n_responses": row.get("n_responses", 0),
            "posterior_sd": row.get("posterior_sd"),
            "is_calibrated": row.get("is_calibrated", False),
            "last_updated": row.get("last_updated"),
        }
        for row in theta_rows
    ]

    return {
        "topics": summary,
    }


@router.get("/fsrs-retention")
def get_fsrs_retention(
    days: int = Query(default=30, ge=1, le=365),
    user=Depends(get_current_user),
):
    user_id = str(user.id)

    cards = (
        supabase_db.table("fsrs_cards")
        .select("due,stability,questions!inner(topic_id,created_by)")
        .eq("user_id", user_id)
        .eq("questions.created_by", user_id)
        .execute()
        .data
        or []
    )

    today = datetime.now(timezone.utc).date()
    horizon = today + timedelta(days=days)

    due_today = 0
    overdue = 0
    due_next_window = 0

    due_counts_by_day: dict[str, int] = defaultdict(int)
    stability_sum_by_day: dict[str, float] = defaultdict(float)
    stability_n_by_day: dict[str, int] = defaultdict(int)

    for row in cards:
        due_day = _to_day(row.get("due"))
        stability = row.get("stability")
        if due_day is None:
            continue

        parsed_due = datetime.fromisoformat(f"{due_day}T00:00:00+00:00").date()

        if parsed_due < today:
            overdue += 1
        elif parsed_due == today:
            due_today += 1
        elif parsed_due <= horizon:
            due_next_window += 1

        if today <= parsed_due <= horizon:
            key = parsed_due.isoformat()
            due_counts_by_day[key] += 1
            if isinstance(stability, (int, float)):
                stability_sum_by_day[key] += float(stability)
                stability_n_by_day[key] += 1

    due_trend = [
        {
            "date": day,
            "due_count": due_counts_by_day[day],
        }
        for day in sorted(due_counts_by_day)
    ]

    stability_trend = [
        {
            "date": day,
            "avg_stability": (
                stability_sum_by_day[day] / stability_n_by_day[day]
                if stability_n_by_day[day]
                else None
            ),
            "card_count": stability_n_by_day[day],
        }
        for day in sorted(stability_n_by_day)
    ]

    return {
        "window_days": days,
        "summary": {
            "overdue": overdue,
            "due_today": due_today,
            "due_in_window": due_next_window,
        },
        "due_counts_over_time": due_trend,
        "stability_trend": stability_trend,
    }


@router.get("/question-performance")
def get_question_performance(
    days: int = Query(default=180, ge=1, le=3650),
    user=Depends(get_current_user),
):
    user_id = str(user.id)

    questions = (
        supabase_db.table("questions")
        .select("id,topic_id,text,irt_b,n_responses,n_correct")
        .eq("created_by", user_id)
        .execute()
        .data
        or []
    )

    question_ids = [row.get("id") for row in questions if row.get("id") is not None]
    if not question_ids:
        return {"questions": []}

    logs = (
        supabase_db.table("review_logs")
        .select("question_id,correct,created_at")
        .eq("user_id", user_id)
        .gte("created_at", _iso_utc_days_ago(days))
        .in_("question_id", question_ids)
        .order("created_at")
        .execute()
        .data
        or []
    )

    by_question: dict[int, list[dict]] = defaultdict(list)
    for row in logs:
        q_id = row.get("question_id")
        if q_id is None:
            continue
        by_question[q_id].append(row)

    out = []
    for question in questions:
        q_id = question.get("id")
        q_logs = by_question.get(q_id, [])

        attempts = len(q_logs)
        correct_n = sum(1 for item in q_logs if bool(item.get("correct")))

        if attempts == 0:
            attempts = int(question.get("n_responses") or 0)
            correct_n = int(question.get("n_correct") or 0)

        pass_rate = (correct_n / attempts) if attempts > 0 else None

        empirical_b = None
        irt_b_drift = None
        if pass_rate is not None:
            empirical_b = -_safe_logit_from_pass_rate(pass_rate)
            irt_b = question.get("irt_b")
            if isinstance(irt_b, (int, float)):
                irt_b_drift = float(irt_b) - empirical_b

        recent = q_logs[-5:]
        recent_pass_rate = None
        if recent:
            recent_pass_rate = sum(1 for item in recent if bool(item.get("correct"))) / len(recent)

        out.append(
            {
                "question_id": q_id,
                "topic_id": question.get("topic_id"),
                "text": question.get("text"),
                "attempts": attempts,
                "correct": correct_n,
                "pass_rate": pass_rate,
                "recent_pass_rate": recent_pass_rate,
                "irt_b": question.get("irt_b"),
                "empirical_b": empirical_b,
                "irt_b_drift": irt_b_drift,
            }
        )

    out.sort(key=lambda row: (row["attempts"], row["question_id"] or 0), reverse=True)

    return {
        "window_days": days,
        "questions": out,
    }


@router.get("/fsrs-ratings")
def get_fsrs_ratings(
    days: int = Query(default=30, ge=1, le=365),
    user=Depends(get_current_user),
):
    user_id = str(user.id)

    logs = (
        supabase_db.table("review_logs")
        .select("fsrs_rating,created_at")
        .eq("user_id", user_id)
        .gte("created_at", _iso_utc_days_ago(days))
        .execute()
        .data
        or []
    )

    rating_counts: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0}
    daily_counts: dict[str, int] = defaultdict(int)

    for row in logs:
        rating = row.get("fsrs_rating")
        if isinstance(rating, int) and rating in rating_counts:
            rating_counts[rating] += 1
        day = _to_day(row.get("created_at"))
        if day:
            daily_counts[day] += 1

    return {
        "window_days": days,
        "ratings": {
            "Again": rating_counts[1],
            "Hard": rating_counts[2],
            "Good": rating_counts[3],
            "Easy": rating_counts[4],
        },
        "daily_reviews": [
            {"date": day, "count": daily_counts[day]}
            for day in sorted(daily_counts)
        ],
    }
