from datetime import date, datetime, timedelta

from app.api.deps import get_twstock_client
from app.db.models.market_data import DailyPrice
from app.db.models.stock import Stock
from app.db.models.strategy import StrategyRun
from app.db.session import get_session_factory
from app.schemas.stock import RealtimeQuoteRead
from app.services.strategy_service import StrategyService
from app.strategies.base import StrategySignal


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


def _seed_strategy_signal_history() -> None:
    session = get_session_factory()()
    try:
        stock_a = Stock(code="2330", name="TSMC", market="TSEC", industry="Semiconductor", is_active=True)
        stock_b = Stock(code="2317", name="Hon Hai", market="TSEC", industry="Electronics", is_active=True)
        session.add_all([stock_a, stock_b])
        session.flush()

        session.add_all(
            [
                StrategyRun(
                    strategy_name="connors_rsi2_long",
                    stock_id=stock_a.id,
                    signal="BUY",
                    signal_reason="older-buy",
                    signal_time=datetime(2025, 8, 26),
                    snapshot_json={"source": "old"},
                ),
                StrategyRun(
                    strategy_name="connors_rsi2_long",
                    stock_id=stock_a.id,
                    signal="SELL",
                    signal_reason="latest-sell",
                    signal_time=datetime(2025, 8, 27),
                    snapshot_json={"source": "latest"},
                ),
                StrategyRun(
                    strategy_name="tw_momentum_breakout_long",
                    stock_id=stock_a.id,
                    signal="HOLD",
                    signal_reason="latest-hold",
                    signal_time=datetime(2025, 8, 28),
                    snapshot_json={"source": "latest"},
                ),
                StrategyRun(
                    strategy_name="connors_rsi2_long",
                    stock_id=stock_b.id,
                    signal="BUY",
                    signal_reason="electronics-buy",
                    signal_time=datetime(2025, 8, 29),
                    snapshot_json={"source": "latest"},
                ),
            ]
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


class HighPriceTwStockClient:
    def get_stock_metadata(self, code: str):
        return {
            "code": code,
            "name": "TSMC",
            "market": "TSEC",
            "industry": "Semiconductor",
            "is_active": True,
        }

    def get_realtime_quote(self, code: str):
        return RealtimeQuoteRead(
            code=code,
            name="TSMC",
            quote_time=date(2026, 3, 30),
            latest_trade_price=800.0,
            reference_price=800.0,
            open_price=800.0,
            high_price=805.0,
            low_price=795.0,
            accumulate_trade_volume=100_000,
            best_bid_price=[799.5],
            best_ask_price=[800.0],
            best_bid_volume=[100],
            best_ask_volume=[100],
        )


def test_run_strategy_cash_percent_can_buy_odd_lot_when_budget_is_below_full_lot(client, monkeypatch):
    _seed_strategy_stock()
    client.app.dependency_overrides[get_twstock_client] = HighPriceTwStockClient
    monkeypatch.setattr(
        StrategyService,
        "evaluate_strategy",
        lambda self, code, strategy_name, prices, position_context=None: StrategySignal(
            strategy_name=strategy_name,
            signal="BUY",
            reason="forced-entry",
            trade_date=date(2026, 3, 30),
            snapshot={},
        ),
    )

    bootstrap_response = client.post(
        "/api/v1/portfolio/bootstrap",
        json={
            "username": "oddlot-runner",
            "email": "oddlot-runner@example.com",
            "initial_cash": 50_000,
            "available_cash": 50_000,
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
            "position_sizing_mode": "cash_percent",
            "cash_allocation_pct": 10,
            "buy_quantity": 1000,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution"]["status"] == "APPLIED"
    assert payload["execution"]["quantity"] == 6


def test_list_portfolio_trades_returns_executed_trade_details(client, monkeypatch):
    _seed_strategy_stock()
    client.app.dependency_overrides[get_twstock_client] = HighPriceTwStockClient
    monkeypatch.setattr(
        StrategyService,
        "evaluate_strategy",
        lambda self, code, strategy_name, prices, position_context=None: StrategySignal(
            strategy_name=strategy_name,
            signal="BUY",
            reason="forced-entry",
            trade_date=date(2026, 3, 30),
            snapshot={},
        ),
    )

    bootstrap_response = client.post(
        "/api/v1/portfolio/bootstrap",
        json={
            "username": "trade-reader",
            "email": "trade-reader@example.com",
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
            "position_sizing_mode": "cash_percent",
            "cash_allocation_pct": 10,
            "buy_quantity": 1000,
        },
    )

    assert response.status_code == 200

    trades_response = client.get(f"/api/v1/portfolio/trades?user_id={user_id}")

    assert trades_response.status_code == 200
    payload = trades_response.json()
    assert len(payload) == 1
    assert payload[0]["stock_code"] == "2330"
    assert payload[0]["side"] == "BUY"
    assert payload[0]["fill_quantity"] > 0


def test_list_signals_can_return_latest_signal_per_stock_strategy(client):
    _seed_strategy_signal_history()

    response = client.get("/api/v1/strategies/signals?latest_only=true")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 3
    assert payload[0]["stock_code"] == "2317"
    assert payload[0]["industry"] == "Electronics"

    connors_tsmc = next(
        item
        for item in payload
        if item["stock_code"] == "2330" and item["strategy_name"] == "connors_rsi2_long"
    )
    assert connors_tsmc["signal"] == "SELL"
    assert connors_tsmc["signal_reason"] == "latest-sell"
    assert connors_tsmc["created_at"] is not None


def test_list_signals_can_filter_latest_signal_by_industry(client):
    _seed_strategy_signal_history()

    response = client.get("/api/v1/strategies/signals?latest_only=true&industry=Semiconductor")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert {item["stock_code"] for item in payload} == {"2330"}
    assert {item["industry"] for item in payload} == {"Semiconductor"}
