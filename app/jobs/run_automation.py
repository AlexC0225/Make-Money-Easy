from app.db.session import get_session_factory
from app.services.automation_service import AutomationService
from app.services.etf_constituent_service import EtfConstituentService
from app.services.trading_calendar_service import TradingCalendarService
from app.services.twstock_client import TwStockClient


def run_daily_workspace_automation_job() -> dict[str, object]:
    if not TradingCalendarService().is_trading_day():
        return {
            "skipped": True,
            "reason": "non_trading_day",
            "processed_users": 0,
            "applied_users": 0,
            "failed_users": [],
        }

    session = get_session_factory()()
    try:
        service = AutomationService(session, TwStockClient(), EtfConstituentService())
        summary = service.run_daily_automation()
        session.commit()
        return {
            "skipped": False,
            "processed_users": summary.processed_users,
            "applied_users": summary.applied_users,
            "failed_users": summary.failed_users,
        }
    finally:
        session.close()
