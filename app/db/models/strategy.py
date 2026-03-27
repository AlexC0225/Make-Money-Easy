from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class StrategyRun(Base):
    __tablename__ = "strategy_runs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    strategy_name: Mapped[str] = mapped_column(String(64), index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    signal: Mapped[str] = mapped_column(String(16), index=True)
    signal_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    signal_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    stock: Mapped["Stock"] = relationship()


class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    strategy_name: Mapped[str] = mapped_column(String(64), index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date] = mapped_column(Date, index=True)
    total_return: Mapped[float] = mapped_column(Float, default=0)
    max_drawdown: Mapped[float] = mapped_column(Float, default=0)
    win_rate: Mapped[float] = mapped_column(Float, default=0)
    profit_factor: Mapped[float] = mapped_column(Float, default=0)
    sharpe_ratio: Mapped[float] = mapped_column(Float, default=0)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    stock: Mapped["Stock"] = relationship()
