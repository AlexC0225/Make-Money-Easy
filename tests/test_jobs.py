from app.api.deps import get_etf_constituent_service, get_twstock_client
from app.services.etf_constituent_service import EtfConstituentSnapshot
from tests.test_stocks import FakeTwStockClient


class FakeEtfConstituentService:
    def get_0050_constituents(self) -> EtfConstituentSnapshot:
        return EtfConstituentSnapshot(
            etf_code="0050",
            codes=["2330", "2317", "2454"],
            source_url="https://www.yuantaetfs.com/tradeInfo/pcf/0050",
            announce_date="2026-03-27",
            trade_date="2026-03-26",
        )


def test_sync_stock_universe_job(client):
    client.app.dependency_overrides[get_twstock_client] = FakeTwStockClient
    client.app.dependency_overrides[get_etf_constituent_service] = FakeEtfConstituentService

    response = client.post("/api/v1/jobs/sync/stocks")

    assert response.status_code == 200
    payload = response.json()
    assert payload["synced_count"] == 2

    stocks_response = client.get("/api/v1/stocks?limit=10")
    stocks = stocks_response.json()
    assert len(stocks) == 2


def test_sync_history_batch_job(client):
    client.app.dependency_overrides[get_twstock_client] = FakeTwStockClient
    client.app.dependency_overrides[get_etf_constituent_service] = FakeEtfConstituentService

    response = client.post(
        "/api/v1/jobs/sync/history",
        json={"codes": ["2330", "2317"], "year": 2026, "month": 3},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["synced_codes"] == 2
    assert payload["synced_rows"] == 2
    assert payload["failed_codes"] == []


def test_sync_targets_default_to_watchlist_plus_0050(client):
    client.app.dependency_overrides[get_twstock_client] = FakeTwStockClient
    client.app.dependency_overrides[get_etf_constituent_service] = FakeEtfConstituentService

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
    assert preview_payload["benchmark_codes"] == ["2330", "2317", "2454"]
    assert preview_payload["codes"] == ["2317", "2330", "2454"]
    assert preview_payload["announce_date"] == "2026-03-27"
    assert preview_payload["trade_date"] == "2026-03-26"

    sync_response = client.post(
        "/api/v1/jobs/sync/history",
        json={"user_id": user_id, "year": 2026, "month": 3},
    )

    assert sync_response.status_code == 200
    sync_payload = sync_response.json()
    assert sync_payload["selection_mode"] == "default"
    assert sync_payload["codes"] == ["2317", "2330", "2454"]
    assert sync_payload["synced_codes"] == 3
    assert sync_payload["failed_codes"] == []
