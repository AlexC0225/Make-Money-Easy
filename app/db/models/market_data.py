from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DailyPrice(Base):
    __tablename__ = "daily_prices"
    __table_args__ = (UniqueConstraint("stock_id", "trade_date", name="uq_daily_prices_stock_date"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    open_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    high_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    low_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    close_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    turnover: Mapped[float | None] = mapped_column(Float, nullable=True)
    transaction_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    stock: Mapped["Stock"] = relationship(back_populates="daily_prices")


class RealtimeQuote(Base):
    __tablename__ = "realtime_quotes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    quote_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    latest_trade_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    open_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    high_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    low_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    accumulate_trade_volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    best_bid_price_json: Mapped[list[float]] = mapped_column(JSON, default=list)
    best_ask_price_json: Mapped[list[float]] = mapped_column(JSON, default=list)
    best_bid_volume_json: Mapped[list[int]] = mapped_column(JSON, default=list)
    best_ask_volume_json: Mapped[list[int]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    stock: Mapped["Stock"] = relationship(back_populates="realtime_quotes")
