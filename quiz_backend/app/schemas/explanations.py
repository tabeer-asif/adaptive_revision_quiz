# app/schemas/explanations.py
from pydantic import BaseModel
from typing import Union, List, Optional


class ExplanationRequest(BaseModel):
    question_id: int
    topic_id: int
    # Mirrors selected_option from SubmitAnswerRequest so the frontend
    # can pass the same value without any conversion.
    selected_option: Union[str, List[str], float]
    self_rating: Optional[int] = None
    response_time: Optional[float] = None


class ExplanationResponse(BaseModel):
    explanation: str


class ChatMessage(BaseModel):
    role: str   # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    question_id: int
    topic_id: int
    user_answer: dict
    history: List[ChatMessage]
    message: str


class ChatResponse(BaseModel):
    reply: str
