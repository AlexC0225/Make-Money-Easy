from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.config import get_settings
from app.services.position_sizing_service import POSITION_SIZING_CASH_PERCENT, POSITION_SIZING_FIXED_SHARES


class StrategyDefinitionRead(BaseModel):
    name: str
    title: str
    description: str
    trade_frequency: str
    execution_timing: str
    is_long_only: bool


class StrategyExecutionRead(BaseModel):
    applied: bool
    action: str
    quantity: int
    status: str
    message: str
    available_cash: float | None = None
    market_value: float | None = None
    total_equity: float | None = None


class StrategySignalRead(BaseModel):
    id: int
    strategy_name: str
    stock_code: str
    stock_name: str
    industry: str | None = None
    signal: str
    signal_reason: str | None = None
    signal_time: datetime
    created_at: datetime | None = None
    snapshot: dict
    execution: StrategyExecutionRead | None = None


class StrategyRunRequest(BaseModel):
    user_id: int = Field(ge=1)
    code: str = Field(min_length=1)
    strategy_name: str = Field(min_length=1)
    execute_trade: bool = False
    position_sizing_mode: Literal["fixed_shares", "cash_percent"] = POSITION_SIZING_FIXED_SHARES
    buy_quantity: int = Field(default=1000, gt=0)
    cash_allocation_pct: float = Field(default=10.0, gt=0, le=100)

    @model_validator(mode="after")
    def validate_sizing_mode(self):
        lot_size = get_settings().default_lot_size
        if self.position_sizing_mode == POSITION_SIZING_FIXED_SHARES and self.buy_quantity % lot_size != 0:
            raise ValueError(f"buy_quantity must be a multiple of {lot_size}.")
        return self


class AutomationConfigRead(BaseModel):
    user_id: int
    enabled: bool
    strategy_name: str
    position_sizing_mode: Literal["fixed_shares", "cash_percent"]
    buy_quantity: int
    cash_allocation_pct: float
    max_open_positions: int
    updated_at: datetime | None = None


class AutomationConfigUpdateRequest(BaseModel):
    enabled: bool = True
    strategy_name: str = Field(min_length=1)
    position_sizing_mode: Literal["fixed_shares", "cash_percent"] = POSITION_SIZING_FIXED_SHARES
    buy_quantity: int = Field(default=1000, gt=0)
    cash_allocation_pct: float = Field(default=10.0, gt=0, le=100)
    max_open_positions: int = Field(default_factory=lambda: get_settings().max_open_positions, gt=0)

    @model_validator(mode="after")
    def validate_sizing_mode(self):
        lot_size = get_settings().default_lot_size
        if self.position_sizing_mode == POSITION_SIZING_FIXED_SHARES and self.buy_quantity % lot_size != 0:
            raise ValueError(f"buy_quantity must be a multiple of {lot_size}.")
        if self.position_sizing_mode == POSITION_SIZING_CASH_PERCENT and self.cash_allocation_pct <= 0:
            raise ValueError("cash_allocation_pct must be greater than zero for cash_percent mode.")
        return self


class BacktestResultRead(BaseModel):
    id: int
    strategy_name: str
    stock_code: str
    stock_name: str
    portfolio_codes: list[str] = Field(default_factory=list)
    is_portfolio: bool = False
    start_date: date
    end_date: date
    total_return: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    sharpe_ratio: float
    result: dict
    created_at: datetime


class BacktestRunRequest(BaseModel):
    user_id: int | None = Field(default=None, ge=1)
    code: str = Field(default="")
    strategy_name: str = Field(min_length=1)
    start_date: date
    end_date: date
    initial_cash: float = Field(gt=0)
    position_sizing_mode: Literal["fixed_shares", "cash_percent"] = POSITION_SIZING_FIXED_SHARES
    lot_size: int = Field(default=1000, gt=0)
    cash_allocation_pct: float = Field(default=10.0, gt=0, le=100)
    max_open_positions: int = Field(default_factory=lambda: get_settings().max_open_positions, gt=0)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date.")
        lot_size = get_settings().default_lot_size
        if self.position_sizing_mode == POSITION_SIZING_FIXED_SHARES and self.lot_size % lot_size != 0:
            raise ValueError(f"lot_size must be a multiple of {lot_size}.")
        return self
