from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AutomationConfig(Base):
    __tablename__ = "automation_configs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    strategy_name: Mapped[str] = mapped_column(String(64), default="connors_rsi2_long")
    buy_quantity: Mapped[int] = mapped_column(Integer, default=1000)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="automation_config")
