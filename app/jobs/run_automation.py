from app.db.session import get_session_factory
from app.services.job_logging_service import JobLoggingService
from app.services.automation_service import AutomationService
from app.services.trading_calendar_service import TradingCalendarService
from app.services.twstock_client import TwStockClient


def run_daily_workspace_automation_job() -> dict[str, object]:
    logger = JobLoggingService()
    job_name = "run-daily-workspace-automation"
    logger.log_event(job_name=job_name, status="RUNNING", event="started")

    if not TradingCalendarService().is_trading_day():
        result = {
            "skipped": True,
            "reason": "non_trading_day",
            "processed_users": 0,
            "applied_users": 0,
            "failed_users": [],
        }
        logger.log_event(job_name=job_name, status="SKIPPED", payload=result)
        return result

    session = get_session_factory()()
    try:
        service = AutomationService(session, TwStockClient())
        summary = service.run_daily_automation()
        session.commit()
        result = {
            "skipped": False,
            "processed_users": summary.processed_users,
            "applied_users": summary.applied_users,
            "failed_users": summary.failed_users,
            "execution_details": summary.execution_details,
        }
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
