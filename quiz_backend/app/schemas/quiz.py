# app/schemas/quiz.py
from pydantic import BaseModel
from typing import List, Union, Optional
from uuid import UUID

class SubmitAnswerRequest(BaseModel):
    #user_id: UUID
    question_id: int
    # MCQ: "A" | MULTI_MCQ: ["A","B"] | NUMERIC: 6.3 | SHORT/OPEN: "text"
    selected_option: Union[str, List[str], float]
    response_time: float  # in seconds
    self_rating: Optional[int] = None  # User's self-assessed rating
    session_id: Optional[int] = None

# Optional: if want to fetch questions by topics
class TopicsRequest(BaseModel):
    topics: List[int]

class CreateTopicRequest(BaseModel):
    name: str
