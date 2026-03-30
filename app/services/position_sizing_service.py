from math import floor

from app.utils.fees import calculate_fee

POSITION_SIZING_FIXED_SHARES = "fixed_shares"
POSITION_SIZING_CASH_PERCENT = "cash_percent"


class PositionSizingServiceError(Exception):
    pass


def resolve_buy_quantity(
    *,
    available_cash: float,
    fill_price: float,
    lot_size: int,
    fee_rate: float,
    position_sizing_mode: str,
    buy_quantity: int,
    cash_allocation_pct: float,
) -> int:
    if fill_price <= 0:
        raise PositionSizingServiceError("Unable to resolve a valid trade price from quote data.")
    if lot_size <= 0:
        raise PositionSizingServiceError("Lot size must be greater than zero.")

    if position_sizing_mode == POSITION_SIZING_FIXED_SHARES:
        if buy_quantity <= 0:
            raise PositionSizingServiceError("Buy quantity must be greater than zero.")
        if buy_quantity % lot_size != 0:
            raise PositionSizingServiceError(f"Quantity must be a multiple of {lot_size} shares.")
        return buy_quantity

    if position_sizing_mode != POSITION_SIZING_CASH_PERCENT:
        raise PositionSizingServiceError(f"Unknown position sizing mode: {position_sizing_mode}")

    if cash_allocation_pct <= 0 or cash_allocation_pct > 100:
        raise PositionSizingServiceError("Cash allocation percent must be between 0 and 100.")

    allocation_budget = available_cash * (cash_allocation_pct / 100)
    quantity = floor(allocation_budget / fill_price)

    while quantity > 0:
        trade_amount = fill_price * quantity
        total_cost = trade_amount + calculate_fee(trade_amount, fee_rate)
        if total_cost <= available_cash and total_cost <= allocation_budget:
            return quantity
        quantity -= 1

    raise PositionSizingServiceError("Cash allocation is insufficient to buy any shares.")
