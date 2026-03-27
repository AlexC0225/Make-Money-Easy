from datetime import date

from app.api.deps import get_twstock_client
from app.schemas.stock import HistoricalPriceRead
from app.services.twstock_client import TwStockClient


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


class DummyResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "longName": "Taiwan Semiconductor Manufacturing Company Limited",
                            "regularMarketPrice": 1820.0,
                            "previousClose": 1840.0,
                            "regularMarketDayHigh": 1845.0,
                            "regularMarketDayLow": 1815.0,
                            "regularMarketVolume": 32000000,
                            "regularMarketTime": 1774589407,
                        },
                        "indicators": {
                            "quote": [
                                {
                                    "open": [1835.0, 1830.0],
                                    "high": [1840.0, 1845.0],
                                    "low": [1820.0, 1815.0],
                                    "close": [1830.0, 1820.0],
                                    "volume": [1000, 2000],
                                }
                            ]
                        },
                    }
                ],
                "error": None,
            }
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


def test_get_realtime_quote_falls_back_to_yahoo(monkeypatch):
    client = TwStockClient()
    with client._quote_cache_lock:
        client._quote_cache.clear()
    with client._realtime_lock:
        client._realtime_request_times.clear()

    def raise_disconnect(_: str):
        raise RuntimeError("remote disconnected")

    monkeypatch.setattr("app.services.twstock_client.twstock.realtime.get", raise_disconnect)
    monkeypatch.setattr("app.services.twstock_client.requests.get", lambda *args, **kwargs: DummyResponse())

    quote = client.get_realtime_quote("2330")

    assert quote.code == "2330"
    assert quote.latest_trade_price == 1820.0
    assert quote.reference_price == 1840.0
    assert quote.open_price == 1835.0
    assert quote.high_price == 1845.0
    assert quote.low_price == 1815.0
    assert quote.accumulate_trade_volume == 32000000
