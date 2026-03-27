from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class PositionRead(BaseModel):
    stock_code: str
    stock_name: str
    quantity: int
    avg_cost: float
    market_price: float
    unrealized_pnl: float
    realized_pnl: float
    updated_at: datetime


class PortfolioSummaryRead(BaseModel):
    user_id: int
    available_cash: float
    frozen_cash: float
    market_value: float
    total_equity: float
    unrealized_pnl: float
    realized_pnl: float


class ManualPositionInput(BaseModel):
    code: str = Field(min_length=1, max_length=16)
    quantity: int = Field(gt=0)
    avg_cost: float = Field(gt=0)
    market_price: float | None = Field(default=None, gt=0)


class PortfolioBootstrapRequest(BaseModel):
    user_id: int | None = None
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr
    initial_cash: float = Field(gt=0)
    available_cash: float = Field(ge=0)
    positions: list[ManualPositionInput] = Field(default_factory=list)


class PortfolioBootstrapResponse(BaseModel):
    user_id: int
    username: str
    email: EmailStr
    initial_cash: float
    available_cash: float
    market_value: float
    total_equity: float
    positions: list[PositionRead]
