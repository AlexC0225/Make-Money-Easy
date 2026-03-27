from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.db.models.watchlist import WatchlistItem
from app.db.repositories.stock_repository import StockRepository
from app.schemas.watchlist import WatchlistItemRead
from app.services.twstock_client import TwStockClient


class WatchlistServiceError(Exception):
    pass


class WatchlistService:
    def __init__(self, session: Session, twstock_client: TwStockClient) -> None:
        self.session = session
        self.twstock_client = twstock_client
        self.stock_repository = StockRepository(session)

    def list_items(self, user_id: int) -> list[WatchlistItemRead]:
        statement = (
            select(WatchlistItem)
            .where(WatchlistItem.user_id == user_id)
            .options(selectinload(WatchlistItem.stock))
            .order_by(WatchlistItem.created_at.desc(), WatchlistItem.id.desc())
        )
        rows = list(self.session.scalars(statement))
        return [
            WatchlistItemRead(
                id=row.id,
                user_id=row.user_id,
                code=row.stock.code,
                name=row.stock.name,
                market=row.stock.market,
                note=row.note,
                created_at=row.created_at,
            )
            for row in rows
        ]

    def add_item(self, user_id: int, code: str, note: str | None = None) -> WatchlistItemRead:
        metadata = self.twstock_client.get_stock_metadata(code)
        stock = self.stock_repository.upsert_stock(**metadata)

        existing = self.session.scalar(
            select(WatchlistItem).where(WatchlistItem.user_id == user_id, WatchlistItem.stock_id == stock.id)
        )
        if existing is not None:
            raise WatchlistServiceError("This stock is already in the watchlist.")

        item = WatchlistItem(user_id=user_id, stock_id=stock.id, note=note)
        self.session.add(item)
        self.session.flush()
        self.session.refresh(item)
        self.session.refresh(stock)
        return WatchlistItemRead(
            id=item.id,
            user_id=item.user_id,
            code=stock.code,
            name=stock.name,
            market=stock.market,
            note=item.note,
            created_at=item.created_at,
        )

    def remove_item(self, user_id: int, code: str) -> None:
        stock = self.stock_repository.get_by_code(code)
        if stock is None:
            raise WatchlistServiceError("Stock not found.")

        result = self.session.execute(
            delete(WatchlistItem).where(WatchlistItem.user_id == user_id, WatchlistItem.stock_id == stock.id)
        )
        if result.rowcount == 0:
            raise WatchlistServiceError("Watchlist item not found.")
