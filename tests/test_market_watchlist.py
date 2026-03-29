from datetime import date

from app.api.deps import get_twstock_client
from app.db.models.market_data import DailyPrice
from app.db.models.stock import Stock
from app.db.session import get_session_factory
from tests.test_stocks import FakeTwStockClient


def _seed_market_snapshot() -> None:
    session = get_session_factory()()
    try:
        data = [
            ("2330", "TSMC", 100.0, 110.0, 500_000),
            ("2317", "HonHai", 100.0, 95.0, 800_000),
            ("0050", "TW50 ETF", 100.0, 103.0, 1_200_000),
        ]
        for code, name, previous_close, latest_close, volume in data:
            stock = Stock(code=code, name=name, market="TSEC", industry="Test", is_active=True)
            session.add(stock)
            session.flush()
            session.add(
                DailyPrice(
                    stock_id=stock.id,
                    trade_date=date(2026, 3, 26),
                    open_price=previous_close,
                    high_price=previous_close + 1,
                    low_price=previous_close - 1,
                    close_price=previous_close,
                    volume=volume - 100_000,
                    turnover=previous_close * (volume - 100_000),
                    transaction_count=1000,
                )
            )
            session.add(
                DailyPrice(
                    stock_id=stock.id,
                    trade_date=date(2026, 3, 27),
                    open_price=latest_close,
                    high_price=latest_close + 1,
                    low_price=latest_close - 1,
                    close_price=latest_close,
                    volume=volume,
                    turnover=latest_close * volume,
                    transaction_count=1200,
                )
            )
        session.commit()
    finally:
        session.close()


def test_market_overview_lists_rankings(client):
    _seed_market_snapshot()

    response = client.get("/api/v1/market/overview?limit=2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["as_of_date"] == "2026-03-27"
    assert payload["top_gainers"][0]["code"] == "2330"
    assert payload["top_losers"][0]["code"] == "2317"
    assert payload["top_volume"][0]["code"] == "0050"


def test_watchlist_crud(client):
    client.app.dependency_overrides[get_twstock_client] = FakeTwStockClient

    bootstrap_response = client.post(
        "/api/v1/portfolio/bootstrap",
        json={
            "username": "watch-user",
            "email": "watch@example.com",
            "initial_cash": 1_000_000,
            "available_cash": 1_000_000,
            "positions": [],
        },
    )
    assert bootstrap_response.status_code == 200
    user_id = bootstrap_response.json()["user_id"]

    create_response = client.post(
        "/api/v1/watchlist",
        json={"user_id": user_id, "code": "2330", "note": "core"},
    )
    assert create_response.status_code == 201
    payload = create_response.json()
    assert payload["code"] == "2330"
    assert payload["industry"] == "\u534a\u5c0e\u9ad4\u696d"

    list_response = client.get(f"/api/v1/watchlist?user_id={user_id}")
    assert list_response.status_code == 200
    items = list_response.json()
    assert len(items) == 1
    assert items[0]["note"] == "core"
    assert items[0]["industry"] == "\u534a\u5c0e\u9ad4\u696d"

    delete_response = client.delete(f"/api/v1/watchlist/2330?user_id={user_id}")
    assert delete_response.status_code == 204

    empty_response = client.get(f"/api/v1/watchlist?user_id={user_id}")
    assert empty_response.status_code == 200
    assert empty_response.json() == []
