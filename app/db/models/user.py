from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped["Account"] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    orders: Mapped[list["Order"]] = relationship(back_populates="user")
    trades: Mapped[list["Trade"]] = relationship(back_populates="user")
    positions: Mapped[list["Position"]] = relationship(back_populates="user")
    automation_config: Mapped["AutomationConfig | None"] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    initial_cash: Mapped[float] = mapped_column(Float, default=1_000_000)
    available_cash: Mapped[float] = mapped_column(Float, default=1_000_000)
    frozen_cash: Mapped[float] = mapped_column(Float, default=0)
    market_value: Mapped[float] = mapped_column(Float, default=0)
    total_equity: Mapped[float] = mapped_column(Float, default=1_000_000)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="account")
