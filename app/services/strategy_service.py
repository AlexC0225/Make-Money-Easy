from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.enums import OrderSide
from app.db.models.order import Trade
from app.db.models.portfolio import Position
from app.db.models.strategy import StrategyRun
from app.db.repositories.stock_repository import StockRepository
from app.schemas.strategy import StrategyDefinitionRead, StrategyExecutionRead, StrategySignalRead
from app.services.order_service import OrderService, TradingServiceError
from app.services.twstock_client import TwStockClient, TwStockClientError
from app.strategies.base import StrategySignal
from app.strategies.hybrid_tw_strategy import HybridTwStrategy
from app.strategies.larry_connors_rsi2_strategy import LarryConnorsRsi2LongStrategy


class StrategyServiceError(Exception):
    pass


class StrategyService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.stock_repository = StockRepository(session)
        self.strategies = {
            HybridTwStrategy.name: HybridTwStrategy(),
            LarryConnorsRsi2LongStrategy.name: LarryConnorsRsi2LongStrategy(),
        }

    def list_strategy_definitions(self) -> list[StrategyDefinitionRead]:
        return [
            StrategyDefinitionRead(
                name=strategy.name,
                title=strategy.title,
                description=strategy.description,
                trade_frequency=strategy.trade_frequency,
                execution_timing=strategy.execution_timing,
                is_long_only=strategy.is_long_only,
            )
            for strategy in self.strategies.values()
        ]

    def get_strategy(self, strategy_name: str):
        strategy = self.strategies.get(strategy_name)
        if strategy is None:
            raise StrategyServiceError(f"Unknown strategy: {strategy_name}")
        return strategy

    def run_strategy(
        self,
        code: str,
        strategy_name: str,
        user_id: int | None = None,
        execute_trade: bool = False,
        buy_quantity: int = 1000,
        twstock_client: TwStockClient | None = None,
    ) -> StrategySignalRead:
        strategy = self.get_strategy(strategy_name)

        stock = self.stock_repository.get_by_code(code)
        if stock is None:
            raise StrategyServiceError("Stock not found. Please sync the stock first.")

        prices = self.stock_repository.get_daily_prices(stock.id)
        if not prices:
            raise StrategyServiceError("Historical prices not found. Please sync data first.")

        position_context = self._build_position_context(user_id=user_id, stock_id=stock.id) if user_id else None
        signal = self.evaluate_strategy(
            code=code,
            strategy_name=strategy_name,
            prices=prices,
            position_context=position_context,
        )

        snapshot = {
            **signal.snapshot,
            "trade_frequency": strategy.trade_frequency,
            "execution_timing": strategy.execution_timing,
        }
        strategy_run = StrategyRun(
            strategy_name=strategy_name,
            stock_id=stock.id,
            signal=signal.signal,
            signal_reason=signal.reason,
            signal_time=datetime.combine(signal.trade_date, datetime.min.time()),
            snapshot_json=snapshot,
        )
        self.session.add(strategy_run)
        self.session.flush()

        execution: StrategyExecutionRead | None = None
        if execute_trade:
            if user_id is None:
                raise StrategyServiceError("Executing a strategy requires user_id.")
            if twstock_client is None:
                raise StrategyServiceError("Executing a strategy requires a market data client.")
            execution = self._apply_signal_to_portfolio(
                user_id=user_id,
                code=stock.code,
                signal=signal,
                buy_quantity=buy_quantity,
                twstock_client=twstock_client,
            )
            strategy_run.snapshot_json = {
                **strategy_run.snapshot_json,
                "execution_status": execution.status,
                "execution_action": execution.action,
                "execution_quantity": execution.quantity,
                "execution_message": execution.message,
            }
            self.session.flush()

        return StrategySignalRead(
            id=strategy_run.id,
            strategy_name=strategy_run.strategy_name,
            stock_code=stock.code,
            stock_name=stock.name,
            signal=strategy_run.signal,
            signal_reason=strategy_run.signal_reason,
            signal_time=strategy_run.signal_time,
            snapshot=strategy_run.snapshot_json,
            execution=execution,
        )

    def list_signals(self, strategy_name: str | None = None, limit: int = 20) -> list[StrategySignalRead]:
        statement = select(StrategyRun).options(selectinload(StrategyRun.stock)).order_by(
            StrategyRun.signal_time.desc(),
            StrategyRun.id.desc(),
        )
        if strategy_name:
            statement = statement.where(StrategyRun.strategy_name == strategy_name)
        statement = statement.limit(limit)

        rows = list(self.session.scalars(statement))
        return [
            StrategySignalRead(
                id=row.id,
                strategy_name=row.strategy_name,
                stock_code=row.stock.code,
                stock_name=row.stock.name,
                signal=row.signal,
                signal_reason=row.signal_reason,
                signal_time=row.signal_time,
                snapshot=row.snapshot_json,
            )
            for row in rows
        ]

    def evaluate_strategy(
        self,
        code: str,
        strategy_name: str,
        prices,
        position_context: dict | None = None,
    ) -> StrategySignal:
        strategy = self.get_strategy(strategy_name)
        try:
            return strategy.evaluate(prices, position_context=position_context)
        except ValueError as exc:
            raise StrategyServiceError(str(exc)) from exc

    def run_strategy_batch(
        self,
        strategy_name: str,
        codes: list[str] | None = None,
        limit: int | None = None,
    ) -> tuple[int, int, list[str]]:
        if codes:
            stock_codes = codes
        else:
            stock_codes = [stock.code for stock in self.stock_repository.list_active_stocks(limit=limit)]

        processed = 0
        saved_signals = 0
        failed_codes: list[str] = []

        for code in stock_codes:
            try:
                self.run_strategy(code=code, strategy_name=strategy_name)
                processed += 1
                saved_signals += 1
            except StrategyServiceError:
                failed_codes.append(code)

        return processed, saved_signals, failed_codes

    def _apply_signal_to_portfolio(
        self,
        user_id: int,
        code: str,
        signal: StrategySignal,
        buy_quantity: int,
        twstock_client: TwStockClient,
    ) -> StrategyExecutionRead:
        position = self._get_position(user_id=user_id, code=code)

        if signal.signal == "HOLD":
            return StrategyExecutionRead(
                applied=False,
                action="NONE",
                quantity=0,
                status="SKIPPED",
                message="Signal is HOLD, no trade applied.",
            )

        if signal.signal == "BUY" and position is not None and position.quantity > 0:
            return StrategyExecutionRead(
                applied=False,
                action="BUY",
                quantity=0,
                status="SKIPPED",
                message="Position already exists, skipping duplicate buy.",
            )

        if signal.signal == "SELL" and (position is None or position.quantity <= 0):
            return StrategyExecutionRead(
                applied=False,
                action="SELL",
                quantity=0,
                status="SKIPPED",
                message="No position exists, skipping sell.",
            )

        quantity = buy_quantity if signal.signal == "BUY" else position.quantity
        order_service = OrderService(self.session, twstock_client)

        try:
            result = order_service.place_market_order(
                user_id=user_id,
                code=code,
                quantity=quantity,
                side=OrderSide.buy if signal.signal == "BUY" else OrderSide.sell,
                enforce_round_lot=signal.signal == "BUY",
            )
            return StrategyExecutionRead(
                applied=True,
                action=signal.signal,
                quantity=quantity,
                status="APPLIED",
                message="Strategy signal applied to portfolio.",
                available_cash=result.account.available_cash,
                market_value=result.account.market_value,
                total_equity=result.account.total_equity,
            )
        except (TradingServiceError, TwStockClientError) as exc:
            return StrategyExecutionRead(
                applied=False,
                action=signal.signal,
                quantity=quantity,
                status="FAILED",
                message=str(exc),
            )

    def _build_position_context(self, user_id: int, stock_id: int) -> dict | None:
        position = self.session.scalar(
            select(Position).where(Position.user_id == user_id, Position.stock_id == stock_id)
        )
        if position is None or position.quantity <= 0:
            return None

        last_buy_trade = self.session.scalar(
            select(Trade)
            .where(
                Trade.user_id == user_id,
                Trade.stock_id == stock_id,
                Trade.side == OrderSide.buy.value,
            )
            .order_by(Trade.executed_at.desc(), Trade.id.desc())
            .limit(1)
        )
        entry_date = last_buy_trade.executed_at.date() if last_buy_trade is not None else None

        return {
            "quantity": position.quantity,
            "entry_price": position.avg_cost,
            "entry_date": entry_date,
        }

    def _get_position(self, user_id: int, code: str) -> Position | None:
        stock = self.stock_repository.get_by_code(code)
        if stock is None:
            return None
        statement = select(Position).where(Position.user_id == user_id, Position.stock_id == stock.id)
        return self.session.scalar(statement)
