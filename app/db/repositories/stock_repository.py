from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models.market_data import DailyPrice, RealtimeQuote
from app.db.models.stock import Stock
from app.schemas.stock import HistoricalPriceRead, RealtimeQuoteRead


class StockRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_stocks(self, limit: int = 20, offset: int = 0) -> list[Stock]:
        statement = select(Stock).order_by(Stock.code).limit(limit).offset(offset)
        return list(self.session.scalars(statement))

    def list_active_stocks(self, limit: int | None = None) -> list[Stock]:
        statement = select(Stock).where(Stock.is_active.is_(True)).order_by(Stock.code)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement))

    def list_active_stocks_by_industries(self, industries: list[str] | tuple[str, ...]) -> list[Stock]:
        normalized_industries = [industry.strip() for industry in industries if industry.strip()]
        if not normalized_industries:
            return []

        statement = (
            select(Stock)
            .where(
                Stock.is_active.is_(True),
                Stock.industry.is_not(None),
                func.trim(Stock.industry).in_(normalized_industries),
            )
            .order_by(Stock.code)
        )
        return list(self.session.scalars(statement))

    def list_active_industries(self, industries: list[str] | tuple[str, ...]) -> list[str]:
        normalized_industries = [industry.strip() for industry in industries if industry.strip()]
        if not normalized_industries:
            return []

        statement = (
            select(func.trim(Stock.industry))
            .where(
                Stock.is_active.is_(True),
                Stock.industry.is_not(None),
                func.trim(Stock.industry).in_(normalized_industries),
            )
            .distinct()
            .order_by(func.trim(Stock.industry))
        )
        return [industry for industry in self.session.scalars(statement) if isinstance(industry, str)]

    def search_stocks(self, query: str, limit: int = 10) -> list[Stock]:
        normalized = query.strip()
        if not normalized:
            return []

        statement = (
            select(Stock)
            .where(
                or_(
                    Stock.code.ilike(f"%{normalized}%"),
                    Stock.name.ilike(f"%{normalized}%"),
                )
            )
            .order_by(Stock.code)
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def get_by_code(self, code: str) -> Stock | None:
        statement = select(Stock).where(Stock.code == code)
        return self.session.scalar(statement)

    def upsert_stock(
        self,
        code: str,
        name: str,
        market: str = "UNKNOWN",
        industry: str | None = None,
        is_active: bool = True,
    ) -> Stock:
        stock = self.get_by_code(code)
        if stock is None:
            stock = Stock(
                code=code,
                name=name,
                market=market,
                industry=industry,
                is_active=is_active,
            )
            self.session.add(stock)
            self.session.flush()
            return stock

        stock.name = name
        stock.market = market
        stock.industry = industry
        stock.is_active = is_active
        self.session.flush()
        return stock

    def upsert_daily_prices(self, stock_id: int, prices: list[HistoricalPriceRead]) -> int:
        synced_count = 0
        for item in prices:
            statement = select(DailyPrice).where(
                DailyPrice.stock_id == stock_id,
                DailyPrice.trade_date == item.trade_date,
            )
            daily_price = self.session.scalar(statement)
            if daily_price is None:
                daily_price = DailyPrice(stock_id=stock_id, trade_date=item.trade_date)
                self.session.add(daily_price)

            daily_price.open_price = item.open_price
            daily_price.high_price = item.high_price
            daily_price.low_price = item.low_price
            daily_price.close_price = item.close_price
            daily_price.volume = item.volume
            daily_price.turnover = item.turnover
            daily_price.transaction_count = item.transaction_count
            synced_count += 1

        self.session.flush()
        return synced_count

    def save_realtime_quote(self, stock_id: int, quote: RealtimeQuoteRead) -> RealtimeQuote:
        db_quote = RealtimeQuote(
            stock_id=stock_id,
            quote_time=quote.quote_time,
            latest_trade_price=quote.latest_trade_price,
            open_price=quote.open_price,
            high_price=quote.high_price,
            low_price=quote.low_price,
            accumulate_trade_volume=quote.accumulate_trade_volume,
            best_bid_price_json=quote.best_bid_price,
            best_ask_price_json=quote.best_ask_price,
            best_bid_volume_json=quote.best_bid_volume,
            best_ask_volume_json=quote.best_ask_volume,
        )
        self.session.add(db_quote)
        self.session.flush()
        return db_quote

    def get_daily_prices(
        self,
        stock_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[DailyPrice]:
        statement = select(DailyPrice).where(DailyPrice.stock_id == stock_id)
        if start_date is not None:
            statement = statement.where(DailyPrice.trade_date >= start_date)
        if end_date is not None:
            statement = statement.where(DailyPrice.trade_date <= end_date)
        statement = statement.order_by(DailyPrice.trade_date.asc())
        return list(self.session.scalars(statement))

    def get_latest_trade_date(self):
        statement = select(DailyPrice.trade_date).order_by(DailyPrice.trade_date.desc()).limit(1)
        return self.session.scalar(statement)

    def get_latest_price(self, stock_id: int) -> float | None:
        latest_quote = self.session.scalar(
            select(RealtimeQuote)
            .where(RealtimeQuote.stock_id == stock_id)
            .order_by(RealtimeQuote.quote_time.desc(), RealtimeQuote.id.desc())
            .limit(1)
        )
        if latest_quote is not None:
            for candidate in (
                latest_quote.latest_trade_price,
                latest_quote.open_price,
                latest_quote.high_price,
                latest_quote.low_price,
            ):
                if candidate is not None and candidate > 0:
                    return float(candidate)

        latest_daily = self.session.scalar(
            select(DailyPrice)
            .where(DailyPrice.stock_id == stock_id)
            .order_by(DailyPrice.trade_date.desc())
            .limit(1)
        )
        if latest_daily is not None and latest_daily.close_price is not None:
            return float(latest_daily.close_price)
        return None
