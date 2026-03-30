from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class StockRead(BaseModel):
    id: int
    code: str
    name: str
    market: str
    industry: str | None = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class StockLookupRead(BaseModel):
    code: str
    name: str
    market: str
    industry: str | None = None
    latest_price: float | None = None


class HistoricalPriceRead(BaseModel):
    trade_date: date
    open_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None
    close_price: float | None = None
    volume: int | None = None
    turnover: float | None = None
    transaction_count: int | None = None


class HistoricalPricesResponse(BaseModel):
    code: str
    year: int
    month: int
    prices: list[HistoricalPriceRead]


class HistoricalRangeResponse(BaseModel):
    code: str
    start_date: date
    end_date: date
    prices: list[HistoricalPriceRead]


class RealtimeQuoteRead(BaseModel):
    code: str
    name: str | None = None
    quote_time: datetime
    latest_trade_price: float | None = None
    latest_trade_price_available: bool = True
    latest_trade_price_source: str = "realtime"
    warning_message: str | None = None
    reference_price: float | None = None
    open_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None
    accumulate_trade_volume: int | None = None
    best_bid_price: list[float] = Field(default_factory=list)
    best_ask_price: list[float] = Field(default_factory=list)
    best_bid_volume: list[int] = Field(default_factory=list)
    best_ask_volume: list[int] = Field(default_factory=list)


class StockSyncResponse(BaseModel):
    code: str
    name: str
    year: int
    month: int
    synced_count: int
