from pydantic import BaseModel
from typing import Optional


class StartSessionRequest(BaseModel):
    topic_id: Optional[int] = None
    topic_ids: Optional[list[int]] = None


class EndSessionRequest(BaseModel):
    final_theta: Optional[float] = None
    termination_reason: Optional[str] = None