from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.core.enums import OrderSide, OrderStatus, OrderType
from app.db.models.order import Order, Trade
from app.db.models.portfolio import Position
from app.db.models.user import Account
from app.db.repositories.stock_repository import StockRepository
from app.db.repositories.user_repository import UserRepository
from app.services.twstock_client import TwStockClient
from app.utils.fees import calculate_fee, calculate_tax


class TradingServiceError(Exception):
    pass


@dataclass
class OrderExecutionResult:
    order: Order
    trade: Trade
    account: Account


class OrderService:
    def __init__(self, session: Session, twstock_client: TwStockClient) -> None:
        self.session = session
        self.twstock_client = twstock_client
        self.settings = get_settings()
        self.user_repository = UserRepository(session)
        self.stock_repository = StockRepository(session)

    def place_market_order(
        self,
        user_id: int,
        code: str,
        quantity: int,
        side: OrderSide,
        enforce_round_lot: bool = True,
    ) -> OrderExecutionResult:
        account = self.user_repository.get_account_by_user_id(user_id)
        if account is None:
            raise TradingServiceError("Account not found.")

        if enforce_round_lot and quantity % self.settings.default_lot_size != 0:
            raise TradingServiceError(
                f"Quantity must be a multiple of {self.settings.default_lot_size} shares."
            )

        metadata = self.twstock_client.get_stock_metadata(code)
        quote = self.twstock_client.get_realtime_quote(code)
        fill_price = self._resolve_trade_price(quote)

        stock = self.stock_repository.upsert_stock(**metadata)
        self.stock_repository.save_realtime_quote(stock_id=stock.id, quote=quote)

        order = Order(
            user_id=user_id,
            stock_id=stock.id,
            side=side.value,
            order_type=OrderType.market.value,
            price=fill_price,
            quantity=quantity,
            status=OrderStatus.filled.value,
            filled_quantity=quantity,
            avg_fill_price=fill_price,
        )
        self.session.add(order)
        self.session.flush()

        trade_amount = fill_price * quantity
        fee = calculate_fee(trade_amount, self.settings.default_fee_rate)
        tax = calculate_tax(trade_amount, self.settings.default_tax_rate) if side is OrderSide.sell else 0

        if side is OrderSide.buy:
            self._execute_buy(account=account, stock_id=stock.id, quantity=quantity, fill_price=fill_price, fee=fee)
        else:
            self._execute_sell(
                account=account,
                stock_id=stock.id,
                quantity=quantity,
                fill_price=fill_price,
                fee=fee,
                tax=tax,
            )

        trade = Trade(
            order_id=order.id,
            user_id=user_id,
            stock_id=stock.id,
            side=side.value,
            fill_price=fill_price,
            fill_quantity=quantity,
            fee=fee,
            tax=tax,
        )
        self.session.add(trade)
        self.session.flush()
        self.session.refresh(order)

        refreshed_account = self._refresh_account_metrics(user_id)
        return OrderExecutionResult(order=order, trade=trade, account=refreshed_account)

    def list_orders(self, user_id: int) -> list[Order]:
        statement = (
            select(Order)
            .where(Order.user_id == user_id)
            .options(selectinload(Order.stock))
            .order_by(Order.created_at.desc(), Order.id.desc())
        )
        return list(self.session.scalars(statement))

    def list_trades(self, user_id: int) -> list[Trade]:
        statement = (
            select(Trade)
            .where(Trade.user_id == user_id)
            .options(selectinload(Trade.stock))
            .order_by(Trade.executed_at.desc(), Trade.id.desc())
        )
        return list(self.session.scalars(statement))

    def _execute_buy(self, account: Account, stock_id: int, quantity: int, fill_price: float, fee: int) -> None:
        total_cost = fill_price * quantity + fee
        if account.available_cash < total_cost:
            raise TradingServiceError("Insufficient available cash.")

        position = self._get_or_create_position(account.user_id, stock_id)
        existing_cost = position.avg_cost * position.quantity
        new_quantity = position.quantity + quantity
        new_total_cost = existing_cost + (fill_price * quantity) + fee

        position.quantity = new_quantity
        position.avg_cost = new_total_cost / new_quantity
        position.market_price = fill_price
        position.unrealized_pnl = (position.market_price - position.avg_cost) * position.quantity
        account.available_cash -= total_cost

    def _execute_sell(
        self,
        account: Account,
        stock_id: int,
        quantity: int,
        fill_price: float,
        fee: int,
        tax: int,
    ) -> None:
        position = self._get_position(account.user_id, stock_id)
        if position is None or position.quantity < quantity:
            raise TradingServiceError("Insufficient position quantity.")

        net_proceeds = (fill_price * quantity) - fee - tax
        realized_delta = net_proceeds - (position.avg_cost * quantity)
        remaining_quantity = position.quantity - quantity

        position.quantity = remaining_quantity
        position.market_price = fill_price
        position.realized_pnl += realized_delta
        position.unrealized_pnl = (position.market_price - position.avg_cost) * remaining_quantity
        if remaining_quantity == 0:
            position.avg_cost = 0
            position.unrealized_pnl = 0

        account.available_cash += net_proceeds

    def _get_or_create_position(self, user_id: int, stock_id: int) -> Position:
        position = self._get_position(user_id, stock_id)
        if position is None:
            position = Position(user_id=user_id, stock_id=stock_id, quantity=0, avg_cost=0, market_price=0)
            self.session.add(position)
            self.session.flush()
        return position

    def _get_position(self, user_id: int, stock_id: int) -> Position | None:
        statement = select(Position).where(Position.user_id == user_id, Position.stock_id == stock_id)
        return self.session.scalar(statement)

    def _resolve_trade_price(self, quote) -> float:
        for candidate in (
            getattr(quote, "reference_price", None),
            quote.latest_trade_price,
            quote.open_price,
            quote.high_price,
            quote.low_price,
        ):
            if candidate is not None and candidate > 0:
                return candidate
        raise TradingServiceError("Unable to resolve a valid trade price from quote data.")

    def _refresh_account_metrics(self, user_id: int) -> Account:
        account = self.user_repository.get_account_by_user_id(user_id)
        if account is None:
            raise TradingServiceError("Account not found.")

        positions = list(self.session.scalars(select(Position).where(Position.user_id == user_id)))
        account.market_value = sum(position.quantity * position.market_price for position in positions)
        account.total_equity = account.available_cash + account.frozen_cash + account.market_value
        self.session.flush()
        return account
