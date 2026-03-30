from datetime import date

import pytest

from app.api.deps import get_twstock_client
from app.schemas.stock import HistoricalPriceRead
from app.services.twstock_client import TwStockClient, TwStockClientError


class FakeTwStockClient:
    def get_stock_metadata(self, code: str):
        return {
            "code": code,
            "name": "TSMC",
            "market": "TSEC",
            "industry": "Semiconductor",
            "is_active": True,
        }

    def get_history_range(self, code: str, start_date: date, end_date: date):
        return [
            HistoricalPriceRead(
                trade_date=start_date,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=108.0,
                volume=100_000,
                turnover=10_800_000.0,
                transaction_count=1234,
            )
        ]


class DummyTpexHistoryResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "tables": [
                {
                    "data": [
                        ["115/03/02", "76,330", "1,154,792", "15.16", "15.16", "15.11", "15.14", "0.01", "7,873"],
                        ["115/03/03", "58,086", "878,382", "15.11", "15.14", "15.11", "15.12", "-0.02", "6,651"],
                    ]
                }
            ]
        }


def test_get_history_range_fetches_upstream_when_database_empty(client):
    client.app.dependency_overrides[get_twstock_client] = FakeTwStockClient

    response = client.get("/api/v1/stocks/2330/history-range?start_date=2026-03-01&end_date=2026-03-31")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == "2330"
    assert payload["prices"][0]["trade_date"] == "2026-03-01"


def test_get_user_returns_404_when_account_missing(client):
    response = client.get("/api/v1/users/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "找不到對應的帳戶"


def test_get_realtime_quote_raises_when_upstream_request_fails(monkeypatch):
    client = TwStockClient()
    with client._quote_cache_lock:
        client._quote_cache.clear()
        client._last_priced_quote_cache.clear()
    with client._realtime_lock:
        client._realtime_request_times.clear()

    def raise_disconnect(_: str):
        raise RuntimeError("remote disconnected")

    monkeypatch.setattr("app.services.twstock_client.twstock.realtime.get", raise_disconnect)
    with pytest.raises(TwStockClientError, match="Failed to fetch realtime quote for 2330"):
        client.get_realtime_quote("2330")


def test_get_realtime_quote_raises_when_latest_trade_price_is_missing(monkeypatch):
    client = TwStockClient()
    with client._quote_cache_lock:
        client._quote_cache.clear()
        client._last_priced_quote_cache.clear()
    with client._realtime_lock:
        client._realtime_request_times.clear()
    monkeypatch.setattr(client, "_acquire_twse_slot", lambda: None)
    monkeypatch.setattr("app.services.twstock_client.sleep", lambda _: None)

    monkeypatch.setattr(
        "app.services.twstock_client.twstock.realtime.get",
        lambda _: {
            "success": True,
            "info": {"name": "TSMC", "time": "2026-03-30 09:30:00"},
            "realtime": {
                "latest_trade_price": "-",
                "best_bid_price": ["950"],
                "best_ask_price": ["951"],
                "open": "945",
                "high": "960",
                "low": "940",
            },
        },
    )

    quote = client.get_realtime_quote("2330")

    assert quote.code == "2330"
    assert quote.latest_trade_price is None
    assert quote.latest_trade_price_available is False
    assert quote.latest_trade_price_source == "unavailable"
    assert quote.warning_message is not None
    assert quote.best_bid_price == [950.0]
    assert quote.best_ask_price == [951.0]


def test_get_realtime_quote_retries_until_latest_trade_price_is_available(monkeypatch):
    client = TwStockClient()
    with client._quote_cache_lock:
        client._quote_cache.clear()
        client._last_priced_quote_cache.clear()
    with client._realtime_lock:
        client._realtime_request_times.clear()
    monkeypatch.setattr(client, "_acquire_twse_slot", lambda: None)
    monkeypatch.setattr("app.services.twstock_client.sleep", lambda _: None)

    responses = iter(
        [
            {
                "success": True,
                "info": {"name": "HonHai", "time": "2026-03-30 10:10:10"},
                "realtime": {
                    "latest_trade_price": "-",
                    "best_bid_price": ["194.0"],
                    "best_ask_price": ["194.5"],
                    "accumulate_trade_volume": "15268",
                    "open": "194.5",
                    "high": "195.5",
                    "low": "194.0",
                },
            },
            {
                "success": True,
                "info": {"name": "HonHai", "time": "2026-03-30 10:10:12"},
                "realtime": {
                    "latest_trade_price": "194.0",
                    "trade_volume": "6",
                    "best_bid_price": ["194.0"],
                    "best_ask_price": ["194.5"],
                    "accumulate_trade_volume": "15286",
                    "open": "194.5",
                    "high": "195.5",
                    "low": "194.0",
                },
            },
        ]
    )

    monkeypatch.setattr("app.services.twstock_client.twstock.realtime.get", lambda _: next(responses))

    quote = client.get_realtime_quote("2317")

    assert quote.code == "2317"
    assert quote.latest_trade_price == 194.0
    assert quote.accumulate_trade_volume == 15286
    assert quote.latest_trade_price_source == "realtime"


def test_get_realtime_quote_force_refresh_bypasses_snapshot_cache(monkeypatch):
    client = TwStockClient()
    with client._quote_cache_lock:
        client._quote_cache.clear()
        client._last_priced_quote_cache.clear()
    with client._realtime_lock:
        client._realtime_request_times.clear()
    monkeypatch.setattr(client, "_acquire_twse_slot", lambda: None)
    monkeypatch.setattr("app.services.twstock_client.sleep", lambda _: None)

    responses = iter(
        [
            {
                "success": True,
                "info": {"name": "TSMC", "time": "2026-03-30 10:20:00"},
                "realtime": {
                    "latest_trade_price": "1000",
                    "best_bid_price": ["999"],
                    "best_ask_price": ["1000"],
                },
            },
            {
                "success": True,
                "info": {"name": "TSMC", "time": "2026-03-30 10:20:03"},
                "realtime": {
                    "latest_trade_price": "1005",
                    "best_bid_price": ["1004"],
                    "best_ask_price": ["1005"],
                },
            },
        ]
    )

    monkeypatch.setattr("app.services.twstock_client.twstock.realtime.get", lambda _: next(responses))

    first_quote = client.get_realtime_quote("2330")
    second_quote = client.get_realtime_quote("2330", force_refresh=True)

    assert first_quote.latest_trade_price == 1000.0
    assert second_quote.latest_trade_price == 1005.0
    assert second_quote.latest_trade_price_source == "realtime"


def test_get_realtime_quote_uses_cached_latest_trade_price_when_current_snapshot_is_missing(monkeypatch):
    client = TwStockClient()
    with client._quote_cache_lock:
        client._quote_cache.clear()
        client._last_priced_quote_cache.clear()
    with client._realtime_lock:
        client._realtime_request_times.clear()
    monkeypatch.setattr(client, "_acquire_twse_slot", lambda: None)
    monkeypatch.setattr("app.services.twstock_client.sleep", lambda _: None)

    first_payload = {
        "success": True,
        "info": {"name": "TSMC", "time": "2026-03-30 10:30:00"},
        "realtime": {
            "latest_trade_price": "1785",
            "best_bid_price": ["1785"],
            "best_ask_price": ["1790"],
            "accumulate_trade_volume": "14000",
            "open": "1780",
            "high": "1790",
            "low": "1780",
        },
    }
    second_payload = {
        "success": True,
        "info": {"name": "TSMC", "time": "2026-03-30 10:30:05"},
        "realtime": {
            "latest_trade_price": "-",
            "best_bid_price": ["1780"],
            "best_ask_price": ["1790"],
            "accumulate_trade_volume": "14020",
            "open": "1780",
            "high": "1790",
            "low": "1780",
        },
    }

    monkeypatch.setattr("app.services.twstock_client.twstock.realtime.get", lambda _: first_payload)
    first_quote = client.get_realtime_quote("2330")
    assert first_quote.latest_trade_price == 1785.0

    with client._quote_cache_lock:
        client._quote_cache.clear()

    monkeypatch.setattr("app.services.twstock_client.twstock.realtime.get", lambda _: second_payload)
    second_quote = client.get_realtime_quote("2330")

    assert second_quote.latest_trade_price == 1785.0
    assert second_quote.latest_trade_price_available is True
    assert second_quote.latest_trade_price_source == "cache"
    assert second_quote.warning_message is not None


def test_get_history_range_uses_tpex_parser_for_bond_etf(monkeypatch):
    client = TwStockClient()

    monkeypatch.setattr("app.services.twstock_client.requests.get", lambda *args, **kwargs: DummyTpexHistoryResponse())
    monkeypatch.setattr(client, "_acquire_twse_slot", lambda: None)

    prices = client.get_history_range("00937B", date(2026, 3, 1), date(2026, 3, 31))

    assert len(prices) == 2
    assert prices[0].trade_date == date(2026, 3, 2)
    assert prices[0].close_price == 15.14
    assert prices[0].volume == 76_330_000
    assert prices[0].turnover == 1_154_792_000.0
    assert prices[0].transaction_count == 7_873
