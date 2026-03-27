from datetime import date, timedelta

from app.db.models.market_data import DailyPrice
from app.db.models.stock import Stock
from app.db.session import get_session_factory


def _seed_backtest_stock() -> None:
    session = get_session_factory()()
    try:
        stock = Stock(code="2330", name="TSMC", market="TSEC", industry="Semiconductor", is_active=True)
        session.add(stock)
        session.flush()

        start_date = date(2025, 1, 1)
        for offset in range(240):
            trade_date = start_date + timedelta(days=offset)
            close_price = 800.0 + (offset * 1.5)
            session.add(
                DailyPrice(
                    stock_id=stock.id,
                    trade_date=trade_date,
                    open_price=close_price - 2,
                    high_price=close_price + 6,
                    low_price=close_price - 6,
                    close_price=close_price,
                    volume=100_000 + (offset * 100),
                    turnover=close_price * (100_000 + (offset * 100)),
                    transaction_count=1_000 + offset,
                )
            )

        session.commit()
    finally:
        session.close()


def test_run_backtest_creates_result(client):
    _seed_backtest_stock()

    response = client.post(
        "/api/v1/backtests/run",
        json={
            "code": "2330",
            "strategy_name": "connors_rsi2_long",
            "start_date": "2025-01-01",
            "end_date": "2025-08-28",
            "initial_cash": 1_000_000,
            "lot_size": 1000,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["stock_code"] == "2330"
    assert payload["strategy_name"] == "connors_rsi2_long"
    assert payload["result"]["initial_cash"] == 1_000_000

    list_response = client.get("/api/v1/backtests?limit=5")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
