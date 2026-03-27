from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator


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
    signal: str
    signal_reason: str | None = None
    signal_time: datetime
    snapshot: dict
    execution: StrategyExecutionRead | None = None


class StrategyRunRequest(BaseModel):
    user_id: int = Field(ge=1)
    code: str = Field(min_length=1)
    strategy_name: str = Field(min_length=1)
    execute_trade: bool = False
    buy_quantity: int = Field(default=1000, gt=0)


class AutomationConfigRead(BaseModel):
    user_id: int
    enabled: bool
    strategy_name: str
    buy_quantity: int
    updated_at: datetime | None = None


class AutomationConfigUpdateRequest(BaseModel):
    enabled: bool = True
    strategy_name: str = Field(min_length=1)
    buy_quantity: int = Field(default=1000, gt=0)


class BacktestResultRead(BaseModel):
    id: int
    strategy_name: str
    stock_code: str
    stock_name: str
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
    code: str = Field(min_length=1)
    strategy_name: str = Field(min_length=1)
    start_date: date
    end_date: date
    initial_cash: float = Field(gt=0)
    lot_size: int = Field(default=1000, gt=0)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date.")
        return self
