from datetime import datetime

from app.db.session import get_session_factory
from app.services.automation_service import AutomationService
from app.services.job_logging_service import JobLoggingService
from app.services.market_data_service import MarketDataService
from app.services.trading_calendar_service import TradingCalendarService
from app.services.twstock_client import TwStockClient


def run_close_sync_workspace_data_job() -> dict[str, object]:
    logger = JobLoggingService()
    job_name = "sync-workspace-close-data"
    logger.log_event(job_name=job_name, status="RUNNING", event="started")

    now = datetime.now()
    if not TradingCalendarService().is_trading_day(now.date()):
        result = {
            "skipped": True,
            "reason": "non_trading_day",
            "year": now.year,
            "month": now.month,
            "codes": [],
            "synced_codes": 0,
            "synced_rows": 0,
            "failed_codes": [],
        }
        logger.log_event(job_name=job_name, status="SKIPPED", payload=result)
        return result

    session = get_session_factory()()
    try:
        twstock_client = TwStockClient()
        automation_service = AutomationService(session, twstock_client)
        codes = automation_service.resolve_daily_sync_codes()
        market_data_service = MarketDataService(session, twstock_client)
        _, synced_codes, synced_rows, failed_codes = market_data_service.sync_history_batch(
            codes=codes,
            year=now.year,
            month=now.month,
        )
        session.commit()
        result = {
            "skipped": False,
            "year": now.year,
            "month": now.month,
            "codes": codes,
            "synced_codes": synced_codes,
            "synced_rows": synced_rows,
            "failed_codes": failed_codes,
        }
        logger.log_event(job_name=job_name, status="SUCCESS", payload=result)
        return result
    except Exception as exc:
        session.rollback()
        logger.log_event(
            job_name=job_name,
            status="FAILED",
            event="failed",
            payload={
                "year": now.year,
                "month": now.month,
                "error": str(exc),
            },
        )
        raise
    finally:
        session.close()
