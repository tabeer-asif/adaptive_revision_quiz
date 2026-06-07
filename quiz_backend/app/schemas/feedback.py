from pydantic import BaseModel


class OpenFeedbackRequest(BaseModel):
    question_id: int
    student_answer: str


class OpenFeedbackResponse(BaseModel):
    strengths: str
    gaps: str
    hint: str
    encouragement: str
    model_answer: str
