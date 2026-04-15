from fastapi import APIRouter, Depends, HTTPException

from app.supabase_client import supabase_db
from app.dependencies.auth import get_current_user
from app.schemas.quiz import CreateTopicRequest

router = APIRouter()


@router.get("/topics")
def get_topics(user=Depends(get_current_user)):
    try:
        response = supabase_db.table("topics").select("*").execute()
        return response.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch topics: {str(e)}")

@router.post("/topics")
def create_topic(payload: CreateTopicRequest, user=Depends(get_current_user)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Topic name cannot be empty")

    existing = supabase_db.table("topics").select("id").eq("name", name).execute()
    if existing.data:
        raise HTTPException(status_code=409, detail="A topic with that name already exists")

    
    res = supabase_db.table("topics").insert({"name": name}).execute()
    

    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to create topic")

    return res.data[0]