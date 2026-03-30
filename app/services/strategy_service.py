from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.core.enums import OrderSide
from app.db.models.order import Trade
from app.db.models.portfolio import Position
from app.db.models.stock import Stock
from app.db.models.strategy import StrategyRun
from app.db.repositories.stock_repository import StockRepository
from app.schemas.strategy import StrategyDefinitionRead, StrategyExecutionRead, StrategySignalRead
from app.services.order_service import OrderService, TradingServiceError
from app.services.position_sizing_service import (
    POSITION_SIZING_FIXED_SHARES,
    PositionSizingServiceError,
    resolve_buy_quantity,
)
from app.services.twstock_client import TwStockClient, TwStockClientError
from app.strategies.base import StrategySignal
from app.strategies.hybrid_tw_strategy import HybridTwStrategy
from app.strategies.larry_connors_rsi2_strategy import LarryConnorsRsi2LongStrategy
from app.strategies.tw_daily_open_momentum_strategy import TaiwanDailyOpenMomentumLongStrategy
from app.strategies.tw_momentum_breakout_strategy import TaiwanMomentumBreakoutLongStrategy


class StrategyServiceError(Exception):
    pass


class StrategyService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()
        self.stock_repository = StockRepository(session)
        self.strategies = {
            HybridTwStrategy.name: HybridTwStrategy(),
            LarryConnorsRsi2LongStrategy.name: LarryConnorsRsi2LongStrategy(),
            TaiwanDailyOpenMomentumLongStrategy.name: TaiwanDailyOpenMomentumLongStrategy(),
            TaiwanMomentumBreakoutLongStrategy.name: TaiwanMomentumBreakoutLongStrategy(),
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
        position_sizing_mode: str = POSITION_SIZING_FIXED_SHARES,
        buy_quantity: int = 1000,
        cash_allocation_pct: float = 10.0,
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
                position_sizing_mode=position_sizing_mode,
                buy_quantity=buy_quantity,
                cash_allocation_pct=cash_allocation_pct,
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

        self.session.refresh(strategy_run)
        return self._serialize_signal_run(strategy_run, execution=execution)

    def list_signals(
        self,
        strategy_name: str | None = None,
        limit: int | None = None,
        latest_only: bool = False,
        industry: str | None = None,
    ) -> list[StrategySignalRead]:
        statement = select(StrategyRun).join(Stock, StrategyRun.stock_id == Stock.id).options(selectinload(StrategyRun.stock)).order_by(
            StrategyRun.signal_time.desc(),
            StrategyRun.id.desc(),
        )
        if strategy_name:
            statement = statement.where(StrategyRun.strategy_name == strategy_name)
        normalized_industry = industry.strip() if industry else None
        if normalized_industry:
            statement = statement.where(
                Stock.industry.is_not(None),
                func.trim(Stock.industry) == normalized_industry,
            )

        rows = list(self.session.scalars(statement))
        if latest_only:
            latest_rows: list[StrategyRun] = []
            seen_keys: set[tuple[str, int]] = set()
            for row in rows:
                key = (row.strategy_name, row.stock_id)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                latest_rows.append(row)
            rows = latest_rows

        effective_limit = limit
        if effective_limit is None and not latest_only:
            effective_limit = 200
        if effective_limit is not None:
            rows = rows[:effective_limit]

        return [self._serialize_signal_run(row) for row in rows]

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
        position_sizing_mode: str,
        buy_quantity: int,
        cash_allocation_pct: float,
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

        if signal.signal == "BUY" and self._count_open_positions(user_id) >= self.settings.max_open_positions:
            return StrategyExecutionRead(
                applied=False,
                action="BUY",
                quantity=0,
                status="SKIPPED",
                message=f"Max open positions reached ({self.settings.max_open_positions}).",
            )

        if signal.signal == "SELL" and (position is None or position.quantity <= 0):
            return StrategyExecutionRead(
                applied=False,
                action="SELL",
                quantity=0,
                status="SKIPPED",
                message="No position exists, skipping sell.",
            )

        quantity = position.quantity if signal.signal == "SELL" else 0
        order_service = OrderService(self.session, twstock_client)

        try:
            if signal.signal == "BUY":
                account = order_service.user_repository.get_account_by_user_id(user_id)
                if account is None:
                    raise TradingServiceError("Account not found.")

                preview_quote = twstock_client.get_realtime_quote(code)
                fill_price = order_service._resolve_trade_price(preview_quote)
                quantity = resolve_buy_quantity(
                    available_cash=account.available_cash,
                    fill_price=fill_price,
                    lot_size=self.settings.default_lot_size,
                    fee_rate=self.settings.default_fee_rate,
                    position_sizing_mode=position_sizing_mode,
                    buy_quantity=buy_quantity,
                    cash_allocation_pct=cash_allocation_pct,
                )

            result = order_service.place_market_order(
                user_id=user_id,
                code=code,
                quantity=quantity,
                side=OrderSide.buy if signal.signal == "BUY" else OrderSide.sell,
                enforce_round_lot=signal.signal == "BUY" and position_sizing_mode == POSITION_SIZING_FIXED_SHARES,
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
        except (PositionSizingServiceError, TradingServiceError, TwStockClientError) as exc:
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

    @staticmethod
    def _serialize_signal_run(
        row: StrategyRun,
        execution: StrategyExecutionRead | None = None,
    ) -> StrategySignalRead:
        return StrategySignalRead(
            id=row.id,
            strategy_name=row.strategy_name,
            stock_code=row.stock.code,
            stock_name=row.stock.name,
            industry=row.stock.industry,
            signal=row.signal,
            signal_reason=row.signal_reason,
            signal_time=row.signal_time,
            created_at=row.created_at,
            snapshot=row.snapshot_json,
            execution=execution,
        )

    def _get_position(self, user_id: int, code: str) -> Position | None:
        stock = self.stock_repository.get_by_code(code)
        if stock is None:
            return None
        statement = select(Position).where(Position.user_id == user_id, Position.stock_id == stock.id)
        return self.session.scalar(statement)

    def _count_open_positions(self, user_id: int) -> int:
        statement = select(Position).where(Position.user_id == user_id, Position.quantity > 0)
        return len(list(self.session.scalars(statement)))
