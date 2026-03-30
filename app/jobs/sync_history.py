from datetime import datetime

from app.db.session import get_session_factory
from app.db.repositories.stock_repository import StockRepository
from app.services.market_data_service import MarketDataService
from app.services.twstock_client import TwStockClient


def run_sync_history_job(codes: list[str], year: int, month: int) -> dict[str, object]:
    session = get_session_factory()()
    try:
        service = MarketDataService(session, TwStockClient())
        _, synced_codes, synced_rows, skipped_codes, failed_codes = service.sync_history_batch(
            codes=codes,
            year=year,
            month=month,
        )
        return {
            "synced_codes": synced_codes,
            "synced_rows": synced_rows,
            "skipped_codes": skipped_codes,
            "failed_codes": failed_codes,
        }
    finally:
        session.close()


def run_sync_current_month_history_job(limit: int | None = None) -> dict[str, object]:
    now = datetime.now()
    session = get_session_factory()()
    try:
        repository = StockRepository(session)
        codes = [stock.code for stock in repository.list_active_stocks(limit=limit)]
        service = MarketDataService(session, TwStockClient())
        _, synced_codes, synced_rows, skipped_codes, failed_codes = service.sync_history_batch(
            codes=codes,
            year=now.year,
            month=now.month,
        )
        return {
            "year": now.year,
            "month": now.month,
            "synced_codes": synced_codes,
            "synced_rows": synced_rows,
            "skipped_codes": skipped_codes,
            "failed_codes": failed_codes,
        }
    finally:
        session.close()
