from fastapi import APIRouter, Depends
from app.supabase_client import supabase_db
from app.dependencies.auth import get_current_user

router = APIRouter()

@router.get("/topics")
def get_topics(user=Depends(get_current_user)):
    """
    Returns all available topics.
    """
    response = supabase_db.table("topics").select("*").execute()

    if not response.data:
        return []

    return response.data