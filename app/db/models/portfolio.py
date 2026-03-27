from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("user_id", "stock_id", name="uq_positions_user_stock"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    avg_cost: Mapped[float] = mapped_column(Float, default=0)
    market_price: Mapped[float] = mapped_column(Float, default=0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="positions")
    stock: Mapped["Stock"] = relationship(back_populates="positions")
