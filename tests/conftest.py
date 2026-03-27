from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db.session import get_engine, get_session_factory
from app.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("MME_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("MME_SCHEDULER_ENABLED", "false")

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
