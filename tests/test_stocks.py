from datetime import date, datetime, timedelta

from app.api.deps import get_twstock_client
from app.schemas.stock import HistoricalPriceRead, RealtimeQuoteRead


class FakeTwStockClient:
    history_range_calls = 0

    def list_stock_universe(self):
        return [
            {
                "code": "2330",
                "name": "TSMC",
                "market": "TSEC",
                "industry": "\u534a\u5c0e\u9ad4\u696d",
                "is_active": True,
            },
            {
                "code": "2317",
                "name": "HonHai",
                "market": "TSEC",
                "industry": "\u96fb\u8166\u53ca\u9031\u908a\u8a2d\u5099\u696d",
                "is_active": True,
            },
        ]

    def get_stock_metadata(self, code: str):
        if code == "2317":
            return {
                "code": code,
                "name": "HonHai",
                "market": "TSEC",
                "industry": "\u96fb\u8166\u53ca\u9031\u908a\u8a2d\u5099\u696d",
                "is_active": True,
            }

        return {
            "code": code,
            "name": "TSMC",
            "market": "TSEC",
            "industry": "\u534a\u5c0e\u9ad4\u696d",
            "is_active": True,
        }

    def get_history(self, code: str, year: int, month: int):
        return [
            HistoricalPriceRead(
                trade_date=date(year, month, 2),
                open_price=100.0,
                high_price=110.0,
                low_price=99.0,
                close_price=108.0,
                volume=100_000,
                turnover=10_800_000.0,
                transaction_count=1234,
            )
        ]

    def get_history_range(self, code: str, start_date: date, end_date: date):
        type(self).history_range_calls += 1
        current = start_date
        rows = []
        close_price = 100.0
        while current <= end_date:
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
            current += timedelta(days=1)
            close_price += 1
        return rows

    def get_realtime_quote(self, code: str, force_refresh: bool = False):
        return RealtimeQuoteRead(
            code=code,
            name="TSMC" if code == "2330" else "HonHai",
            quote_time=datetime(2026, 3, 27, 9, 0, 0),
            latest_trade_price=108.0,
            latest_trade_price_available=True,
            reference_price=108.0,
            open_price=100.0,
            high_price=110.0,
            low_price=99.0,
            accumulate_trade_volume=100_000,
            best_bid_price=[107.5, 107.0],
            best_ask_price=[108.0, 108.5],
            best_bid_volume=[100, 200],
            best_ask_volume=[150, 250],
        )


class MissingLatestTradePriceTwStockClient(FakeTwStockClient):
    def get_realtime_quote(self, code: str, force_refresh: bool = False):
        return RealtimeQuoteRead(
            code=code,
            name="TSMC" if code == "2330" else "HonHai",
            quote_time=datetime(2026, 3, 30, 10, 26, 45),
            latest_trade_price=None,
            latest_trade_price_available=False,
            warning_message=f"Realtime latest trade price is unavailable for {code} after snapshot 2026-03-30 10:26:45 (attempt 4/4).",
            reference_price=1787.5,
            open_price=1780.0,
            high_price=1790.0,
            low_price=1780.0,
            accumulate_trade_volume=16680,
            best_bid_price=[1780.0],
            best_ask_price=[1790.0],
            best_bid_volume=[4875],
            best_ask_volume=[1047],
        )


def test_list_stocks_default_empty(client):
    response = client.get("/api/v1/stocks")

    assert response.status_code == 200
    assert response.json() == []


def test_sync_stock_history_persists_records(client):
    client.app.dependency_overrides[get_twstock_client] = FakeTwStockClient

    response = client.post("/api/v1/stocks/2330/sync?year=2026&month=3")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == "2330"
    assert payload["synced_count"] == 1

    stock_list_response = client.get("/api/v1/stocks")
    stocks = stock_list_response.json()
    assert len(stocks) == 1
    assert stocks[0]["name"] == "TSMC"


def test_get_realtime_quote(client):
    client.app.dependency_overrides[get_twstock_client] = FakeTwStockClient

    response = client.get("/api/v1/stocks/2330/quote")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == "2330"
    assert payload["latest_trade_price"] == 108.0


def test_get_realtime_quote_returns_snapshot_without_502_when_latest_trade_price_is_missing(client):
    client.app.dependency_overrides[get_twstock_client] = MissingLatestTradePriceTwStockClient

    response = client.get("/api/v1/stocks/2330/quote")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == "2330"
    assert payload["latest_trade_price"] is None
    assert payload["latest_trade_price_available"] is False
    assert "Realtime latest trade price is unavailable" in payload["warning_message"]


def test_get_history_range_from_database(client):
    client.app.dependency_overrides[get_twstock_client] = FakeTwStockClient
    sync_response = client.post("/api/v1/stocks/2330/sync?year=2026&month=3")
    assert sync_response.status_code == 200

    response = client.get("/api/v1/stocks/2330/history-range?start_date=2026-03-01&end_date=2026-03-31")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == "2330"
    assert payload["prices"][0]["trade_date"] == "2026-03-01"
    assert payload["prices"][-1]["trade_date"] == "2026-03-31"
    assert len(payload["prices"]) == 31


def test_get_history_range_uses_cached_prices_for_weekend_boundary(client):
    client.app.dependency_overrides[get_twstock_client] = FakeTwStockClient
    FakeTwStockClient.history_range_calls = 0

    prime_response = client.get("/api/v1/stocks/0050/history-range?start_date=2026-03-02&end_date=2026-03-27")
    assert prime_response.status_code == 200
    assert FakeTwStockClient.history_range_calls == 1

    response = client.get("/api/v1/stocks/0050/history-range?start_date=2026-03-02&end_date=2026-03-28")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == "0050"
    assert payload["prices"][0]["trade_date"] == "2026-03-02"
    assert payload["prices"][-1]["trade_date"] == "2026-03-27"
    assert FakeTwStockClient.history_range_calls == 1
