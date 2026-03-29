from datetime import date, timedelta

from app.db.models.market_data import DailyPrice
from app.db.models.stock import Stock
from app.db.session import get_session_factory
from app.strategies.tw_momentum_breakout_strategy import TaiwanMomentumBreakoutLongStrategy


def _build_momentum_prices() -> list[DailyPrice]:
    prices: list[DailyPrice] = []
    start_date = date(2025, 1, 1)

    for offset in range(150):
        trade_date = start_date + timedelta(days=offset)
        if offset < 120:
            close_price = 50.0 + (offset * 0.4)
            volume = 200_000
        elif offset == 120:
            close_price = 100.0
            volume = 450_000
        else:
            close_price = 100.5 + ((offset - 121) * 0.25)
            volume = 230_000

        prices.append(
            DailyPrice(
                trade_date=trade_date,
                open_price=close_price - 0.5,
                high_price=close_price + 1.5,
                low_price=close_price - 1.5,
                close_price=close_price,
                volume=volume,
                turnover=close_price * volume,
                transaction_count=5_000 + offset,
            )
        )

    return prices


def _seed_momentum_stock() -> tuple[list[DailyPrice], str]:
    session = get_session_factory()()
    try:
        stock = Stock(code="2454", name="MomentumTest", market="TSEC", industry="Electronics", is_active=True)
        session.add(stock)
        session.flush()

        prices = _build_momentum_prices()
        for item in prices:
            item.stock_id = stock.id
            session.add(item)

        session.commit()
        return prices, stock.code
    finally:
        session.close()


def test_momentum_breakout_generates_buy_signal():
    strategy = TaiwanMomentumBreakoutLongStrategy()
    prices = _build_momentum_prices()

    signal = strategy.evaluate(prices[:121])

    assert signal.strategy_name == "tw_momentum_breakout_long"
    assert signal.signal == "BUY"
    assert signal.reason == "trend_breakout_volume_rsi_confirmed"
    assert signal.snapshot["relative_volume"] > 1.5
    assert signal.snapshot["rsi14"] > 55


def test_momentum_breakout_exits_on_max_holding_period():
    strategy = TaiwanMomentumBreakoutLongStrategy()
    prices = _build_momentum_prices()
    entry_bar = prices[121]

    signal = strategy.evaluate(
        prices[:142],
        position_context={
            "quantity": 1000,
            "entry_price": float(entry_bar.open_price),
            "entry_date": entry_bar.trade_date,
        },
    )

    assert signal.signal == "SELL"
    assert signal.reason == "max_hold_20_days"


def test_momentum_breakout_backtest_executes_on_next_open(client):
    prices, code = _seed_momentum_stock()

    response = client.post(
        "/api/v1/backtests/run",
        json={
            "code": code,
            "strategy_name": "tw_momentum_breakout_long",
            "start_date": prices[0].trade_date.isoformat(),
            "end_date": prices[-1].trade_date.isoformat(),
            "initial_cash": 1_000_000,
            "lot_size": 1000,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["strategy_name"] == "tw_momentum_breakout_long"

    trades = payload["result"]["trades"]
    assert trades[0]["side"] == "BUY"
    assert trades[0]["date"] == prices[121].trade_date.isoformat()
    assert trades[1]["side"] == "SELL"
    assert trades[1]["date"] == prices[142].trade_date.isoformat()
