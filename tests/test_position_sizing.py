from datetime import date

from app.db.session import get_session_factory
from app.services.position_sizing_service import resolve_buy_quantity
from app.services.strategy_service import StrategyService
from app.strategies.base import StrategySignal


def test_resolve_buy_quantity_uses_cash_percent_to_fill_budget_with_odd_lot_remainder():
    quantity = resolve_buy_quantity(
        available_cash=1_000_000,
        fill_price=123.4,
        lot_size=1000,
        fee_rate=0.001425,
        position_sizing_mode="cash_percent",
        buy_quantity=1000,
        cash_allocation_pct=25,
    )

    assert quantity == 2023


def test_resolve_buy_quantity_uses_odd_lot_when_cash_percent_cannot_afford_full_lot():
    quantity = resolve_buy_quantity(
        available_cash=50_000,
        fill_price=800,
        lot_size=1000,
        fee_rate=0.001425,
        position_sizing_mode="cash_percent",
        buy_quantity=1000,
        cash_allocation_pct=10,
    )

    assert quantity == 6


def test_strategy_service_skips_buy_when_max_open_positions_reached():
    session = get_session_factory()()
    try:
        service = StrategyService(session)
        service._get_position = lambda user_id, code: None  # type: ignore[method-assign]
        service._count_open_positions = lambda user_id: service.settings.max_open_positions  # type: ignore[method-assign]

        result = service._apply_signal_to_portfolio(
            user_id=1,
            code="2330",
            signal=StrategySignal(
                strategy_name="connors_rsi2_long",
                signal="BUY",
                reason="entry",
                trade_date=date(2026, 3, 30),
                snapshot={},
            ),
            position_sizing_mode="fixed_shares",
            buy_quantity=1000,
            cash_allocation_pct=10,
            twstock_client=object(),  # type: ignore[arg-type]
        )

        assert result.status == "SKIPPED"
        assert result.message == f"Max open positions reached ({service.settings.max_open_positions})."
    finally:
        session.close()
