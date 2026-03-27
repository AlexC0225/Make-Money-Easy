from dataclasses import dataclass, field
from datetime import date


@dataclass
class StrategySignal:
    strategy_name: str
    signal: str
    reason: str | None
    trade_date: date
    snapshot: dict = field(default_factory=dict)
