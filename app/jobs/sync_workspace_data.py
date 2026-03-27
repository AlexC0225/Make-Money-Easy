from datetime import datetime

from app.db.session import get_session_factory
from app.services.automation_service import AutomationService
from app.services.etf_constituent_service import EtfConstituentService
from app.services.market_data_service import MarketDataService
from app.services.trading_calendar_service import TradingCalendarService
from app.services.twstock_client import TwStockClient


def run_close_sync_workspace_data_job() -> dict[str, object]:
    now = datetime.now()
    if not TradingCalendarService().is_trading_day(now.date()):
        return {
            "skipped": True,
            "reason": "non_trading_day",
            "year": now.year,
            "month": now.month,
            "codes": [],
            "synced_codes": 0,
            "synced_rows": 0,
            "failed_codes": [],
        }

    session = get_session_factory()()
    try:
        twstock_client = TwStockClient()
        constituent_service = EtfConstituentService()
        automation_service = AutomationService(session, twstock_client, constituent_service)
        codes = automation_service.resolve_daily_sync_codes()
        market_data_service = MarketDataService(session, twstock_client, constituent_service)
        _, synced_codes, synced_rows, failed_codes = market_data_service.sync_history_batch(
            codes=codes,
            year=now.year,
            month=now.month,
        )
        session.commit()
        return {
            "skipped": False,
            "year": now.year,
            "month": now.month,
            "codes": codes,
            "synced_codes": synced_codes,
            "synced_rows": synced_rows,
            "failed_codes": failed_codes,
        }
    finally:
        session.close()
