from datetime import date

from pydantic import BaseModel


class MarketLeaderItem(BaseModel):
    code: str
    name: str
    close_price: float
    change_percent: float
    volume: int
    turnover: float | None = None


class MarketOverviewRead(BaseModel):
    as_of_date: date
    top_gainers: list[MarketLeaderItem]
    top_losers: list[MarketLeaderItem]
    top_volume: list[MarketLeaderItem]
