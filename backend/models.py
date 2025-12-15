from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class EventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    start: str
    end: Optional[str] = None

class ChatRequest(BaseModel):
    message: str