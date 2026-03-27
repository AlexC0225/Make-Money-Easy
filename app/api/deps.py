from collections.abc import Generator

from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.etf_constituent_service import EtfConstituentService
from app.services.twstock_client import TwStockClient


def get_db_session() -> Generator[Session, None, None]:
    yield from get_db()


def get_twstock_client() -> TwStockClient:
    return TwStockClient()


def get_etf_constituent_service() -> EtfConstituentService:
    return EtfConstituentService()
