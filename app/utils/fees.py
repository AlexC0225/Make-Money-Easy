from math import floor


def calculate_fee(amount: float, fee_rate: float) -> int:
    return max(floor(amount * fee_rate), 1)


def calculate_tax(amount: float, tax_rate: float) -> int:
    return floor(amount * tax_rate)
