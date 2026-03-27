from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.market_data import DailyPrice
from app.db.models.stock import Stock
from app.db.repositories.stock_repository import StockRepository
from app.schemas.market import MarketLeaderItem, MarketOverviewRead


class MarketServiceError(Exception):
    pass


@dataclass
class _MarketRow:
    code: str
    name: str
    close_price: float
    change_percent: float
    volume: int
    turnover: float | None


class MarketService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.stock_repository = StockRepository(session)

    def get_market_overview(self, limit: int = 10) -> MarketOverviewRead:
        latest_date = self.stock_repository.get_latest_trade_date()
        if latest_date is None:
            raise MarketServiceError("No market history found. Please sync data first.")

        rows: list[_MarketRow] = []
        latest_statement = (
            select(DailyPrice, Stock)
            .join(Stock, Stock.id == DailyPrice.stock_id)
            .where(DailyPrice.trade_date == latest_date)
        )
        latest_rows = self.session.execute(latest_statement).all()

        for daily_price, stock in latest_rows:
            previous_statement = (
                select(DailyPrice)
                .where(
                    DailyPrice.stock_id == stock.id,
                    DailyPrice.trade_date < latest_date,
                )
                .order_by(DailyPrice.trade_date.desc())
                .limit(1)
            )
            previous = self.session.scalar(previous_statement)
            if previous is None or previous.close_price in (None, 0) or daily_price.close_price is None:
                continue

            change_percent = (daily_price.close_price - previous.close_price) / previous.close_price
            rows.append(
                _MarketRow(
                    code=stock.code,
                    name=stock.name,
                    close_price=daily_price.close_price,
                    change_percent=change_percent,
                    volume=daily_price.volume or 0,
                    turnover=daily_price.turnover,
                )
            )

        if not rows:
            raise MarketServiceError("Not enough market history to build leaderboard.")

        top_gainers = sorted(rows, key=lambda item: item.change_percent, reverse=True)[:limit]
        top_losers = sorted(rows, key=lambda item: item.change_percent)[:limit]
        top_volume = sorted(rows, key=lambda item: item.volume, reverse=True)[:limit]

        return MarketOverviewRead(
            as_of_date=latest_date,
            top_gainers=[self._to_schema(item) for item in top_gainers],
            top_losers=[self._to_schema(item) for item in top_losers],
            top_volume=[self._to_schema(item) for item in top_volume],
        )

    @staticmethod
    def _to_schema(item: _MarketRow) -> MarketLeaderItem:
        return MarketLeaderItem(
            code=item.code,
            name=item.name,
            close_price=item.close_price,
            change_percent=item.change_percent,
            volume=item.volume,
            turnover=item.turnover,
        )
