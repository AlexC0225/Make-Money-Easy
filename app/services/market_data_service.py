from dataclasses import dataclass
from datetime import date

from sqlalchemy import select

from app.db.models.stock import Stock
from app.db.models.watchlist import WatchlistItem
from app.db.repositories.stock_repository import StockRepository
from app.services.etf_constituent_service import EtfConstituentService
from app.services.twstock_client import TwStockClient


class MarketDataServiceError(Exception):
    pass


@dataclass(slots=True)
class SyncTargetSelection:
    codes: list[str]
    watchlist_codes: list[str]
    benchmark_codes: list[str]
    selection_mode: str
    source_url: str | None
    announce_date: str | None
    trade_date: str | None


class MarketDataService:
    def __init__(
        self,
        session,
        twstock_client: TwStockClient,
        constituent_service: EtfConstituentService,
    ) -> None:
        self.session = session
        self.twstock_client = twstock_client
        self.constituent_service = constituent_service
        self.stock_repository = StockRepository(session)

    def sync_stock_universe(self) -> int:
        stocks = self.twstock_client.list_stock_universe()
        synced_count = 0
        for item in stocks:
            self.stock_repository.upsert_stock(**item)
            synced_count += 1
        self.session.flush()
        return synced_count

    def sync_history(self, code: str, year: int, month: int) -> int:
        metadata = self.twstock_client.get_stock_metadata(code)
        history = self.twstock_client.get_history(code=code, year=year, month=month)
        stock = self.stock_repository.upsert_stock(**metadata)
        return self.stock_repository.upsert_daily_prices(stock_id=stock.id, prices=history)

    def sync_history_batch(
        self,
        codes: list[str] | None,
        year: int,
        month: int,
        user_id: int | None = None,
    ) -> tuple[SyncTargetSelection, int, int, list[str]]:
        selection = self.resolve_sync_targets(codes=codes, user_id=user_id)
        synced_codes = 0
        synced_rows = 0
        failed_codes: list[str] = []

        for code in selection.codes:
            try:
                synced_rows += self.sync_history(code=code, year=year, month=month)
                synced_codes += 1
            except Exception:
                failed_codes.append(code)

        self.session.flush()
        return selection, synced_codes, synced_rows, failed_codes

    def sync_history_range(self, code: str, start_date: date, end_date: date) -> int:
        metadata = self.twstock_client.get_stock_metadata(code)
        history = self.twstock_client.get_history_range(code=code, start_date=start_date, end_date=end_date)
        stock = self.stock_repository.upsert_stock(**metadata)
        return self.stock_repository.upsert_daily_prices(stock_id=stock.id, prices=history)

    def sync_history_range_batch(
        self,
        codes: list[str] | None,
        start_date: date,
        end_date: date,
        user_id: int | None = None,
    ) -> tuple[SyncTargetSelection, int, int, list[str]]:
        selection = self.resolve_sync_targets(codes=codes, user_id=user_id)
        synced_codes = 0
        synced_rows = 0
        failed_codes: list[str] = []

        for code in selection.codes:
            try:
                synced_rows += self.sync_history_range(code=code, start_date=start_date, end_date=end_date)
                synced_codes += 1
            except Exception:
                failed_codes.append(code)

        self.session.flush()
        return selection, synced_codes, synced_rows, failed_codes

    def resolve_sync_targets(
        self,
        codes: list[str] | None,
        user_id: int | None = None,
    ) -> SyncTargetSelection:
        manual_codes = self._normalize_codes(codes)
        if manual_codes:
            return SyncTargetSelection(
                codes=manual_codes,
                watchlist_codes=[],
                benchmark_codes=[],
                selection_mode="custom",
                source_url=None,
                announce_date=None,
                trade_date=None,
            )

        snapshot = self.constituent_service.get_0050_constituents()
        watchlist_codes = self._list_watchlist_codes(user_id)
        target_codes = self._normalize_codes([*watchlist_codes, *snapshot.codes])
        if not target_codes:
            raise MarketDataServiceError("No symbols available for synchronization.")

        return SyncTargetSelection(
            codes=target_codes,
            watchlist_codes=watchlist_codes,
            benchmark_codes=snapshot.codes,
            selection_mode="default",
            source_url=snapshot.source_url,
            announce_date=snapshot.announce_date,
            trade_date=snapshot.trade_date,
        )

    def _list_watchlist_codes(self, user_id: int | None) -> list[str]:
        if user_id is None:
            return []

        statement = (
            select(Stock.code)
            .join(WatchlistItem, WatchlistItem.stock_id == Stock.id)
            .where(WatchlistItem.user_id == user_id)
            .order_by(WatchlistItem.created_at.desc(), WatchlistItem.id.desc())
        )
        return [code for code in self.session.scalars(statement) if isinstance(code, str)]

    @staticmethod
    def _normalize_codes(codes: list[str] | None) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()

        for code in codes or []:
            value = code.strip()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)

        return normalized
