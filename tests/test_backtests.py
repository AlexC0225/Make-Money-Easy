from datetime import date, timedelta

from app.db.models.market_data import DailyPrice
from app.db.models.stock import Stock
from app.db.session import get_session_factory
from app.services.backtest_service import BacktestService, BacktestSpec
from app.services.market_data_service import MarketDataService
from app.services.strategy_service import StrategyService
from app.strategies.base import StrategySignal


def _seed_backtest_stocks(codes: list[str]) -> None:
    session = get_session_factory()()
    try:
        start_date = date(2025, 1, 1)
        default_industry = MarketDataService.DEFAULT_SYNC_POOL_INDUSTRIES[0]

        for stock_index, code in enumerate(codes):
            stock = Stock(
                code=code,
                name=f"Stock {code}",
                market="TSEC",
                industry=default_industry,
                is_active=True,
            )
            session.add(stock)
            session.flush()

            for offset in range(240):
                trade_date = start_date + timedelta(days=offset)
                close_price = 800.0 + (offset * (1.2 + (stock_index * 0.1)))
                volume = 150_000 + (offset * 100)
                session.add(
                    DailyPrice(
                        stock_id=stock.id,
                        trade_date=trade_date,
                        open_price=close_price - 2,
                        high_price=close_price + 6,
                        low_price=close_price - 6,
                        close_price=close_price,
                        volume=volume,
                        turnover=close_price * volume,
                        transaction_count=1_000 + offset,
                    )
                )

        session.commit()
    finally:
        session.close()


def test_run_backtest_creates_single_stock_result(client):
    _seed_backtest_stocks(["2330"])

    response = client.post(
        "/api/v1/backtests/run",
        json={
            "code": "2330",
            "strategy_name": "connors_rsi2_long",
            "start_date": "2025-01-01",
            "end_date": "2025-08-28",
            "initial_cash": 1_000_000,
            "position_sizing_mode": "cash_percent",
            "lot_size": 1000,
            "cash_allocation_pct": 25,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["stock_code"] == "2330"
    assert payload["is_portfolio"] is False
    assert payload["portfolio_codes"] == []
    assert payload["strategy_name"] == "connors_rsi2_long"
    assert payload["result"]["initial_cash"] == 1_000_000
    assert payload["result"]["position_sizing_mode"] == "cash_percent"
    assert payload["result"]["cash_allocation_pct"] == 25
    assert payload["result"]["max_open_positions"] == 20

    list_response = client.get("/api/v1/backtests?limit=5")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


def test_run_backtest_uses_warmup_history_before_selected_start_date(client):
    _seed_backtest_stocks(["2330"])

    response = client.post(
        "/api/v1/backtests/run",
        json={
            "code": "2330",
            "strategy_name": "connors_rsi2_long",
            "start_date": "2025-07-20",
            "end_date": "2025-08-28",
            "initial_cash": 1_000_000,
            "position_sizing_mode": "cash_percent",
            "lot_size": 1000,
            "cash_allocation_pct": 25,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["stock_code"] == "2330"
    assert payload["result"]["equity_curve"][0]["date"] == "2025-07-20"


def test_run_backtest_creates_portfolio_result(client):
    _seed_backtest_stocks(["2330", "2317"])

    response = client.post(
        "/api/v1/backtests/run",
        json={
            "code": "2330, 2317",
            "strategy_name": "connors_rsi2_long",
            "start_date": "2025-01-01",
            "end_date": "2025-08-28",
            "initial_cash": 1_000_000,
            "position_sizing_mode": "cash_percent",
            "lot_size": 1000,
            "cash_allocation_pct": 20,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["stock_code"] == "PORTFOLIO"
    assert payload["is_portfolio"] is True
    assert payload["portfolio_codes"] == ["2330", "2317"]
    assert payload["result"]["portfolio_codes"] == ["2330", "2317"]
    assert payload["result"]["is_portfolio"] is True
    assert payload["result"]["max_open_positions"] == 20
    assert "equity_curve" in payload["result"]
    assert payload["result"]["open_positions"] == []


def test_run_backtest_uses_default_list_when_code_is_blank(client):
    _seed_backtest_stocks(["2330", "2317"])

    response = client.post(
        "/api/v1/backtests/run",
        json={
            "code": "",
            "strategy_name": "connors_rsi2_long",
            "start_date": "2025-01-01",
            "end_date": "2025-08-28",
            "initial_cash": 1_000_000,
            "position_sizing_mode": "cash_percent",
            "lot_size": 1000,
            "cash_allocation_pct": 20,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["is_portfolio"] is True
    assert sorted(payload["portfolio_codes"]) == ["2317", "2330"]


def test_run_backtest_respects_custom_max_open_positions(client, monkeypatch):
    _seed_backtest_stocks(["2330", "2317"])
    monkeypatch.setattr(
        StrategyService,
        "evaluate_strategy",
        lambda self, code, strategy_name, prices, position_context=None: StrategySignal(
            strategy_name=strategy_name,
            signal="BUY",
            reason="forced-entry",
            trade_date=prices[-1].trade_date,
            snapshot={},
        ),
    )

    response = client.post(
        "/api/v1/backtests/run",
        json={
            "code": "2330, 2317",
            "strategy_name": "connors_rsi2_long",
            "start_date": "2025-01-01",
            "end_date": "2025-08-28",
            "initial_cash": 1_000_000,
            "position_sizing_mode": "cash_percent",
            "lot_size": 1000,
            "cash_allocation_pct": 20,
            "max_open_positions": 1,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["result"]["max_open_positions"] == 1
    assert payload["result"]["trade_count"] == 1
    assert payload["result"]["open_position_count"] == 1


def test_run_backtest_persists_after_concurrent_write(client, monkeypatch):
    _seed_backtest_stocks(["2330"])

    original_runner = BacktestService._run_same_close_backtest

    def run_with_concurrent_commit(self, payload, stock, prices):
        writer_session = get_session_factory()()
        try:
            writer_session.add(
                Stock(
                    code="9999",
                    name="Concurrent Writer",
                    market="TSEC",
                    industry="TEST",
                    is_active=False,
                )
            )
            writer_session.commit()
        finally:
            writer_session.close()

        return original_runner(self, payload, stock, prices)

    monkeypatch.setattr(BacktestService, "_run_same_close_backtest", run_with_concurrent_commit)

    session = get_session_factory()()
    try:
        service = BacktestService(session)
        result = service.run_backtest(
            BacktestSpec(
                codes=["2330"],
                strategy_name="connors_rsi2_long",
                start_date=date(2025, 1, 1),
                end_date=date(2025, 8, 28),
                initial_cash=1_000_000,
                position_sizing_mode="cash_percent",
                lot_size=1000,
                cash_allocation_pct=25,
                max_open_positions=20,
            )
        )
        session.commit()
    finally:
        session.close()

    assert result.stock_code == "2330"
    assert result.id > 0


def test_run_backtest_handles_strategy_history_boundary_without_server_error(client):
    _seed_backtest_stocks(["2330"])

    response = client.post(
        "/api/v1/backtests/run",
        json={
            "code": "2330",
            "strategy_name": "tw_daily_open_momentum_long",
            "start_date": "2025-04-30",
            "end_date": "2025-08-28",
            "initial_cash": 1_000_000,
            "position_sizing_mode": "cash_percent",
            "lot_size": 1000,
            "cash_allocation_pct": 25,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["stock_code"] == "2330"
    assert payload["result"]["equity_curve"][0]["date"] == "2025-05-01"
