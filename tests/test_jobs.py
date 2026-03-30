from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.api.deps import get_twstock_client
from app.db.models.stock import Stock
from app.db.session import get_session_factory
from app.services.market_data_service import MarketDataService
from tests.test_stocks import FakeTwStockClient


def test_sync_stock_universe_job(client):
    client.app.dependency_overrides[get_twstock_client] = FakeTwStockClient

    response = client.post("/api/v1/jobs/sync/stocks")

    assert response.status_code == 200
    payload = response.json()
    assert payload["synced_count"] == 2

    stocks_response = client.get("/api/v1/stocks?limit=10")
    stocks = stocks_response.json()
    assert len(stocks) == 2


def test_sync_history_batch_job(client):
    client.app.dependency_overrides[get_twstock_client] = FakeTwStockClient

    response = client.post(
        "/api/v1/jobs/sync/history",
        json={"codes": ["2330", "2317"], "year": 2026, "month": 3},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["synced_codes"] == 2
    assert payload["synced_rows"] == 2
    assert payload["failed_codes"] == []


def test_sync_targets_default_to_watchlist_plus_default_pool(client):
    client.app.dependency_overrides[get_twstock_client] = FakeTwStockClient

    sync_stocks_response = client.post("/api/v1/jobs/sync/stocks")
    assert sync_stocks_response.status_code == 200

    bootstrap_response = client.post(
        "/api/v1/portfolio/bootstrap",
        json={
            "username": "sync-user",
            "email": "sync@example.com",
            "initial_cash": 1_000_000,
            "available_cash": 1_000_000,
            "positions": [],
        },
    )
    assert bootstrap_response.status_code == 200
    user_id = bootstrap_response.json()["user_id"]

    create_watchlist_response = client.post(
        "/api/v1/watchlist",
        json={"user_id": user_id, "code": "2317", "note": "focus"},
    )
    assert create_watchlist_response.status_code == 201

    preview_response = client.get(f"/api/v1/jobs/sync/targets?user_id={user_id}")

    assert preview_response.status_code == 200
    preview_payload = preview_response.json()
    assert preview_payload["selection_mode"] == "default"
    assert preview_payload["watchlist_codes"] == ["2317"]
    assert preview_payload["default_pool_codes"] == ["2317", "2330"]
    assert preview_payload["codes"] == ["2317", "2330"]
    assert preview_payload["default_pool_industries"] == [
        "\u534a\u5c0e\u9ad4\u696d",
        "\u96fb\u8166\u53ca\u9031\u908a\u8a2d\u5099\u696d",
    ]
    assert preview_payload["default_pool_items"] == [
        {"code": "2317", "name": "HonHai", "industry": "\u96fb\u8166\u53ca\u9031\u908a\u8a2d\u5099\u696d"},
        {"code": "2330", "name": "TSMC", "industry": "\u534a\u5c0e\u9ad4\u696d"},
    ]

    sync_response = client.post(
        "/api/v1/jobs/sync/history",
        json={"user_id": user_id, "year": 2026, "month": 3},
    )

    assert sync_response.status_code == 200
    sync_payload = sync_response.json()
    assert sync_payload["selection_mode"] == "default"
    assert sync_payload["codes"] == ["2317", "2330"]
    assert sync_payload["default_pool_items"] == [
        {"code": "2317", "name": "HonHai", "industry": "\u96fb\u8166\u53ca\u9031\u908a\u8a2d\u5099\u696d"},
        {"code": "2330", "name": "TSMC", "industry": "\u534a\u5c0e\u9ad4\u696d"},
    ]
    assert sync_payload["synced_codes"] == 2
    assert sync_payload["failed_codes"] == []


def test_sync_history_range_uses_default_targets_when_codes_omitted(client):
    client.app.dependency_overrides[get_twstock_client] = FakeTwStockClient

    sync_stocks_response = client.post("/api/v1/jobs/sync/stocks")
    assert sync_stocks_response.status_code == 200

    bootstrap_response = client.post(
        "/api/v1/portfolio/bootstrap",
        json={
            "username": "range-sync-user",
            "email": "range-sync@example.com",
            "initial_cash": 1_000_000,
            "available_cash": 1_000_000,
            "positions": [],
        },
    )
    assert bootstrap_response.status_code == 200
    user_id = bootstrap_response.json()["user_id"]

    watchlist_response = client.post(
        "/api/v1/watchlist",
        json={"user_id": user_id, "code": "2317", "note": "focus"},
    )
    assert watchlist_response.status_code == 201

    response = client.post(
        "/api/v1/jobs/sync/history-range",
        json={
            "user_id": user_id,
            "start_date": "2026-03-24",
            "end_date": "2026-03-26",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["selection_mode"] == "default"
    assert payload["codes"] == ["2317", "2330"]
    assert payload["default_pool_items"] == [
        {"code": "2317", "name": "HonHai", "industry": "\u96fb\u8166\u53ca\u9031\u908a\u8a2d\u5099\u696d"},
        {"code": "2330", "name": "TSMC", "industry": "\u534a\u5c0e\u9ad4\u696d"},
    ]
    assert payload["synced_codes"] == 2
    assert payload["failed_codes"] == []


def test_sync_history_range_only_uses_manual_codes_when_provided(client):
    client.app.dependency_overrides[get_twstock_client] = FakeTwStockClient

    response = client.post(
        "/api/v1/jobs/sync/history-range",
        json={
            "codes": ["2330", "2454"],
            "start_date": "2026-03-24",
            "end_date": "2026-03-26",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["selection_mode"] == "custom"
    assert payload["codes"] == ["2330", "2454"]
    assert payload["watchlist_codes"] == []
    assert payload["default_pool_codes"] == []
    assert payload["default_pool_industries"] == []
    assert payload["default_pool_items"] == []
    assert payload["synced_codes"] == 2
    assert payload["failed_codes"] == []


def test_sync_history_range_isolates_failed_code_writes(client, monkeypatch):
    client.app.dependency_overrides[get_twstock_client] = FakeTwStockClient
    original_sync_history_range = MarketDataService.sync_history_range

    def flaky_sync_history_range(self, code, start_date, end_date):
        if code == "2454":
            raise OperationalError("UPDATE daily_prices ...", {}, Exception("database is locked"))
        return original_sync_history_range(self, code, start_date, end_date)

    monkeypatch.setattr(
        "app.services.market_data_service.MarketDataService.sync_history_range",
        flaky_sync_history_range,
    )

    response = client.post(
        "/api/v1/jobs/sync/history-range",
        json={
            "codes": ["2330", "2454"],
            "start_date": "2026-03-24",
            "end_date": "2026-03-26",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["synced_codes"] == 1
    assert payload["failed_codes"] == ["2454"]

    session = get_session_factory()()
    try:
        stock = session.execute(select(Stock).where(Stock.code == "2330")).scalar_one()
        prices = stock.daily_prices
        assert len(prices) == 3
    finally:
        session.close()


def test_sync_history_range_returns_503_when_database_is_busy(client, monkeypatch):
    client.app.dependency_overrides[get_twstock_client] = FakeTwStockClient

    def raise_locked_error(self, codes, start_date, end_date, user_id=None):
        raise OperationalError("UPDATE daily_prices ...", {}, Exception("database is locked"))

    monkeypatch.setattr(
        "app.api.routes.jobs.MarketDataService.sync_history_range_batch",
        raise_locked_error,
    )

    response = client.post(
        "/api/v1/jobs/sync/history-range",
        json={
            "codes": ["2330"],
            "start_date": "2026-03-24",
            "end_date": "2026-03-26",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Database is busy. Please retry the sync in a few seconds."
