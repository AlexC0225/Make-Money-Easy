from statistics import mean

import twstock

from app.db.models.market_data import DailyPrice
from app.strategies.base import StrategySignal
from app.strategies.twstock_adapter import TwStockAnalyticsAdapter


class HybridTwStrategy:
    name = "hybrid_tw_strategy"
    title = "Hybrid TW Trend + BestFourPoint"
    description = "MA20 / MA60 趨勢搭配成交量與 BestFourPoint 訊號。"
    minimum_required_history = 60
    execution_timing = "same_close"
    trade_frequency = "signal_based"
    is_long_only = False

    def evaluate(self, prices: list[DailyPrice], position_context: dict | None = None) -> StrategySignal:
        if len(prices) < self.minimum_required_history:
            raise ValueError("Hybrid strategy requires at least 60 trading days of history.")

        latest = prices[-1]
        recent_closes = [item.close_price for item in prices if item.close_price is not None]
        recent_opens = [item.open_price for item in prices if item.open_price is not None]
        recent_highs = [item.high_price for item in prices if item.high_price is not None]
        recent_lows = [item.low_price for item in prices if item.low_price is not None]
        recent_volumes = [item.volume or 0 for item in prices]

        adapter = TwStockAnalyticsAdapter(
            open=[float(value) for value in recent_opens],
            price=[float(value) for value in recent_closes],
            high=[float(value) for value in recent_highs],
            low=[float(value) for value in recent_lows],
            capacity=[int(value) for value in recent_volumes],
        )
        best_four_point = twstock.BestFourPoint(adapter)

        ma20 = adapter.moving_average(adapter.price, 20)[-1]
        ma60 = adapter.moving_average(adapter.price, 60)[-1]
        ma5_series = adapter.moving_average(adapter.price, 5)
        avg_volume20 = round(mean(adapter.capacity[-20:]), 2)
        buy_reason = best_four_point.best_four_point_to_buy()
        sell_reason = best_four_point.best_four_point_to_sell()
        latest_close = float(latest.close_price or 0)
        latest_volume = int(latest.volume or 0)

        snapshot = {
            "close": latest_close,
            "ma5": ma5_series[-1],
            "ma20": ma20,
            "ma60": ma60,
            "avg_volume20": avg_volume20,
            "latest_volume": latest_volume,
        }

        if buy_reason and ma20 > ma60 and latest_close > ma20 and latest_volume >= avg_volume20:
            return StrategySignal(
                strategy_name=self.name,
                signal="BUY",
                reason=buy_reason,
                trade_date=latest.trade_date,
                snapshot=snapshot,
            )

        if sell_reason or latest_close < ma20:
            return StrategySignal(
                strategy_name=self.name,
                signal="SELL",
                reason=sell_reason or "close_below_ma20",
                trade_date=latest.trade_date,
                snapshot=snapshot,
            )

        return StrategySignal(
            strategy_name=self.name,
            signal="HOLD",
            reason="trend_filter_not_triggered",
            trade_date=latest.trade_date,
            snapshot=snapshot,
        )
