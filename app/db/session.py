from collections.abc import Generator
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.base import Base


def _prepare_sqlite_database_url(database_url: str) -> str:
    url = make_url(database_url)
    database = url.database

    if not database or database == ":memory:" or database.startswith("file:"):
        return database_url

    database_path = Path(database)
    if not database_path.is_absolute():
        database_path = Path.cwd() / database_path

    database_path.parent.mkdir(parents=True, exist_ok=True)
    return url.set(database=str(database_path)).render_as_string(hide_password=False)


@lru_cache
def get_engine():
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        database_url = _prepare_sqlite_database_url(settings.database_url)
        engine = create_engine(
            database_url,
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

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _apply_schema_updates(engine)


def _apply_schema_updates(engine) -> None:
    with engine.begin() as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if "automation_configs" not in tables:
            return

        columns = {column["name"] for column in inspector.get_columns("automation_configs")}
        if "position_sizing_mode" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE automation_configs ADD COLUMN position_sizing_mode VARCHAR(32) NOT NULL DEFAULT 'fixed_shares'"
            )
        if "cash_allocation_pct" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE automation_configs ADD COLUMN cash_allocation_pct FLOAT NOT NULL DEFAULT 10.0"
            )
        if "max_open_positions" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE automation_configs ADD COLUMN max_open_positions INTEGER NOT NULL DEFAULT 20"
            )
