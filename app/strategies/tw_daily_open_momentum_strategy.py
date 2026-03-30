from statistics import mean

from app.db.models.market_data import DailyPrice
from app.strategies.base import StrategySignal


class TaiwanDailyOpenMomentumLongStrategy:
    """Single-stock momentum strategy for next-open execution.

    This strategy is intentionally limited to per-symbol logic because the current
    engine evaluates one stock at a time. Cross-sectional ranking, sector caps,
    and portfolio-level exposure controls should be handled by the caller.
    """

    name = "tw_daily_open_momentum_long"
    title = "Taiwan Daily Open Momentum Long-only"
    description = (
        "Conservative Taiwan momentum rules with liquidity and trend filters, "
        "daily open execution, and fixed plus ATR-based risk control."
    )
    minimum_required_history = 121
    execution_timing = "next_market_open"
    trade_frequency = "daily_open_once"
    is_long_only = True

    price_floor = 20.0
    minimum_average_volume = 100_000
    minimum_average_turnover = 80_000_000.0
    minimum_return_20 = 0.03
    minimum_return_60 = 0.08
    minimum_return_120 = 0.12
    minimum_relative_volume = 1.0
    maximum_extension_above_ma20 = 0.12
    atr_period = 14
    initial_stop_pct = 0.07
    initial_stop_atr_multiple = 2.0
    trailing_stop_atr_multiple = 2.5
    max_holding_days = 30
    ma_slope_lookback = 5

    def evaluate(self, prices: list[DailyPrice], position_context: dict | None = None) -> StrategySignal:
        valid_prices = [item for item in prices if item.close_price is not None]
        if len(valid_prices) < self.minimum_required_history:
            raise ValueError("Daily open momentum strategy requires at least 121 trading days of history.")

        latest = valid_prices[-1]
        closes = [float(item.close_price or 0) for item in valid_prices]
        highs = [float(item.high_price or item.close_price or 0) for item in valid_prices]
        lows = [float(item.low_price or item.close_price or 0) for item in valid_prices]
        volumes = [int(item.volume or 0) for item in valid_prices]
        turnovers = [float(item.turnover or 0) for item in valid_prices]

        latest_close = closes[-1]
        ma20 = self._sma(closes, 20)
        ma60 = self._sma(closes, 60)
        ma120 = self._sma(closes, 120)
        ma20_prev = self._sma(closes[: -self.ma_slope_lookback], 20)
        ma60_prev = self._sma(closes[: -self.ma_slope_lookback], 60)
        ma20_slope = ma20 - ma20_prev
        ma60_slope = ma60 - ma60_prev
        avg_volume20 = mean(volumes[-20:])
        avg_turnover20 = mean(turnovers[-20:])
        relative_volume = (volumes[-1] / avg_volume20) if avg_volume20 else 0.0
        return20 = self._return_over(closes, 20)
        return60 = self._return_over(closes, 60)
        return120 = self._return_over(closes, 120)
        breakout_level = max(closes[-21:-1])
        atr14 = self._atr(highs, lows, closes, self.atr_period)
        atr_pct = (atr14 / latest_close) if latest_close else 0.0
        extension_above_ma20 = ((latest_close / ma20) - 1.0) if ma20 else 0.0

        holding_days = self._holding_days(valid_prices, position_context)
        entry_price = float(position_context["entry_price"]) if position_context and position_context.get("entry_price") else 0.0
        has_position = bool(position_context and position_context.get("quantity", 0) > 0)
        highest_close_since_entry = self._highest_close_since_entry(valid_prices, position_context)

        fixed_stop = (entry_price * (1 - self.initial_stop_pct)) if entry_price else None
        atr_stop = (entry_price - (self.initial_stop_atr_multiple * atr14)) if entry_price else None
        trailing_stop = None
        if highest_close_since_entry is not None:
            trailing_stop = highest_close_since_entry - (self.trailing_stop_atr_multiple * atr14)

        protective_stop_candidates = [value for value in (fixed_stop, atr_stop, trailing_stop) if value is not None]
        protective_stop = max(protective_stop_candidates) if protective_stop_candidates else None

        snapshot = {
            "close": round(latest_close, 4),
            "ma20": round(ma20, 4),
            "ma60": round(ma60, 4),
            "ma120": round(ma120, 4),
            "ma20_slope": round(ma20_slope, 4),
            "ma60_slope": round(ma60_slope, 4),
            "avg_volume20": round(avg_volume20, 2),
            "avg_turnover20": round(avg_turnover20, 2),
            "relative_volume": round(relative_volume, 4),
            "return20": round(return20, 6),
            "return60": round(return60, 6),
            "return120": round(return120, 6),
            "breakout_level": round(breakout_level, 4),
            "atr14": round(atr14, 4),
            "atr_pct": round(atr_pct, 6),
            "extension_above_ma20": round(extension_above_ma20, 6),
            "holding_days": holding_days,
            "entry_price": round(entry_price, 4) if entry_price else 0.0,
            "fixed_stop": round(fixed_stop, 4) if fixed_stop is not None else None,
            "atr_stop": round(atr_stop, 4) if atr_stop is not None else None,
            "trailing_stop": round(trailing_stop, 4) if trailing_stop is not None else None,
            "protective_stop": round(protective_stop, 4) if protective_stop is not None else None,
        }

        if has_position:
            if protective_stop is not None and latest_close < protective_stop:
                return StrategySignal(self.name, "SELL", "close_below_protective_stop", latest.trade_date, snapshot)
            if latest_close < ma20:
                return StrategySignal(self.name, "SELL", "close_below_ma20", latest.trade_date, snapshot)
            if ma20_slope <= 0 and return20 <= 0:
                return StrategySignal(self.name, "SELL", "short_term_momentum_deterioration", latest.trade_date, snapshot)
            if holding_days >= self.max_holding_days:
                return StrategySignal(self.name, "SELL", "max_hold_30_days", latest.trade_date, snapshot)
            return StrategySignal(self.name, "HOLD", "holding_momentum_position", latest.trade_date, snapshot)

        if latest_close <= self.price_floor:
            return StrategySignal(self.name, "HOLD", "price_floor_filter", latest.trade_date, snapshot)
        if avg_volume20 < self.minimum_average_volume:
            return StrategySignal(self.name, "HOLD", "volume_filter", latest.trade_date, snapshot)
        if avg_turnover20 < self.minimum_average_turnover:
            return StrategySignal(self.name, "HOLD", "turnover_filter", latest.trade_date, snapshot)
        if not (latest_close > ma20 > ma60 > ma120):
            return StrategySignal(self.name, "HOLD", "trend_filter", latest.trade_date, snapshot)
        if ma20_slope <= 0:
            return StrategySignal(self.name, "HOLD", "ma20_slope_filter", latest.trade_date, snapshot)
        if ma60_slope <= 0:
            return StrategySignal(self.name, "HOLD", "ma60_slope_filter", latest.trade_date, snapshot)
        if return20 <= self.minimum_return_20:
            return StrategySignal(self.name, "HOLD", "return20_filter", latest.trade_date, snapshot)
        if return60 <= self.minimum_return_60:
            return StrategySignal(self.name, "HOLD", "return60_filter", latest.trade_date, snapshot)
        if return120 <= self.minimum_return_120:
            return StrategySignal(self.name, "HOLD", "return120_filter", latest.trade_date, snapshot)
        if latest_close <= breakout_level:
            return StrategySignal(self.name, "HOLD", "breakout_not_confirmed", latest.trade_date, snapshot)
        if relative_volume < self.minimum_relative_volume:
            return StrategySignal(self.name, "HOLD", "relative_volume_filter", latest.trade_date, snapshot)
        if extension_above_ma20 > self.maximum_extension_above_ma20:
            return StrategySignal(self.name, "HOLD", "too_extended_above_ma20", latest.trade_date, snapshot)

        return StrategySignal(
            strategy_name=self.name,
            signal="BUY",
            reason="trend_momentum_breakout_confirmed",
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
