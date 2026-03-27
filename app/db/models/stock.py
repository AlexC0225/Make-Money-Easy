from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Stock(Base):
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    market: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    industry: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    daily_prices: Mapped[list["DailyPrice"]] = relationship(
        back_populates="stock",
        cascade="all, delete-orphan",
    )
    realtime_quotes: Mapped[list["RealtimeQuote"]] = relationship(
        back_populates="stock",
        cascade="all, delete-orphan",
    )
    orders: Mapped[list["Order"]] = relationship(back_populates="stock")
    trades: Mapped[list["Trade"]] = relationship(back_populates="stock")
    positions: Mapped[list["Position"]] = relationship(back_populates="stock")
