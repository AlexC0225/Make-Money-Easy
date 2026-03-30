from dataclasses import dataclass
from datetime import date

from sqlalchemy import select

from app.db.models.stock import Stock
from app.db.models.watchlist import WatchlistItem
from app.db.repositories.stock_repository import StockRepository
from app.services.sync_progress_service import SyncProgressService
from app.services.twstock_client import TwStockClient


class MarketDataServiceError(Exception):
    pass


@dataclass(slots=True)
class SyncTargetStockItem:
    code: str
    name: str
    industry: str | None


@dataclass(slots=True)
class SyncTargetSelection:
    codes: list[str]
    watchlist_codes: list[str]
    default_pool_codes: list[str]
    default_pool_industries: list[str]
    default_pool_items: list[SyncTargetStockItem]
    tradable_pool_codes: list[str]
    tradable_pool_items: list[SyncTargetStockItem]
    selection_mode: str


class MarketDataService:
    DEFAULT_SYNC_POOL_INDUSTRIES = (
        "\u534a\u5c0e\u9ad4\u696d",
        "\u96fb\u8166\u53ca\u9031\u908a\u8a2d\u5099\u696d",
        "\u96fb\u5b50\u96f6\u7d44\u4ef6\u696d",
        "\u901a\u4fe1\u7db2\u8def\u696d",
        "\u5176\u4ed6\u96fb\u5b50\u696d",
        "\u91d1\u878d\u4fdd\u96aa\u696d",
        "\u8cc7\u8a0a\u670d\u52d9\u696d",
        "\u6578\u4f4d\u96f2\u7aef",
    )
    DEFAULT_SYNC_POOL_MARKET = "TSEC"
    DEFAULT_MINIMUM_RECENT_DAILY_TURNOVER = 100_000_000.0
    DEFAULT_RECENT_TURNOVER_LOOKBACK_DAYS = 20

    def __init__(
        self,
        session,
        twstock_client: TwStockClient,
    ) -> None:
        self.session = session
        self.twstock_client = twstock_client
        self.stock_repository = StockRepository(session)
        self.sync_progress_service = SyncProgressService()

    def sync_stock_universe(self, progress_run_id: str | None = None) -> int:
        stocks = self.twstock_client.list_stock_universe()
        if progress_run_id:
            self.sync_progress_service.start_run(
                progress_run_id,
                job_name="sync-stock-universe",
                total_codes=len(stocks),
            )
        synced_count = 0
        current_code: str | None = None
        try:
            for item in stocks:
                current_code = item.get("code")
                if progress_run_id:
                    self.sync_progress_service.set_current_code(progress_run_id, current_code)
                self.stock_repository.upsert_stock(**item)
                self.session.commit()
                synced_count += 1
                if progress_run_id:
                    self.sync_progress_service.mark_code_success(progress_run_id, current_code)
        except Exception as exc:
            self.session.rollback()
            if progress_run_id:
                self.sync_progress_service.mark_code_failure(progress_run_id, current_code, str(exc))
                self.sync_progress_service.fail_run(progress_run_id, str(exc))
            raise

        if progress_run_id:
            self.sync_progress_service.complete_run(progress_run_id)
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
        progress_run_id: str | None = None,
    ) -> tuple[SyncTargetSelection, int, int, list[str]]:
        selection = self.resolve_sync_targets(codes=codes, user_id=user_id)
        if progress_run_id:
            self.sync_progress_service.start_run(
                progress_run_id,
                job_name="sync-history",
                total_codes=len(selection.codes),
            )
        synced_codes = 0
        synced_rows = 0
        failed_codes: list[str] = []

        for code in selection.codes:
            try:
                if progress_run_id:
                    self.sync_progress_service.set_current_code(progress_run_id, code)
                synced_count = self.sync_history(code=code, year=year, month=month)
                self.session.commit()
                synced_rows += synced_count
                synced_codes += 1
                if progress_run_id:
                    self.sync_progress_service.mark_code_success(progress_run_id, code, synced_count)
            except Exception:
                self.session.rollback()
                failed_codes.append(code)
                if progress_run_id:
                    self.sync_progress_service.mark_code_failure(progress_run_id, code)

        if progress_run_id:
            self.sync_progress_service.complete_run(progress_run_id)
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
        progress_run_id: str | None = None,
    ) -> tuple[SyncTargetSelection, int, int, list[str]]:
        selection = self.resolve_sync_targets(codes=codes, user_id=user_id)
        if progress_run_id:
            self.sync_progress_service.start_run(
                progress_run_id,
                job_name="sync-history-range",
                total_codes=len(selection.codes),
            )
        synced_codes = 0
        synced_rows = 0
        failed_codes: list[str] = []

        for code in selection.codes:
            try:
                if progress_run_id:
                    self.sync_progress_service.set_current_code(progress_run_id, code)
                synced_count = self.sync_history_range(code=code, start_date=start_date, end_date=end_date)
                self.session.commit()
                synced_rows += synced_count
                synced_codes += 1
                if progress_run_id:
                    self.sync_progress_service.mark_code_success(progress_run_id, code, synced_count)
            except Exception:
                self.session.rollback()
                failed_codes.append(code)
                if progress_run_id:
                    self.sync_progress_service.mark_code_failure(progress_run_id, code)

        if progress_run_id:
            self.sync_progress_service.complete_run(progress_run_id)
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
                default_pool_codes=[],
                default_pool_industries=[],
                default_pool_items=[],
                tradable_pool_codes=[],
                tradable_pool_items=[],
                selection_mode="custom",
            )

        watchlist_codes = self._list_watchlist_codes(user_id)
        default_pool_items = self.list_default_sync_pool_items()
        default_pool_codes = self.list_default_sync_pool_codes()
        tradable_pool_items = self.list_default_tradable_pool_items()
        tradable_pool_codes = [item.code for item in tradable_pool_items]
        target_codes = self._normalize_codes([*watchlist_codes, *default_pool_codes])
        if not target_codes:
            raise MarketDataServiceError("No symbols available for synchronization.")

        return SyncTargetSelection(
            codes=target_codes,
            watchlist_codes=watchlist_codes,
            default_pool_codes=default_pool_codes,
            default_pool_industries=self.list_default_sync_pool_industries(),
            default_pool_items=default_pool_items,
            tradable_pool_codes=tradable_pool_codes,
            tradable_pool_items=tradable_pool_items,
            selection_mode="default",
        )

    def list_default_sync_pool_codes(self) -> list[str]:
        return [item.code for item in self.list_default_sync_pool_items()]

    def list_default_sync_pool_industries(self) -> list[str]:
        return self.stock_repository.list_active_industries(self.DEFAULT_SYNC_POOL_INDUSTRIES)

    def list_default_sync_pool_items(self) -> list[SyncTargetStockItem]:
        stocks = self.stock_repository.list_active_stocks_by_industries_and_market(
            self.DEFAULT_SYNC_POOL_INDUSTRIES,
            self.DEFAULT_SYNC_POOL_MARKET,
        )
        return [
            SyncTargetStockItem(code=stock.code, name=stock.name, industry=stock.industry)
            for stock in stocks
            if isinstance(stock.code, str) and isinstance(stock.name, str)
        ]

    def list_default_tradable_pool_codes(self) -> list[str]:
        return [item.code for item in self.list_default_tradable_pool_items()]

    def list_default_tradable_pool_items(self) -> list[SyncTargetStockItem]:
        stocks = self.stock_repository.list_active_stocks_by_industries_and_market(
            self.DEFAULT_SYNC_POOL_INDUSTRIES,
            self.DEFAULT_SYNC_POOL_MARKET,
        )
        return [
            SyncTargetStockItem(code=stock.code, name=stock.name, industry=stock.industry)
            for stock in stocks
            if (
                isinstance(stock.code, str)
                and isinstance(stock.name, str)
                and self._passes_recent_turnover_filter(stock.id)
            )
        ]

    def resolve_trading_target_codes(self, user_id: int | None = None) -> list[str]:
        watchlist_codes = self._list_watchlist_codes(user_id)
        tradable_codes = self.list_default_tradable_pool_codes()
        return self._normalize_codes([*watchlist_codes, *tradable_codes])

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

    def _passes_recent_turnover_filter(self, stock_id: int) -> bool:
        recent_prices = self.stock_repository.get_recent_daily_prices(
            stock_id,
            self.DEFAULT_RECENT_TURNOVER_LOOKBACK_DAYS,
        )
        if len(recent_prices) < self.DEFAULT_RECENT_TURNOVER_LOOKBACK_DAYS:
            return False

        return all(
            float(item.turnover or 0) >= self.DEFAULT_MINIMUM_RECENT_DAILY_TURNOVER
            for item in recent_prices
        )
