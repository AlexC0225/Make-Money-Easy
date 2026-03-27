from statistics import mean

from app.db.models.market_data import DailyPrice
from app.strategies.base import StrategySignal


class LarryConnorsRsi2LongStrategy:
    name = "connors_rsi2_long"
    title = "Larry Connors RSI(2) Long-only"
    description = "收盤高於 SMA200 且 RSI(2) < 5 時做多，採日線均值回歸。"
    minimum_required_history = 200
    execution_timing = "next_market_open"
    trade_frequency = "daily_open_once"
    is_long_only = True

    def evaluate(self, prices: list[DailyPrice], position_context: dict | None = None) -> StrategySignal:
        closes = [float(item.close_price) for item in prices if item.close_price is not None]
        if len(closes) < self.minimum_required_history:
            raise ValueError("Larry Connors RSI(2) strategy requires at least 200 trading days of history.")

        latest = prices[-1]
        latest_close = float(latest.close_price or 0)
        sma200 = mean(closes[-200:])
        rsi2 = self._compute_rsi(closes, period=2)

        holding_days = self._holding_days(prices, position_context)
        entry_price = float(position_context["entry_price"]) if position_context and position_context.get("entry_price") else 0.0
        has_position = bool(position_context and position_context.get("quantity", 0) > 0)

        snapshot = {
            "close": latest_close,
            "sma200": round(sma200, 4),
            "rsi2": round(rsi2, 4),
            "holding_days": holding_days,
            "entry_price": round(entry_price, 4) if entry_price else 0.0,
        }

        if has_position:
            if rsi2 > 70:
                return StrategySignal(
                    strategy_name=self.name,
                    signal="SELL",
                    reason="rsi2_above_70",
                    trade_date=latest.trade_date,
                    snapshot=snapshot,
                )
            if entry_price and latest_close > entry_price:
                return StrategySignal(
                    strategy_name=self.name,
                    signal="SELL",
                    reason="close_above_entry_price",
                    trade_date=latest.trade_date,
                    snapshot=snapshot,
                )
            if holding_days >= 2:
                return StrategySignal(
                    strategy_name=self.name,
                    signal="SELL",
                    reason="max_hold_2_days",
                    trade_date=latest.trade_date,
                    snapshot=snapshot,
                )
            return StrategySignal(
                strategy_name=self.name,
                signal="HOLD",
                reason="holding_wait_exit",
                trade_date=latest.trade_date,
                snapshot=snapshot,
            )

        if latest_close > sma200 and rsi2 < 5:
            return StrategySignal(
                strategy_name=self.name,
                signal="BUY",
                reason="trend_above_sma200_and_rsi2_below_5",
                trade_date=latest.trade_date,
                snapshot=snapshot,
            )

        return StrategySignal(
            strategy_name=self.name,
            signal="HOLD",
            reason="entry_condition_not_met",
            trade_date=latest.trade_date,
            snapshot=snapshot,
        )

    def _holding_days(self, prices: list[DailyPrice], position_context: dict | None) -> int:
        if not position_context or not position_context.get("entry_date"):
            return 0
        entry_date = position_context["entry_date"]
        return max(sum(1 for item in prices if item.trade_date >= entry_date) - 1, 0)

    @staticmethod
    def _compute_rsi(closes: list[float], period: int = 2) -> float:
        if len(closes) < period + 1:
            raise ValueError("Not enough data to compute RSI.")

        gains: list[float] = []
        losses: list[float] = []
        for previous, current in zip(closes[-(period + 1):], closes[-period:]):
            delta = current - previous
            gains.append(max(delta, 0))
            losses.append(abs(min(delta, 0)))

        average_gain = sum(gains) / period
        average_loss = sum(losses) / period
        if average_loss == 0:
            return 100.0
        rs = average_gain / average_loss
        return 100 - (100 / (1 + rs))
