from datetime import date

from app.db.models.market_data import DailyPrice
from app.db.models.stock import Stock
from app.db.session import get_session_factory


def _seed_lookup_stock() -> None:
    session = get_session_factory()()
    try:
        stock = Stock(code="2330", name="TSMC", market="TSEC", industry="Semiconductor", is_active=True)
        session.add(stock)
        session.flush()
        session.add(
            DailyPrice(
                stock_id=stock.id,
                trade_date=date(2026, 3, 27),
                open_price=980.0,
                high_price=995.0,
                low_price=978.0,
                close_price=990.0,
                volume=100000,
                turnover=99000000.0,
                transaction_count=1000,
            )
        )
        session.commit()
    finally:
        session.close()


def test_search_stocks_returns_matches_and_latest_price(client):
    _seed_lookup_stock()

    response = client.get("/api/v1/stocks/search?q=23")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["code"] == "2330"
    assert payload[0]["latest_price"] == 990.0


def test_strategy_catalog_lists_available_strategies(client):
    catalog_response = client.get("/api/v1/strategies/catalog")

    assert catalog_response.status_code == 200
    catalog = catalog_response.json()
    strategy_names = {item["name"] for item in catalog}
    assert "hybrid_tw_strategy" in strategy_names
    assert "connors_rsi2_long" in strategy_names
    assert "tw_momentum_breakout_long" in strategy_names
