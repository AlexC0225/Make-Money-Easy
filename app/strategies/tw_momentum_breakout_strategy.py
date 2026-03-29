from statistics import mean

from app.db.models.market_data import DailyPrice
from app.strategies.base import StrategySignal


class TaiwanMomentumBreakoutLongStrategy:
    """Daily breakout momentum strategy adapted to the current single-stock engine."""

    name = "tw_momentum_breakout_long"
    title = "Taiwan Momentum Breakout Long-only"
    description = (
        "Trend filter + 20-day breakout + volume expansion + RSI(14), "
        "with ATR-based trailing stop and max holding period control."
    )
    minimum_required_history = 120
    execution_timing = "next_market_open"
    trade_frequency = "daily_open_once"
    is_long_only = True

    price_floor = 20.0
    minimum_average_volume = 50_000
    minimum_average_turnover = 20_000_000.0
    minimum_return_60 = 0.10
    minimum_rsi_entry = 55.0
    maximum_rsi_exit = 50.0
    breakout_lookback = 20
    volume_expansion_ratio = 1.5
    atr_period = 14
    max_holding_days = 20
    initial_stop_atr_multiple = 2.0
    trailing_stop_atr_multiple = 2.5
    ma_slope_lookback = 5

    def evaluate(self, prices: list[DailyPrice], position_context: dict | None = None) -> StrategySignal:
        valid_prices = [item for item in prices if item.close_price is not None]
        if len(valid_prices) < self.minimum_required_history:
            raise ValueError("Momentum breakout strategy requires at least 120 trading days of history.")

        latest = valid_prices[-1]
        closes = [float(item.close_price or 0) for item in valid_prices]
        highs = [float(item.high_price or item.close_price or 0) for item in valid_prices]
        lows = [float(item.low_price or item.close_price or 0) for item in valid_prices]
        volumes = [int(item.volume or 0) for item in valid_prices]
        turnovers = [float(item.turnover or 0) for item in valid_prices]

        latest_close = closes[-1]
        ma10 = self._sma(closes, 10)
        ma20 = self._sma(closes, 20)
        ma60 = self._sma(closes, 60)
        ma60_prev = self._sma(closes[: -self.ma_slope_lookback], 60)
        ma60_slope = ma60 - ma60_prev
        breakout_level = max(closes[-(self.breakout_lookback + 1) : -1])
        avg_volume20 = mean(volumes[-20:])
        avg_turnover20 = mean(turnovers[-20:])
        relative_volume = (volumes[-1] / avg_volume20) if avg_volume20 else 0.0
        return20 = self._return_over(closes, 20)
        return60 = self._return_over(closes, 60)
        rsi14 = self._rsi(closes, 14)
        atr14 = self._atr(highs, lows, closes, self.atr_period)
        holding_days = self._holding_days(valid_prices, position_context)
        entry_price = float(position_context["entry_price"]) if position_context and position_context.get("entry_price") else 0.0
        highest_close_since_entry = self._highest_close_since_entry(valid_prices, position_context)
        initial_stop = (entry_price - (self.initial_stop_atr_multiple * atr14)) if entry_price else None
        trailing_stop = None
        if highest_close_since_entry is not None:
            trailing_stop = highest_close_since_entry - (self.trailing_stop_atr_multiple * atr14)
            if initial_stop is not None:
                trailing_stop = max(trailing_stop, initial_stop)

        snapshot = {
            "close": round(latest_close, 4),
            "ma10": round(ma10, 4),
            "ma20": round(ma20, 4),
            "ma60": round(ma60, 4),
            "ma60_slope": round(ma60_slope, 4),
            "breakout_level": round(breakout_level, 4),
            "avg_volume20": round(avg_volume20, 2),
            "avg_turnover20": round(avg_turnover20, 2),
            "relative_volume": round(relative_volume, 4),
            "return20": round(return20, 6),
            "return60": round(return60, 6),
            "rsi14": round(rsi14, 4),
            "atr14": round(atr14, 4),
            "holding_days": holding_days,
            "entry_price": round(entry_price, 4) if entry_price else 0.0,
            "trailing_stop": round(trailing_stop, 4) if trailing_stop is not None else None,
        }

        has_position = bool(position_context and position_context.get("quantity", 0) > 0)
        if has_position:
            if latest_close < ma10:
                return StrategySignal(self.name, "SELL", "close_below_ma10", latest.trade_date, snapshot)
            if rsi14 < self.maximum_rsi_exit:
                return StrategySignal(self.name, "SELL", "rsi14_below_50", latest.trade_date, snapshot)
            if trailing_stop is not None and latest_close < trailing_stop:
                return StrategySignal(self.name, "SELL", "close_below_atr_trailing_stop", latest.trade_date, snapshot)
            if holding_days >= self.max_holding_days:
                return StrategySignal(self.name, "SELL", "max_hold_20_days", latest.trade_date, snapshot)
            return StrategySignal(self.name, "HOLD", "holding_momentum_position", latest.trade_date, snapshot)

        if latest_close <= self.price_floor:
            return StrategySignal(self.name, "HOLD", "price_floor_filter", latest.trade_date, snapshot)
        if avg_volume20 < self.minimum_average_volume:
            return StrategySignal(self.name, "HOLD", "volume_filter", latest.trade_date, snapshot)
        if avg_turnover20 < self.minimum_average_turnover:
            return StrategySignal(self.name, "HOLD", "turnover_filter", latest.trade_date, snapshot)
        if not (latest_close > ma20 > ma60):
            return StrategySignal(self.name, "HOLD", "trend_filter", latest.trade_date, snapshot)
        if ma60_slope <= 0:
            return StrategySignal(self.name, "HOLD", "ma60_slope_filter", latest.trade_date, snapshot)
        if return60 <= self.minimum_return_60:
            return StrategySignal(self.name, "HOLD", "return60_filter", latest.trade_date, snapshot)
        if latest_close <= breakout_level:
            return StrategySignal(self.name, "HOLD", "breakout_not_confirmed", latest.trade_date, snapshot)
        if relative_volume <= self.volume_expansion_ratio:
            return StrategySignal(self.name, "HOLD", "volume_expansion_filter", latest.trade_date, snapshot)
        if rsi14 <= self.minimum_rsi_entry:
            return StrategySignal(self.name, "HOLD", "rsi14_filter", latest.trade_date, snapshot)

        return StrategySignal(
            strategy_name=self.name,
            signal="BUY",
            reason="trend_breakout_volume_rsi_confirmed",
            trade_date=latest.trade_date,
            snapshot=snapshot,
        )

    @staticmethod
    def _sma(values: list[float], period: int) -> float:
        if len(values) < period:
            raise ValueError(f"Not enough data to compute SMA({period}).")
        return sum(values[-period:]) / period

    @staticmethod
    def _return_over(values: list[float], lookback: int) -> float:
        if len(values) <= lookback:
            raise ValueError(f"Not enough data to compute {lookback}-day return.")
        anchor = values[-(lookback + 1)]
        if anchor == 0:
            return 0.0
        return (values[-1] / anchor) - 1

    @staticmethod
    def _rsi(values: list[float], period: int) -> float:
        if len(values) < period + 1:
            raise ValueError(f"Not enough data to compute RSI({period}).")

        gains: list[float] = []
        losses: list[float] = []
        for previous, current in zip(values[-(period + 1) :], values[-period:]):
            delta = current - previous
            gains.append(max(delta, 0.0))
            losses.append(abs(min(delta, 0.0)))

        average_gain = sum(gains) / period
        average_loss = sum(losses) / period
        if average_loss == 0:
            return 100.0
        rs = average_gain / average_loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _atr(highs: list[float], lows: list[float], closes: list[float], period: int) -> float:
        if len(closes) < period + 1:
            raise ValueError(f"Not enough data to compute ATR({period}).")

        true_ranges: list[float] = []
        for index in range(len(closes) - period, len(closes)):
            previous_close = closes[index - 1]
            high = highs[index]
            low = lows[index]
            true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
        return sum(true_ranges) / period

    @staticmethod
    def _holding_days(prices: list[DailyPrice], position_context: dict | None) -> int:
        if not position_context or not position_context.get("entry_date"):
            return 0
        entry_date = position_context["entry_date"]
        return max(sum(1 for item in prices if item.trade_date >= entry_date) - 1, 0)

    @staticmethod
    def _highest_close_since_entry(prices: list[DailyPrice], position_context: dict | None) -> float | None:
        if not position_context or not position_context.get("entry_date"):
            return None

        entry_date = position_context["entry_date"]
        closes_since_entry = [
            float(item.close_price)
            for item in prices
            if item.trade_date >= entry_date and item.close_price is not None
        ]
        if not closes_since_entry:
            return None
        return max(closes_since_entry)
