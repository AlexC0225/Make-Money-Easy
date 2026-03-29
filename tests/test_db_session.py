from app.config import get_settings
from app.db.session import (
    _prepare_sqlite_database_url,
    get_engine,
    get_session_factory,
)


def test_prepare_sqlite_database_url_creates_parent_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    database_url = "sqlite:///./nested/data/app.db"
    prepared_url = _prepare_sqlite_database_url(database_url)

    assert (tmp_path / "nested" / "data").exists()
    assert prepared_url.startswith("sqlite:///")


def test_get_engine_connects_when_sqlite_directory_is_missing(tmp_path, monkeypatch):
    database_path = tmp_path / "runtime" / "db" / "app.db"
    monkeypatch.setenv("MME_DATABASE_URL", f"sqlite:///{database_path.as_posix()}")

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    engine = get_engine()
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("select 1").scalar_one() == 1
    finally:
        engine.dispose()
        get_settings.cache_clear()
        get_engine.cache_clear()
        get_session_factory.cache_clear()
