from app.db.session import get_session_factory
from app.services.etf_constituent_service import EtfConstituentService
from app.services.market_data_service import MarketDataService
from app.services.twstock_client import TwStockClient


def run_sync_stocks_job() -> dict[str, int]:
    session = get_session_factory()()
    try:
        service = MarketDataService(session, TwStockClient(), EtfConstituentService())
        synced_count = service.sync_stock_universe()
        session.commit()
        return {"synced_count": synced_count}
    finally:
        session.close()
