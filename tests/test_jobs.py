from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.api.deps import get_twstock_client
from app.db.models.stock import Stock
from app.db.session import get_session_factory
from app.schemas.stock import HistoricalPriceRead
from app.services.market_data_service import MarketDataService
from tests.test_stocks import FakeTwStockClient


class TradingDayOnlyHistoryRangeTwStockClient(FakeTwStockClient):
    history_range_calls = 0

    def get_history_range(self, code: str, start_date: date, end_date: date):
        type(self).history_range_calls += 1
        rows = []
        current = start_date
        close_price = 100.0
        long_holiday = {date(2026, 2, day) for day in range(16, 21)}

        while current <= end_date:
            is_weekend = current.weekday() >= 5
            if not is_weekend and current not in long_holiday:
                rows.append(
                    HistoricalPriceRead(
                        trade_date=current,
                        open_price=close_price - 1,
                        high_price=close_price + 1,
                        low_price=close_price - 2,
                        close_price=close_price,
                        volume=100_000,
                        turnover=close_price * 100_000,
                        transaction_count=1000,
                    )
                )
                close_price += 1
            current += timedelta(days=1)

        return rows


def test_sync_stock_universe_job(client):
    client.app.dependency_overrides[get_twstock_client] = FakeTwStockClient

    response = client.post("/api/v1/jobs/sync/stocks")

    assert response.status_code == 200
    payload = response.json()
    assert payload["synced_count"] == 2

    stocks_response = client.get("/api/v1/stocks?limit=10")
    stocks = stocks_response.json()
    assert len(stocks) == 2


def test_run_workspace_automation_job_route(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.jobs.run_daily_workspace_automation_job",
        lambda: {
            "skipped": False,
            "reason": None,
            "processed_users": 1,
            "applied_users": 1,
            "failed_users": [],
            "execution_details": [
                {
                    "user_id": 1,
                    "code": "2330",
                    "strategy_name": "connors_rsi2_long",
                    "execution": {
                        "applied": True,
                        "action": "BUY",
                        "quantity": 1000,
                        "status": "APPLIED",
                        "message": "Strategy signal applied to portfolio.",
                    },
                }
            ],
        },
    )

    response = client.post("/api/v1/jobs/run/automation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["skipped"] is False
    assert payload["processed_users"] == 1
    assert payload["applied_users"] == 1
    assert payload["failed_users"] == []
    assert payload["execution_details"][0]["code"] == "2330"


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
    assert payload["skipped_codes"] == []
    assert payload["failed_codes"] == []


def test_sync_progress_returns_completed_state_after_history_range_sync(client):
    client.app.dependency_overrides[get_twstock_client] = FakeTwStockClient

    run_id = "sync-progress-range"
    response = client.post(
        "/api/v1/jobs/sync/history-range",
        json={
            "codes": ["2330", "2454"],
            "start_date": "2026-03-24",
            "end_date": "2026-03-26",
            "run_id": run_id,
        },
    )

    assert response.status_code == 200

    progress_response = client.get(f"/api/v1/jobs/sync/progress/{run_id}")
    assert progress_response.status_code == 200
    progress_payload = progress_response.json()
    assert progress_payload["status"] == "completed"
    assert progress_payload["job_name"] == "sync-history-range"
    assert progress_payload["total_codes"] == 2
    assert progress_payload["completed_codes"] == 2
    assert progress_payload["synced_codes"] == 2
    assert progress_payload["synced_rows"] == 6
    assert progress_payload["skipped_codes"] == []
    assert progress_payload["failed_codes"] == []
    assert progress_payload["current_code"] is None
    assert progress_payload["started_at"] is not None
    assert progress_payload["finished_at"] is not None


def test_sync_progress_returns_404_for_unknown_run_id(client):
    response = client.get("/api/v1/jobs/sync/progress/missing-run-id")

    assert response.status_code == 404
    assert response.json()["detail"] == "Sync progress not found."


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
    assert sync_payload["skipped_codes"] == []
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
    assert payload["skipped_codes"] == []
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
    assert payload["skipped_codes"] == []
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
    assert payload["skipped_codes"] == []
    assert payload["failed_codes"] == ["2454"]

    session = get_session_factory()()
    try:
        stock = session.execute(select(Stock).where(Stock.code == "2330")).scalar_one()
        prices = stock.daily_prices
        assert len(prices) == 3
    finally:
        session.close()


def test_sync_history_range_commits_each_code_without_outer_commit(client, monkeypatch):
    client.app.dependency_overrides[get_twstock_client] = FakeTwStockClient
    original_sync_history_range = MarketDataService.sync_history_range

    def flaky_sync_history_range(self, code, start_date, end_date):
        if code == "2454":
            raise RuntimeError("upstream error")
        return original_sync_history_range(self, code, start_date, end_date)

    monkeypatch.setattr(
        "app.services.market_data_service.MarketDataService.sync_history_range",
        flaky_sync_history_range,
    )

    session = get_session_factory()()
    try:
        service = MarketDataService(session, FakeTwStockClient())
        _, synced_codes, synced_rows, skipped_codes, failed_codes = service.sync_history_range_batch(
            codes=["2330", "2454"],
            start_date=date(2026, 3, 24),
            end_date=date(2026, 3, 26),
        )

        assert synced_codes == 1
        assert synced_rows == 3
        assert skipped_codes == []
        assert failed_codes == ["2454"]
    finally:
        session.close()

    verification_session = get_session_factory()()
    try:
        stock = verification_session.execute(select(Stock).where(Stock.code == "2330")).scalar_one()
        prices = stock.daily_prices
        assert len(prices) == 3
    finally:
        verification_session.close()


def test_sync_history_range_skips_codes_already_covered(client):
    client.app.dependency_overrides[get_twstock_client] = FakeTwStockClient
    FakeTwStockClient.history_range_calls = 0

    first_response = client.post(
        "/api/v1/jobs/sync/history-range",
        json={
            "codes": ["2330"],
            "start_date": "2026-03-24",
            "end_date": "2026-03-26",
        },
    )

    assert first_response.status_code == 200
    assert FakeTwStockClient.history_range_calls == 1

    second_response = client.post(
        "/api/v1/jobs/sync/history-range",
        json={
            "codes": ["2330"],
            "start_date": "2026-03-24",
            "end_date": "2026-03-26",
        },
    )

    assert second_response.status_code == 200
    payload = second_response.json()
    assert payload["synced_codes"] == 0
    assert payload["synced_rows"] == 0
    assert payload["skipped_codes"] == ["2330"]
    assert payload["failed_codes"] == []
    assert FakeTwStockClient.history_range_calls == 1


def test_sync_progress_tracks_skipped_codes_after_history_range_sync(client):
    client.app.dependency_overrides[get_twstock_client] = FakeTwStockClient

    seed_response = client.post(
        "/api/v1/jobs/sync/history-range",
        json={
            "codes": ["2330"],
            "start_date": "2026-03-24",
            "end_date": "2026-03-26",
        },
    )
    assert seed_response.status_code == 200

    run_id = "sync-progress-range-skipped"
    response = client.post(
        "/api/v1/jobs/sync/history-range",
        json={
            "codes": ["2330"],
            "start_date": "2026-03-24",
            "end_date": "2026-03-26",
            "run_id": run_id,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["skipped_codes"] == ["2330"]

    progress_response = client.get(f"/api/v1/jobs/sync/progress/{run_id}")
    assert progress_response.status_code == 200
    progress_payload = progress_response.json()
    assert progress_payload["completed_codes"] == 1
    assert progress_payload["synced_codes"] == 0
    assert progress_payload["synced_rows"] == 0
    assert progress_payload["skipped_codes"] == ["2330"]
    assert progress_payload["failed_codes"] == []


def test_sync_history_range_marks_noop_refetch_as_skipped(client, monkeypatch):
    client.app.dependency_overrides[get_twstock_client] = FakeTwStockClient

    first_response = client.post(
        "/api/v1/jobs/sync/history-range",
        json={
            "codes": ["2330"],
            "start_date": "2026-03-24",
            "end_date": "2026-03-26",
        },
    )
    assert first_response.status_code == 200

    monkeypatch.setattr(
        "app.services.market_data_service.MarketDataService._has_complete_trading_day_coverage",
        lambda self, stock_id, start_date, end_date: False,
    )

    second_response = client.post(
        "/api/v1/jobs/sync/history-range",
        json={
            "codes": ["2330"],
            "start_date": "2026-03-24",
            "end_date": "2026-03-26",
        },
    )

    assert second_response.status_code == 200
    payload = second_response.json()
    assert payload["synced_codes"] == 0
    assert payload["synced_rows"] == 0
    assert payload["skipped_codes"] == ["2330"]
    assert payload["failed_codes"] == []


def test_sync_history_range_returns_503_when_database_is_busy(client, monkeypatch):
    client.app.dependency_overrides[get_twstock_client] = FakeTwStockClient

    def raise_locked_error(self, codes, start_date, end_date, user_id=None, progress_run_id=None):
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


def test_sync_history_range_treats_same_day_end_date_as_already_covered_before_daily_close(client, monkeypatch):
    client.app.dependency_overrides[get_twstock_client] = FakeTwStockClient

    first_response = client.post(
        "/api/v1/jobs/sync/history-range",
        json={
            "codes": ["2330"],
            "start_date": "2026-03-24",
            "end_date": "2026-03-30",
        },
    )
    assert first_response.status_code == 200

    class FakeDateTime:
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 3, 31, 12, 0, 0, tzinfo=tz)

    monkeypatch.setattr("app.services.market_data_service.datetime", FakeDateTime)
    monkeypatch.setattr(
        "app.services.trading_calendar_service.TradingCalendarService._get_holiday_dates",
        lambda self, year: set(),
    )

    session = get_session_factory()()
    try:
        service = MarketDataService(session, FakeTwStockClient())
        _, synced_codes, synced_rows, skipped_codes, failed_codes = service.sync_history_range_batch(
            codes=["2330"],
            start_date=date(2026, 3, 24),
            end_date=date(2026, 3, 31),
        )

        assert synced_codes == 0
        assert synced_rows == 0
        assert skipped_codes == ["2330"]
        assert failed_codes == []
    finally:
        session.close()


def test_sync_history_range_skips_existing_data_across_long_market_holiday(client, monkeypatch):
    client.app.dependency_overrides[get_twstock_client] = TradingDayOnlyHistoryRangeTwStockClient
    TradingDayOnlyHistoryRangeTwStockClient.history_range_calls = 0

    long_holiday = {date(2026, 2, day) for day in range(16, 21)}
    monkeypatch.setattr(
        "app.services.trading_calendar_service.TradingCalendarService._get_holiday_dates",
        lambda self, year: long_holiday if year == 2026 else set(),
    )

    payload = {
        "codes": ["2330"],
        "start_date": "2025-10-01",
        "end_date": "2026-03-31",
    }

    first_response = client.post("/api/v1/jobs/sync/history-range", json=payload)

    assert first_response.status_code == 200
    assert TradingDayOnlyHistoryRangeTwStockClient.history_range_calls == 1

    second_response = client.post("/api/v1/jobs/sync/history-range", json=payload)

    assert second_response.status_code == 200
    second_payload = second_response.json()
    assert second_payload["synced_codes"] == 0
    assert second_payload["synced_rows"] == 0
    assert second_payload["skipped_codes"] == ["2330"]
    assert second_payload["failed_codes"] == []
    assert TradingDayOnlyHistoryRangeTwStockClient.history_range_calls == 1
