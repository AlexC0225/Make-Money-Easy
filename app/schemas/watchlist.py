from datetime import datetime

from pydantic import BaseModel, Field


class WatchlistCreateRequest(BaseModel):
    user_id: int
    code: str = Field(min_length=1, max_length=16)
    note: str | None = Field(default=None, max_length=255)


class WatchlistItemRead(BaseModel):
    id: int
    user_id: int
    code: str
    name: str
    market: str
    industry: str | None = None
    note: str | None = None
    created_at: datetime
