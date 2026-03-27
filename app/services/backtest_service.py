from dataclasses import dataclass
from math import sqrt
from statistics import mean, pstdev
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.db.models.strategy import BacktestResult
from app.db.repositories.stock_repository import StockRepository
from app.schemas.strategy import BacktestResultRead
from app.services.strategy_service import StrategyService
from app.utils.fees import calculate_fee, calculate_tax


class BacktestServiceError(Exception):
    pass


@dataclass
class BacktestSpec:
    code: str
    strategy_name: str
    start_date: date
    end_date: date
    initial_cash: float
    lot_size: int


class BacktestService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()
        self.stock_repository = StockRepository(session)
        self.strategy_service = StrategyService(session)

    def run_backtest(self, payload: BacktestSpec) -> BacktestResultRead:
        stock = self.stock_repository.get_by_code(payload.code)
        if stock is None:
            raise BacktestServiceError("Stock not found. Please sync the stock first.")

        prices = self.stock_repository.get_daily_prices(
            stock.id,
            start_date=payload.start_date,
            end_date=payload.end_date,
        )
        strategy = self.strategy_service.get_strategy(payload.strategy_name)
        if len(prices) < strategy.minimum_required_history:
            raise BacktestServiceError(
                f"Backtest requires at least {strategy.minimum_required_history} trading days of history."
            )

        if strategy.execution_timing == "next_market_open":
            result_payload = self._run_next_open_backtest(payload, prices)
        else:
            result_payload = self._run_same_close_backtest(payload, prices)

        equity_values = [point["equity"] for point in result_payload["equity_curve"]]
        daily_returns = self._daily_returns(equity_values)
        closed_trade_pnls = [
            float(trade["pnl"])
            for trade in result_payload["trades"]
            if trade["side"] == "SELL" and "pnl" in trade
        ]
        closed_trade_returns = [
            float(trade["return"])
            for trade in result_payload["trades"]
            if trade["side"] == "SELL" and "return" in trade
        ]
        gross_profit = sum(item for item in closed_trade_pnls if item > 0)
        gross_loss = abs(sum(item for item in closed_trade_pnls if item < 0))

        db_row = BacktestResult(
            strategy_name=payload.strategy_name,
            stock_id=stock.id,
            start_date=payload.start_date,
            end_date=payload.end_date,
            total_return=round((result_payload["final_equity"] - payload.initial_cash) / payload.initial_cash, 6),
            max_drawdown=round(self._max_drawdown(equity_values), 6),
            win_rate=round(self._win_rate(closed_trade_returns), 6),
            profit_factor=round(gross_profit / gross_loss, 6) if gross_loss > 0 else 0.0,
            sharpe_ratio=round(self._sharpe_ratio(daily_returns), 6),
            result_json=result_payload,
        )
        self.session.add(db_row)
        self.session.flush()
        self.session.refresh(db_row)

        return BacktestResultRead(
            id=db_row.id,
            strategy_name=db_row.strategy_name,
            stock_code=stock.code,
            stock_name=stock.name,
            start_date=db_row.start_date,
            end_date=db_row.end_date,
            total_return=db_row.total_return,
            max_drawdown=db_row.max_drawdown,
            win_rate=db_row.win_rate,
            profit_factor=db_row.profit_factor,
            sharpe_ratio=db_row.sharpe_ratio,
            result=db_row.result_json,
            created_at=db_row.created_at,
        )

    def get_backtest_result(self, result_id: int) -> BacktestResultRead:
        statement = select(BacktestResult).where(BacktestResult.id == result_id).options(selectinload(BacktestResult.stock))
        row = self.session.scalar(statement)
        if row is None:
            raise BacktestServiceError("Backtest result not found.")

        return BacktestResultRead(
            id=row.id,
            strategy_name=row.strategy_name,
            stock_code=row.stock.code,
            stock_name=row.stock.name,
            start_date=row.start_date,
            end_date=row.end_date,
            total_return=row.total_return,
            max_drawdown=row.max_drawdown,
            win_rate=row.win_rate,
            profit_factor=row.profit_factor,
            sharpe_ratio=row.sharpe_ratio,
            result=row.result_json,
            created_at=row.created_at,
        )

    def list_backtest_results(self, limit: int = 20) -> list[BacktestResultRead]:
        statement = (
            select(BacktestResult)
            .options(selectinload(BacktestResult.stock))
            .order_by(BacktestResult.created_at.desc(), BacktestResult.id.desc())
            .limit(limit)
        )
        rows = list(self.session.scalars(statement))
        return [
            BacktestResultRead(
                id=row.id,
                strategy_name=row.strategy_name,
                stock_code=row.stock.code,
                stock_name=row.stock.name,
                start_date=row.start_date,
                end_date=row.end_date,
                total_return=row.total_return,
                max_drawdown=row.max_drawdown,
                win_rate=row.win_rate,
                profit_factor=row.profit_factor,
                sharpe_ratio=row.sharpe_ratio,
                result=row.result_json,
                created_at=row.created_at,
            )
            for row in rows
        ]

    def _run_same_close_backtest(self, payload: BacktestSpec, prices) -> dict:
        strategy = self.strategy_service.get_strategy(payload.strategy_name)
        cash = payload.initial_cash
        quantity = 0
        entry_cost = 0.0
        entry_price = 0.0
        entry_date = None
        equity_curve: list[dict] = []
        executed_trades: list[dict] = []
        realized_pnl = 0.0

        for index in range(strategy.minimum_required_history - 1, len(prices)):
            window = prices[: index + 1]
            current = window[-1]
            position_context = None
            if quantity > 0:
                position_context = {
                    "quantity": quantity,
                    "entry_price": entry_price,
                    "entry_date": entry_date,
                }
            signal = self.strategy_service.evaluate_strategy(
                payload.code,
                payload.strategy_name,
                window,
                position_context=position_context,
            )
            close_price = float(current.close_price or 0)
            if close_price <= 0:
                continue

            if quantity == 0 and signal.signal == "BUY":
                trade_amount = close_price * payload.lot_size
                fee = calculate_fee(trade_amount, self.settings.default_fee_rate)
                total_cost = trade_amount + fee
                if cash >= total_cost:
                    cash -= total_cost
                    quantity = payload.lot_size
                    entry_cost = total_cost
                    entry_price = close_price
                    entry_date = current.trade_date
                    executed_trades.append(
                        {
                            "date": current.trade_date.isoformat(),
                            "side": "BUY",
                            "price": close_price,
                            "quantity": payload.lot_size,
                            "reason": signal.reason,
                        }
                    )
            elif quantity > 0 and signal.signal == "SELL":
                trade_amount = close_price * quantity
                fee = calculate_fee(trade_amount, self.settings.default_fee_rate)
                tax = calculate_tax(trade_amount, self.settings.default_tax_rate)
                net_proceeds = trade_amount - fee - tax
                pnl = net_proceeds - entry_cost
                cash += net_proceeds
                realized_pnl += pnl
                executed_trades.append(
                    {
                        "date": current.trade_date.isoformat(),
                        "side": "SELL",
                        "price": close_price,
                        "quantity": quantity,
                        "reason": signal.reason,
                        "pnl": round(pnl, 2),
                        "return": round(pnl / entry_cost, 6) if entry_cost else 0.0,
                    }
                )
                quantity = 0
                entry_cost = 0.0
                entry_price = 0.0
                entry_date = None

            equity_curve.append(
                {
                    "date": current.trade_date.isoformat(),
                    "equity": round(cash + (quantity * close_price), 2),
                    "signal": signal.signal,
                    "close": close_price,
                }
            )

        final_close = float(prices[-1].close_price or 0)
        return {
            "initial_cash": payload.initial_cash,
            "final_equity": round(cash + (quantity * final_close), 2),
            "realized_pnl": round(realized_pnl, 2),
            "open_position_quantity": quantity,
            "trade_count": len(executed_trades),
            "closed_trade_count": sum(1 for trade in executed_trades if trade["side"] == "SELL"),
            "equity_curve": equity_curve,
            "trades": executed_trades,
        }

    def _run_next_open_backtest(self, payload: BacktestSpec, prices) -> dict:
        strategy = self.strategy_service.get_strategy(payload.strategy_name)
        cash = payload.initial_cash
        quantity = 0
        entry_cost = 0.0
        entry_price = 0.0
        entry_date = None
        equity_curve: list[dict] = []
        executed_trades: list[dict] = []
        realized_pnl = 0.0

        for index in range(strategy.minimum_required_history - 1, len(prices) - 1):
            window = prices[: index + 1]
            current = window[-1]
            next_bar = prices[index + 1]
            next_open = float(next_bar.open_price or next_bar.close_price or 0)
            if next_open <= 0:
                continue

            position_context = None
            if quantity > 0:
                position_context = {
                    "quantity": quantity,
                    "entry_price": entry_price,
                    "entry_date": entry_date,
                }
            signal = self.strategy_service.evaluate_strategy(
                payload.code,
                payload.strategy_name,
                window,
                position_context=position_context,
            )

            if quantity == 0 and signal.signal == "BUY":
                trade_amount = next_open * payload.lot_size
                fee = calculate_fee(trade_amount, self.settings.default_fee_rate)
                total_cost = trade_amount + fee
                if cash >= total_cost:
                    cash -= total_cost
                    quantity = payload.lot_size
                    entry_cost = total_cost
                    entry_price = next_open
                    entry_date = next_bar.trade_date
                    executed_trades.append(
                        {
                            "date": next_bar.trade_date.isoformat(),
                            "side": "BUY",
                            "price": next_open,
                            "quantity": payload.lot_size,
                            "reason": signal.reason,
                        }
                    )
            elif quantity > 0 and signal.signal == "SELL":
                trade_amount = next_open * quantity
                fee = calculate_fee(trade_amount, self.settings.default_fee_rate)
                tax = calculate_tax(trade_amount, self.settings.default_tax_rate)
                net_proceeds = trade_amount - fee - tax
                pnl = net_proceeds - entry_cost
                cash += net_proceeds
                realized_pnl += pnl
                executed_trades.append(
                    {
                        "date": next_bar.trade_date.isoformat(),
                        "side": "SELL",
                        "price": next_open,
                        "quantity": quantity,
                        "reason": signal.reason,
                        "pnl": round(pnl, 2),
                        "return": round(pnl / entry_cost, 6) if entry_cost else 0.0,
                    }
                )
                quantity = 0
                entry_cost = 0.0
                entry_price = 0.0
                entry_date = None

            close_price = float(current.close_price or 0)
            equity_curve.append(
                {
                    "date": current.trade_date.isoformat(),
                    "equity": round(cash + (quantity * close_price), 2),
                    "signal": signal.signal,
                    "close": close_price,
                }
            )

        final_close = float(prices[-1].close_price or 0)
        return {
            "initial_cash": payload.initial_cash,
            "final_equity": round(cash + (quantity * final_close), 2),
            "realized_pnl": round(realized_pnl, 2),
            "open_position_quantity": quantity,
            "trade_count": len(executed_trades),
            "closed_trade_count": sum(1 for trade in executed_trades if trade["side"] == "SELL"),
            "equity_curve": equity_curve,
            "trades": executed_trades,
        }

    @staticmethod
    def _daily_returns(equity_curve: list[float]) -> list[float]:
        returns: list[float] = []
        for previous, current in zip(equity_curve, equity_curve[1:]):
            if previous == 0:
                continue
            returns.append((current - previous) / previous)
        return returns

    @staticmethod
    def _max_drawdown(equity_curve: list[float]) -> float:
        if not equity_curve:
            return 0.0
        peak = equity_curve[0]
        max_drawdown = 0.0
        for equity in equity_curve:
            peak = max(peak, equity)
            drawdown = (peak - equity) / peak if peak else 0.0
            max_drawdown = max(max_drawdown, drawdown)
        return max_drawdown

    @staticmethod
    def _win_rate(closed_trade_returns: list[float]) -> float:
        if not closed_trade_returns:
            return 0.0
        wins = sum(1 for item in closed_trade_returns if item > 0)
        return wins / len(closed_trade_returns)

    @staticmethod
    def _sharpe_ratio(daily_returns: list[float]) -> float:
        if len(daily_returns) < 2:
            return 0.0
        volatility = pstdev(daily_returns)
        if volatility == 0:
            return 0.0
        return mean(daily_returns) / volatility * sqrt(252)
