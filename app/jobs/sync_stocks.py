from app.db.session import get_session_factory
from app.services.job_logging_service import JobLoggingService
from app.services.market_data_service import MarketDataService
from app.services.twstock_client import TwStockClient


def run_sync_stocks_job() -> dict[str, int]:
    logger = JobLoggingService()
    job_name = "sync-stock-universe"
    logger.log_event(job_name=job_name, status="RUNNING", event="started")

    session = get_session_factory()()
    try:
        service = MarketDataService(session, TwStockClient())
        synced_count = service.sync_stock_universe()
        session.commit()
        result = {"synced_count": synced_count}
        logger.log_event(job_name=job_name, status="SUCCESS", payload=result)
        return result
    except Exception as exc:
        session.rollback()
        logger.log_event(
            job_name=job_name,
            status="FAILED",
            event="failed",
            payload={"error": str(exc)},
        )
        raise
    finally:
        session.close()
