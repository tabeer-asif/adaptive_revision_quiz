# app/schemas/quiz.py
from pydantic import BaseModel
from typing import Dict, List
from uuid import UUID

class SubmitAnswerRequest(BaseModel):
    #user_id: UUID
    question_id: int
    selected_option: Dict # e.g. {"A": true} or {"B": false}
    response_time: float  # in seconds

# Optional: if want to fetch questions by topics
class TopicsRequest(BaseModel):
    topics: List[int]