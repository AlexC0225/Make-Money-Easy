from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.db.models.portfolio import Position
from app.db.models.user import Account
from app.db.repositories.stock_repository import StockRepository
from app.db.repositories.user_repository import UserRepository
from app.schemas.portfolio import (
    PortfolioBootstrapRequest,
    PortfolioBootstrapResponse,
    PortfolioSummaryRead,
    PositionRead,
)
from app.services.twstock_client import TwStockClient
from app.services.user_service import UserService


class PortfolioService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.stock_repository = StockRepository(session)
        self.user_repository = UserRepository(session)

    def get_summary(self, user_id: int) -> PortfolioSummaryRead:
        account = self._get_account(user_id)
        positions = list(self.session.scalars(select(Position).where(Position.user_id == user_id)))
        unrealized_pnl = sum(position.unrealized_pnl for position in positions)
        realized_pnl = sum(position.realized_pnl for position in positions)

        return PortfolioSummaryRead(
            user_id=user_id,
            available_cash=account.available_cash,
            frozen_cash=account.frozen_cash,
            market_value=account.market_value,
            total_equity=account.total_equity,
            unrealized_pnl=unrealized_pnl,
            realized_pnl=realized_pnl,
        )

    def list_positions(self, user_id: int, include_closed: bool = False) -> list[PositionRead]:
        self._get_account(user_id)
        statement = (
            select(Position)
            .where(Position.user_id == user_id)
            .options(selectinload(Position.stock))
            .order_by(Position.updated_at.desc(), Position.id.desc())
        )
        positions = list(self.session.scalars(statement))
        if not include_closed:
            positions = [position for position in positions if position.quantity > 0]

        return [
            PositionRead(
                stock_code=position.stock.code,
                stock_name=position.stock.name,
                quantity=position.quantity,
                avg_cost=position.avg_cost,
                market_price=position.market_price,
                unrealized_pnl=position.unrealized_pnl,
                realized_pnl=position.realized_pnl,
                updated_at=position.updated_at,
            )
            for position in positions
        ]

    def _get_account(self, user_id: int) -> Account:
        statement = select(Account).where(Account.user_id == user_id)
        account = self.session.scalar(statement)
        if account is None:
            raise ValueError("Account not found.")
        return account

    def bootstrap_portfolio(
        self,
        payload: PortfolioBootstrapRequest,
        twstock_client: TwStockClient,
    ) -> PortfolioBootstrapResponse:
        if payload.user_id is None:
            existing_user = self.user_repository.get_single_user()
            user = existing_user if existing_user is not None else UserService(self.session).create_user(payload)
        else:
            user = self.user_repository.get_user(payload.user_id)
            if user is None:
                raise ValueError("User not found.")

        user.username = payload.username
        user.email = payload.email

        account = self.user_repository.get_account_by_user_id(user.id)
        if account is None:
            account = self.user_repository.create_account(user.id, payload.initial_cash)

        account.initial_cash = payload.initial_cash
        account.available_cash = payload.available_cash
        account.frozen_cash = 0

        self.session.execute(delete(Position).where(Position.user_id == user.id))
        self.session.flush()

        market_value = 0.0
        for item in payload.positions:
            metadata = twstock_client.get_stock_metadata(item.code)
            stock = self.stock_repository.upsert_stock(**metadata)
            market_price = item.market_price or item.avg_cost
            unrealized_pnl = (market_price - item.avg_cost) * item.quantity
            position = Position(
                user_id=user.id,
                stock_id=stock.id,
                quantity=item.quantity,
                avg_cost=item.avg_cost,
                market_price=market_price,
                unrealized_pnl=unrealized_pnl,
                realized_pnl=0,
            )
            self.session.add(position)
            market_value += item.quantity * market_price

        account.market_value = market_value
        account.total_equity = account.available_cash + account.market_value
        self.session.flush()
        self.session.refresh(user)
        self.session.refresh(account)

        positions = self.list_positions(user.id, include_closed=True)
        return PortfolioBootstrapResponse(
            user_id=user.id,
            username=user.username,
            email=user.email,
            initial_cash=account.initial_cash,
            available_cash=account.available_cash,
            market_value=account.market_value,
            total_equity=account.total_equity,
            positions=positions,
        )
