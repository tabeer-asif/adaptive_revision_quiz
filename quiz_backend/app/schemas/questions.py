from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, Dict, List, Union, Literal


QuestionType = Literal["MCQ", "MULTI_MCQ", "NUMERIC", "SHORT", "OPEN"]


class CreateQuestionRequest(BaseModel):
    topic_id: int = Field(..., gt=0)
    text: str = Field(..., min_length=1)
    type: QuestionType
    # MCQ / MULTI_MCQ
    options: Optional[Dict[str, str]] = None

    # answer can vary by type:
    # MCQ -> str ("A")
    # MULTI_MCQ -> List[str] (["A","C"])
    # NUMERIC -> float
    # SHORT -> str
    # OPEN -> str (optional reference answer)
    answer: Optional[Union[str, float, List[str]]] = None

    difficulty: Optional[int] = Field(default=1, ge=1, le=5)
    # NUMERIC only
    tolerance: Optional[float] = Field(default=None, ge=0)
    # SHORT only
    keywords: Optional[List[str]] = None
    irt_a: Optional[float] = Field(default=None, ge=0.5, le=2.5)
    irt_b: Optional[float] = Field(default=None, ge=-3.0, le=3.0)
    irt_c: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    irt_thresholds: Optional[List[float]] = None # GRM thresholds for MULTI_MCQ
    image_url: Optional[str] = None

class BulkDeleteRequest(BaseModel):
    ids: List[int]