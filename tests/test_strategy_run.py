from datetime import date, timedelta

from app.db.models.market_data import DailyPrice
from app.db.models.stock import Stock
from app.db.session import get_session_factory


def _seed_strategy_stock() -> None:
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


def test_run_strategy_can_record_signal_for_workspace_user(client):
    _seed_strategy_stock()

    bootstrap_response = client.post(
        "/api/v1/portfolio/bootstrap",
        json={
            "username": "runner",
            "email": "runner@example.com",
            "initial_cash": 1_000_000,
            "available_cash": 1_000_000,
            "positions": [],
        },
    )

    assert bootstrap_response.status_code == 200
    user_id = bootstrap_response.json()["user_id"]

    response = client.post(
        "/api/v1/strategies/run",
        json={
            "user_id": user_id,
            "code": "2330",
            "strategy_name": "connors_rsi2_long",
            "execute_trade": True,
            "buy_quantity": 1000,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["strategy_name"] == "connors_rsi2_long"
    assert payload["stock_code"] == "2330"
    assert payload["execution"]["status"] == "SKIPPED"
