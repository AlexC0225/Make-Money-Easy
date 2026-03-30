from datetime import date
from dataclasses import dataclass
from math import sqrt
from statistics import mean, pstdev

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.db.models.strategy import BacktestResult
from app.db.models.stock import Stock
from app.db.repositories.stock_repository import StockRepository
from app.schemas.strategy import BacktestResultRead
from app.services.market_data_service import MarketDataService
from app.services.position_sizing_service import (
    PositionSizingServiceError,
    resolve_buy_quantity,
)
from app.services.strategy_service import StrategyService
from app.utils.fees import calculate_fee, calculate_tax

PORTFOLIO_STOCK_CODE = "__PORTFOLIO__"
PORTFOLIO_DISPLAY_CODE = "PORTFOLIO"
PORTFOLIO_STOCK_NAME = "Portfolio Basket"


class BacktestServiceError(Exception):
    pass


@dataclass
class BacktestSpec:
    codes: list[str]
    strategy_name: str
    start_date: date
    end_date: date
    initial_cash: float
    position_sizing_mode: str
    lot_size: int
    cash_allocation_pct: float
    max_open_positions: int


@dataclass
class OpenPositionState:
    stock_code: str
    stock_name: str
    quantity: int
    entry_cost: float
    entry_price: float
    entry_date: date


class BacktestService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()
        self.stock_repository = StockRepository(session)
        self.strategy_service = StrategyService(session)

    def run_backtest(self, payload: BacktestSpec) -> BacktestResultRead:
        codes = self._resolve_backtest_codes(payload.codes)
        payload.codes = codes

        strategy = self.strategy_service.get_strategy(payload.strategy_name)
        stocks_by_code, prices_by_code = self._load_backtest_universe(
            codes=codes,
            start_date=payload.start_date,
            end_date=payload.end_date,
            minimum_required_history=strategy.minimum_required_history,
        )

        if len(codes) == 1:
            stock = stocks_by_code[codes[0]]
            prices = prices_by_code[codes[0]]
            if strategy.execution_timing == "next_market_open":
                result_payload = self._run_next_open_backtest(payload, stock, prices)
            else:
                result_payload = self._run_same_close_backtest(payload, stock, prices)
            result_stock_id = stock.id
        else:
            if strategy.execution_timing == "next_market_open":
                result_payload = self._run_next_open_portfolio_backtest(payload, stocks_by_code, prices_by_code)
            else:
                result_payload = self._run_same_close_portfolio_backtest(payload, stocks_by_code, prices_by_code)
            result_stock_id = None

        # SQLite can fail to upgrade a long-lived read transaction into a writer
        # if another connection commits in the meantime. End the read transaction
        # before we persist the finished backtest result.
        self.session.rollback()

        if result_stock_id is None:
            result_stock = self._get_or_create_portfolio_stock()
        else:
            result_stock = self.session.get(Stock, result_stock_id)
            if result_stock is None:
                raise BacktestServiceError("Backtest stock not found while saving the result.")

        db_row = self._persist_backtest_result(payload, result_stock, result_payload)
        return self._serialize_backtest_result(db_row)

    def get_backtest_result(self, result_id: int) -> BacktestResultRead:
        statement = select(BacktestResult).where(BacktestResult.id == result_id).options(selectinload(BacktestResult.stock))
        row = self.session.scalar(statement)
        if row is None:
            raise BacktestServiceError("Backtest result not found.")
        return self._serialize_backtest_result(row)

    def list_backtest_results(self, limit: int = 20) -> list[BacktestResultRead]:
        statement = (
            select(BacktestResult)
            .options(selectinload(BacktestResult.stock))
            .order_by(BacktestResult.created_at.desc(), BacktestResult.id.desc())
            .limit(limit)
        )
        rows = list(self.session.scalars(statement))
        return [self._serialize_backtest_result(row) for row in rows]

    def _run_same_close_backtest(self, payload: BacktestSpec, stock: Stock, prices) -> dict:
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
                stock.code,
                payload.strategy_name,
                window,
                position_context=position_context,
            )
            close_price = float(current.close_price or 0)
            if close_price <= 0:
                continue

            if quantity == 0 and signal.signal == "BUY":
                try:
                    buy_quantity = self._resolve_backtest_buy_quantity(cash, close_price, payload)
                except PositionSizingServiceError:
                    buy_quantity = 0

                if buy_quantity > 0:
                    trade_amount = close_price * buy_quantity
                    fee = calculate_fee(trade_amount, self.settings.default_fee_rate)
                    total_cost = trade_amount + fee
                    cash -= total_cost
                    quantity = buy_quantity
                    entry_cost = total_cost
                    entry_price = close_price
                    entry_date = current.trade_date
                    executed_trades.append(
                        self._build_trade_entry(
                            trade_date=current.trade_date,
                            side="BUY",
                            price=close_price,
                            quantity=buy_quantity,
                            reason=signal.reason,
                            stock_code=stock.code,
                            stock_name=stock.name,
                        )
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
                    self._build_trade_entry(
                        trade_date=current.trade_date,
                        side="SELL",
                        price=close_price,
                        quantity=quantity,
                        reason=signal.reason,
                        stock_code=stock.code,
                        stock_name=stock.name,
                        pnl=pnl,
                        return_value=(pnl / entry_cost) if entry_cost else 0.0,
                    )
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
            "position_sizing_mode": payload.position_sizing_mode,
            "lot_size": payload.lot_size,
            "cash_allocation_pct": payload.cash_allocation_pct,
            "max_open_positions": payload.max_open_positions,
            "portfolio_codes": [],
            "is_portfolio": False,
            "final_equity": round(cash + (quantity * final_close), 2),
            "realized_pnl": round(realized_pnl, 2),
            "open_position_quantity": quantity,
            "open_position_count": 1 if quantity > 0 else 0,
            "trade_count": len(executed_trades),
            "closed_trade_count": sum(1 for trade in executed_trades if trade["side"] == "SELL"),
            "equity_curve": equity_curve,
            "trades": executed_trades,
            "open_positions": (
                [
                    {
                        "stock_code": stock.code,
                        "stock_name": stock.name,
                        "quantity": quantity,
                        "entry_price": round(entry_price, 2),
                        "market_price": round(final_close, 2),
                        "market_value": round(quantity * final_close, 2),
                        "entry_date": entry_date.isoformat() if entry_date else None,
                    }
                ]
                if quantity > 0
                else []
            ),
        }

    def _run_next_open_backtest(self, payload: BacktestSpec, stock: Stock, prices) -> dict:
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
                stock.code,
                payload.strategy_name,
                window,
                position_context=position_context,
            )

            if quantity == 0 and signal.signal == "BUY":
                try:
                    buy_quantity = self._resolve_backtest_buy_quantity(cash, next_open, payload)
                except PositionSizingServiceError:
                    buy_quantity = 0

                if buy_quantity > 0:
                    trade_amount = next_open * buy_quantity
                    fee = calculate_fee(trade_amount, self.settings.default_fee_rate)
                    total_cost = trade_amount + fee
                    cash -= total_cost
                    quantity = buy_quantity
                    entry_cost = total_cost
                    entry_price = next_open
                    entry_date = next_bar.trade_date
                    executed_trades.append(
                        self._build_trade_entry(
                            trade_date=next_bar.trade_date,
                            side="BUY",
                            price=next_open,
                            quantity=buy_quantity,
                            reason=signal.reason,
                            stock_code=stock.code,
                            stock_name=stock.name,
                        )
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
                    self._build_trade_entry(
                        trade_date=next_bar.trade_date,
                        side="SELL",
                        price=next_open,
                        quantity=quantity,
                        reason=signal.reason,
                        stock_code=stock.code,
                        stock_name=stock.name,
                        pnl=pnl,
                        return_value=(pnl / entry_cost) if entry_cost else 0.0,
                    )
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
            "position_sizing_mode": payload.position_sizing_mode,
            "lot_size": payload.lot_size,
            "cash_allocation_pct": payload.cash_allocation_pct,
            "max_open_positions": payload.max_open_positions,
            "portfolio_codes": [],
            "is_portfolio": False,
            "final_equity": round(cash + (quantity * final_close), 2),
            "realized_pnl": round(realized_pnl, 2),
            "open_position_quantity": quantity,
            "open_position_count": 1 if quantity > 0 else 0,
            "trade_count": len(executed_trades),
            "closed_trade_count": sum(1 for trade in executed_trades if trade["side"] == "SELL"),
            "equity_curve": equity_curve,
            "trades": executed_trades,
            "open_positions": (
                [
                    {
                        "stock_code": stock.code,
                        "stock_name": stock.name,
                        "quantity": quantity,
                        "entry_price": round(entry_price, 2),
                        "market_price": round(final_close, 2),
                        "market_value": round(quantity * final_close, 2),
                        "entry_date": entry_date.isoformat() if entry_date else None,
                    }
                ]
                if quantity > 0
                else []
            ),
        }

    def _run_same_close_portfolio_backtest(
        self,
        payload: BacktestSpec,
        stocks_by_code: dict[str, Stock],
        prices_by_code: dict[str, list],
    ) -> dict:
        strategy = self.strategy_service.get_strategy(payload.strategy_name)
        dates = self._collect_trade_dates(prices_by_code)
        last_close_by_code: dict[str, float] = {}
        positions: dict[str, OpenPositionState] = {}
        equity_curve: list[dict] = []
        executed_trades: list[dict] = []
        realized_pnl = 0.0
        cash = payload.initial_cash

        for current_date in dates:
            day_evaluations: list[dict] = []
            for code in payload.codes:
                series = prices_by_code[code]
                current_bar = self._get_price_for_date(series, current_date)
                if current_bar is not None and current_bar.close_price is not None:
                    last_close_by_code[code] = float(current_bar.close_price)
                if current_bar is None:
                    continue

                window = [item for item in series if item.trade_date <= current_date]
                if len(window) < strategy.minimum_required_history:
                    continue

                signal = self.strategy_service.evaluate_strategy(
                    code,
                    payload.strategy_name,
                    window,
                    position_context=self._build_position_context(positions.get(code)),
                )
                day_evaluations.append(
                    {
                        "code": code,
                        "stock_name": stocks_by_code[code].name,
                        "signal": signal,
                        "current_bar": current_bar,
                    }
                )

            for evaluation in day_evaluations:
                code = evaluation["code"]
                position = positions.get(code)
                current_bar = evaluation["current_bar"]
                signal = evaluation["signal"]
                close_price = float(current_bar.close_price or 0)
                if position is None or signal.signal != "SELL" or close_price <= 0:
                    continue

                trade_amount = close_price * position.quantity
                fee = calculate_fee(trade_amount, self.settings.default_fee_rate)
                tax = calculate_tax(trade_amount, self.settings.default_tax_rate)
                net_proceeds = trade_amount - fee - tax
                pnl = net_proceeds - position.entry_cost
                cash += net_proceeds
                realized_pnl += pnl
                executed_trades.append(
                    self._build_trade_entry(
                        trade_date=current_date,
                        side="SELL",
                        price=close_price,
                        quantity=position.quantity,
                        reason=signal.reason,
                        stock_code=code,
                        stock_name=position.stock_name,
                        pnl=pnl,
                        return_value=(pnl / position.entry_cost) if position.entry_cost else 0.0,
                    )
                )
                positions.pop(code, None)

            for evaluation in day_evaluations:
                if len(positions) >= payload.max_open_positions:
                    break

                code = evaluation["code"]
                signal = evaluation["signal"]
                current_bar = evaluation["current_bar"]
                close_price = float(current_bar.close_price or 0)
                if signal.signal != "BUY" or code in positions or close_price <= 0:
                    continue

                try:
                    buy_quantity = self._resolve_backtest_buy_quantity(cash, close_price, payload)
                except PositionSizingServiceError:
                    buy_quantity = 0
                if buy_quantity <= 0:
                    continue

                trade_amount = close_price * buy_quantity
                fee = calculate_fee(trade_amount, self.settings.default_fee_rate)
                total_cost = trade_amount + fee
                if total_cost > cash:
                    continue

                cash -= total_cost
                positions[code] = OpenPositionState(
                    stock_code=code,
                    stock_name=evaluation["stock_name"],
                    quantity=buy_quantity,
                    entry_cost=total_cost,
                    entry_price=close_price,
                    entry_date=current_date,
                )
                executed_trades.append(
                    self._build_trade_entry(
                        trade_date=current_date,
                        side="BUY",
                        price=close_price,
                        quantity=buy_quantity,
                        reason=signal.reason,
                        stock_code=code,
                        stock_name=evaluation["stock_name"],
                    )
                )

            holdings_value = self._portfolio_holdings_value(positions, last_close_by_code)
            equity_curve.append(
                {
                    "date": current_date.isoformat(),
                    "equity": round(cash + holdings_value, 2),
                    "cash": round(cash, 2),
                    "holdings_value": round(holdings_value, 2),
                    "open_positions": len(positions),
                }
            )

        final_equity = equity_curve[-1]["equity"] if equity_curve else round(payload.initial_cash, 2)
        return {
            "initial_cash": payload.initial_cash,
            "position_sizing_mode": payload.position_sizing_mode,
            "lot_size": payload.lot_size,
            "cash_allocation_pct": payload.cash_allocation_pct,
            "max_open_positions": payload.max_open_positions,
            "portfolio_codes": payload.codes,
            "is_portfolio": True,
            "final_equity": final_equity,
            "realized_pnl": round(realized_pnl, 2),
            "open_position_quantity": sum(position.quantity for position in positions.values()),
            "open_position_count": len(positions),
            "trade_count": len(executed_trades),
            "closed_trade_count": sum(1 for trade in executed_trades if trade["side"] == "SELL"),
            "equity_curve": equity_curve,
            "trades": executed_trades,
            "open_positions": self._serialize_open_positions(positions, last_close_by_code),
        }

    def _run_next_open_portfolio_backtest(
        self,
        payload: BacktestSpec,
        stocks_by_code: dict[str, Stock],
        prices_by_code: dict[str, list],
    ) -> dict:
        strategy = self.strategy_service.get_strategy(payload.strategy_name)
        dates = self._collect_trade_dates(prices_by_code)
        next_bar_lookup = {
            code: {
                series[index].trade_date: series[index + 1]
                for index in range(len(series) - 1)
            }
            for code, series in prices_by_code.items()
        }

        last_close_by_code: dict[str, float] = {}
        positions: dict[str, OpenPositionState] = {}
        equity_curve: list[dict] = []
        executed_trades: list[dict] = []
        realized_pnl = 0.0
        cash = payload.initial_cash
        code_priority = {code: index for index, code in enumerate(payload.codes)}
        queued_orders: dict[date, list[dict]] = {}

        for current_date in dates:
            orders_for_today = sorted(
                queued_orders.pop(current_date, []),
                key=lambda item: (0 if item["side"] == "SELL" else 1, code_priority[item["stock_code"]]),
            )

            for order in orders_for_today:
                code = order["stock_code"]
                position = positions.get(code)
                price = float(order["price"])
                if order["side"] != "SELL" or position is None or price <= 0:
                    continue

                trade_amount = price * position.quantity
                fee = calculate_fee(trade_amount, self.settings.default_fee_rate)
                tax = calculate_tax(trade_amount, self.settings.default_tax_rate)
                net_proceeds = trade_amount - fee - tax
                pnl = net_proceeds - position.entry_cost
                cash += net_proceeds
                realized_pnl += pnl
                executed_trades.append(
                    self._build_trade_entry(
                        trade_date=current_date,
                        side="SELL",
                        price=price,
                        quantity=position.quantity,
                        reason=order["reason"],
                        stock_code=code,
                        stock_name=position.stock_name,
                        pnl=pnl,
                        return_value=(pnl / position.entry_cost) if position.entry_cost else 0.0,
                    )
                )
                positions.pop(code, None)

            for order in orders_for_today:
                code = order["stock_code"]
                stock_name = order["stock_name"]
                price = float(order["price"])
                if order["side"] != "BUY" or code in positions or price <= 0:
                    continue
                if len(positions) >= payload.max_open_positions:
                    break

                try:
                    buy_quantity = self._resolve_backtest_buy_quantity(cash, price, payload)
                except PositionSizingServiceError:
                    buy_quantity = 0
                if buy_quantity <= 0:
                    continue

                trade_amount = price * buy_quantity
                fee = calculate_fee(trade_amount, self.settings.default_fee_rate)
                total_cost = trade_amount + fee
                if total_cost > cash:
                    continue

                cash -= total_cost
                positions[code] = OpenPositionState(
                    stock_code=code,
                    stock_name=stock_name,
                    quantity=buy_quantity,
                    entry_cost=total_cost,
                    entry_price=price,
                    entry_date=current_date,
                )
                executed_trades.append(
                    self._build_trade_entry(
                        trade_date=current_date,
                        side="BUY",
                        price=price,
                        quantity=buy_quantity,
                        reason=order["reason"],
                        stock_code=code,
                        stock_name=stock_name,
                    )
                )

            for code in payload.codes:
                current_bar = self._get_price_for_date(prices_by_code[code], current_date)
                if current_bar is not None and current_bar.close_price is not None:
                    last_close_by_code[code] = float(current_bar.close_price)

            for code in payload.codes:
                series = prices_by_code[code]
                current_bar = self._get_price_for_date(series, current_date)
                next_bar = next_bar_lookup[code].get(current_date)
                if current_bar is None or next_bar is None:
                    continue

                window = [item for item in series if item.trade_date <= current_date]
                if len(window) < strategy.minimum_required_history:
                    continue

                signal = self.strategy_service.evaluate_strategy(
                    code,
                    payload.strategy_name,
                    window,
                    position_context=self._build_position_context(positions.get(code)),
                )
                if signal.signal == "HOLD":
                    continue

                execution_price = float(next_bar.open_price or next_bar.close_price or 0)
                if execution_price <= 0:
                    continue

                queued_orders.setdefault(next_bar.trade_date, []).append(
                    {
                        "stock_code": code,
                        "stock_name": stocks_by_code[code].name,
                        "side": signal.signal,
                        "price": execution_price,
                        "reason": signal.reason,
                    }
                )

            holdings_value = self._portfolio_holdings_value(positions, last_close_by_code)
            equity_curve.append(
                {
                    "date": current_date.isoformat(),
                    "equity": round(cash + holdings_value, 2),
                    "cash": round(cash, 2),
                    "holdings_value": round(holdings_value, 2),
                    "open_positions": len(positions),
                }
            )

        final_equity = equity_curve[-1]["equity"] if equity_curve else round(payload.initial_cash, 2)
        return {
            "initial_cash": payload.initial_cash,
            "position_sizing_mode": payload.position_sizing_mode,
            "lot_size": payload.lot_size,
            "cash_allocation_pct": payload.cash_allocation_pct,
            "max_open_positions": payload.max_open_positions,
            "portfolio_codes": payload.codes,
            "is_portfolio": True,
            "final_equity": final_equity,
            "realized_pnl": round(realized_pnl, 2),
            "open_position_quantity": sum(position.quantity for position in positions.values()),
            "open_position_count": len(positions),
            "trade_count": len(executed_trades),
            "closed_trade_count": sum(1 for trade in executed_trades if trade["side"] == "SELL"),
            "equity_curve": equity_curve,
            "trades": executed_trades,
            "open_positions": self._serialize_open_positions(positions, last_close_by_code),
        }

    def _persist_backtest_result(self, payload: BacktestSpec, stock: Stock, result_payload: dict) -> BacktestResult:
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
        return db_row

    def _serialize_backtest_result(self, row: BacktestResult) -> BacktestResultRead:
        result_json = row.result_json or {}
        portfolio_codes = [
            str(item).strip().upper()
            for item in result_json.get("portfolio_codes", [])
            if str(item).strip()
        ]
        is_portfolio = bool(result_json.get("is_portfolio") or portfolio_codes)
        stock_code = PORTFOLIO_DISPLAY_CODE if is_portfolio else row.stock.code
        stock_name = f"{len(portfolio_codes)}-stock portfolio" if is_portfolio else row.stock.name

        return BacktestResultRead(
            id=row.id,
            strategy_name=row.strategy_name,
            stock_code=stock_code,
            stock_name=stock_name,
            portfolio_codes=portfolio_codes,
            is_portfolio=is_portfolio,
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

    def _load_backtest_universe(
        self,
        codes: list[str],
        start_date: date,
        end_date: date,
        minimum_required_history: int,
    ) -> tuple[dict[str, Stock], dict[str, list]]:
        stocks_by_code: dict[str, Stock] = {}
        prices_by_code: dict[str, list] = {}

        for code in codes:
            stock = self.stock_repository.get_by_code(code)
            if stock is None:
                raise BacktestServiceError(f"Stock not found: {code}. Please sync the stock first.")

            prices = self.stock_repository.get_daily_prices(
                stock.id,
                start_date=start_date,
                end_date=end_date,
            )
            if len(prices) < minimum_required_history:
                raise BacktestServiceError(
                    f"Backtest requires at least {minimum_required_history} trading days of history for {code}."
                )

            stocks_by_code[code] = stock
            prices_by_code[code] = prices

        return stocks_by_code, prices_by_code

    def _resolve_backtest_codes(self, codes: list[str]) -> list[str]:
        normalized = [code.strip().upper() for code in codes if code.strip()]
        if normalized:
            return normalized

        default_codes = [
            stock.code
            for stock in self.stock_repository.list_active_stocks_by_industries(
                MarketDataService.DEFAULT_SYNC_POOL_INDUSTRIES
            )
            if isinstance(stock.code, str) and stock.code.strip()
        ]
        resolved_codes: list[str] = []
        seen: set[str] = set()
        for code in default_codes:
            normalized_code = code.strip().upper()
            if normalized_code in seen:
                continue
            seen.add(normalized_code)
            resolved_codes.append(normalized_code)

        if not resolved_codes:
            raise BacktestServiceError("No stock codes were provided and the default backtest list is empty.")
        return resolved_codes

    def _get_or_create_portfolio_stock(self) -> Stock:
        return self.stock_repository.upsert_stock(
            code=PORTFOLIO_STOCK_CODE,
            name=PORTFOLIO_STOCK_NAME,
            market="SYSTEM",
            industry="PORTFOLIO",
            is_active=False,
        )

    def _resolve_backtest_buy_quantity(self, cash: float, entry_price: float, payload: BacktestSpec) -> int:
        return resolve_buy_quantity(
            available_cash=cash,
            fill_price=entry_price,
            lot_size=self.settings.default_lot_size,
            fee_rate=self.settings.default_fee_rate,
            position_sizing_mode=payload.position_sizing_mode,
            buy_quantity=payload.lot_size,
            cash_allocation_pct=payload.cash_allocation_pct,
        )

    @staticmethod
    def _build_position_context(position: OpenPositionState | None) -> dict | None:
        if position is None or position.quantity <= 0:
            return None
        return {
            "quantity": position.quantity,
            "entry_price": position.entry_price,
            "entry_date": position.entry_date,
        }

    @staticmethod
    def _build_trade_entry(
        trade_date: date,
        side: str,
        price: float,
        quantity: int,
        reason: str | None,
        stock_code: str,
        stock_name: str,
        pnl: float | None = None,
        return_value: float | None = None,
    ) -> dict:
        payload = {
            "date": trade_date.isoformat(),
            "side": side,
            "price": round(price, 2),
            "quantity": quantity,
            "reason": reason,
            "stock_code": stock_code,
            "stock_name": stock_name,
        }
        if pnl is not None:
            payload["pnl"] = round(pnl, 2)
        if return_value is not None:
            payload["return"] = round(return_value, 6)
        return payload

    @staticmethod
    def _get_price_for_date(series: list, trade_date: date):
        for item in series:
            if item.trade_date == trade_date:
                return item
        return None

    @staticmethod
    def _collect_trade_dates(prices_by_code: dict[str, list]) -> list[date]:
        return sorted({item.trade_date for series in prices_by_code.values() for item in series})

    @staticmethod
    def _portfolio_holdings_value(positions: dict[str, OpenPositionState], last_close_by_code: dict[str, float]) -> float:
        holdings_value = 0.0
        for code, position in positions.items():
            market_price = last_close_by_code.get(code, position.entry_price)
            holdings_value += position.quantity * market_price
        return holdings_value

    @staticmethod
    def _serialize_open_positions(
        positions: dict[str, OpenPositionState],
        last_close_by_code: dict[str, float],
    ) -> list[dict]:
        serialized: list[dict] = []
        for code, position in positions.items():
            market_price = last_close_by_code.get(code, position.entry_price)
            serialized.append(
                {
                    "stock_code": code,
                    "stock_name": position.stock_name,
                    "quantity": position.quantity,
                    "entry_price": round(position.entry_price, 2),
                    "market_price": round(market_price, 2),
                    "market_value": round(position.quantity * market_price, 2),
                    "entry_date": position.entry_date.isoformat(),
                }
            )
        return serialized

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
