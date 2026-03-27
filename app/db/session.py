from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.base import Base


@lru_cache
def get_engine():
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        engine = create_engine(
            settings.database_url,
            connect_args={
                "check_same_thread": False,
                "timeout": 30,
            },
        )

        @event.listens_for(engine, "connect")
        def configure_sqlite(dbapi_connection, _):  # pragma: no cover - DBAPI specific
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute("PRAGMA busy_timeout = 30000")
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.execute("PRAGMA synchronous = NORMAL")
            cursor.close()

        return engine

    return create_engine(settings.database_url)


@lru_cache
def get_session_factory():
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )


def get_db() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def create_db_and_tables() -> None:
    import app.db.models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())
