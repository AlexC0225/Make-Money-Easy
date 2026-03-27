from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    side: Mapped[str] = mapped_column(String(8))
    order_type: Mapped[str] = mapped_column(String(16), default="MARKET")
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="FILLED")
    filled_quantity: Mapped[int] = mapped_column(Integer, default=0)
    avg_fill_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="orders")
    stock: Mapped["Stock"] = relationship(back_populates="orders")
    trades: Mapped[list["Trade"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    side: Mapped[str] = mapped_column(String(8))
    fill_price: Mapped[float] = mapped_column(Float)
    fill_quantity: Mapped[int] = mapped_column(Integer)
    fee: Mapped[int] = mapped_column(Integer, default=0)
    tax: Mapped[int] = mapped_column(Integer, default=0)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    order: Mapped["Order"] = relationship(back_populates="trades")
    user: Mapped["User"] = relationship(back_populates="trades")
    stock: Mapped["Stock"] = relationship(back_populates="trades")
