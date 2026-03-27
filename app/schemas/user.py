from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AccountRead(BaseModel):
    id: int
    user_id: int
    initial_cash: float
    available_cash: float
    frozen_cash: float
    market_value: float
    total_equity: float

    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr
    initial_cash: float = Field(default=1_000_000, gt=0)


class UserLoginRequest(BaseModel):
    login: str = Field(min_length=3, max_length=255)


class UserRead(BaseModel):
    id: int
    username: str
    email: EmailStr
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserWithAccountRead(UserRead):
    account: AccountRead


class UserLoginResponse(BaseModel):
    user: UserWithAccountRead
    active_user_id: int
