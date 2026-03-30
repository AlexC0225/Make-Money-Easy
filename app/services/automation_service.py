from dataclasses import dataclass

from app.db.repositories.user_repository import UserRepository
from app.config import get_settings
from app.schemas.strategy import AutomationConfigRead, AutomationConfigUpdateRequest
from app.services.market_data_service import MarketDataService
from app.services.position_sizing_service import POSITION_SIZING_FIXED_SHARES
from app.services.strategy_service import StrategyService, StrategyServiceError
from app.services.twstock_client import TwStockClient


class AutomationServiceError(Exception):
    pass


@dataclass
class AutomationRunSummary:
    processed_users: int
    applied_users: int
    failed_users: list[int]
    execution_details: list[dict[str, object]]


class AutomationService:
    def __init__(self, session, twstock_client: TwStockClient) -> None:
        self.session = session
        self.twstock_client = twstock_client
        self.user_repository = UserRepository(session)

    def get_or_create_config(self, user_id: int) -> AutomationConfigRead:
        user = self.user_repository.get_user(user_id)
        if user is None:
            raise AutomationServiceError("User not found.")

        config = self.user_repository.get_automation_config_by_user_id(user_id)
        if config is None:
            settings = get_settings()
            config = self.user_repository.upsert_automation_config(
                user_id=user_id,
                strategy_name="connors_rsi2_long",
                position_sizing_mode=POSITION_SIZING_FIXED_SHARES,
                buy_quantity=1000,
                cash_allocation_pct=settings.default_cash_allocation_pct,
                enabled=True,
            )

        return AutomationConfigRead(
            user_id=config.user_id,
            enabled=config.enabled,
            strategy_name=config.strategy_name,
            position_sizing_mode=config.position_sizing_mode,
            buy_quantity=config.buy_quantity,
            cash_allocation_pct=config.cash_allocation_pct,
            updated_at=config.updated_at,
        )

    def update_config(self, user_id: int, payload: AutomationConfigUpdateRequest) -> AutomationConfigRead:
        user = self.user_repository.get_user(user_id)
        if user is None:
            raise AutomationServiceError("User not found.")

        config = self.user_repository.upsert_automation_config(
            user_id=user_id,
            enabled=payload.enabled,
            strategy_name=payload.strategy_name,
            position_sizing_mode=payload.position_sizing_mode,
            buy_quantity=payload.buy_quantity,
            cash_allocation_pct=payload.cash_allocation_pct,
        )
        return AutomationConfigRead(
            user_id=config.user_id,
            enabled=config.enabled,
            strategy_name=config.strategy_name,
            position_sizing_mode=config.position_sizing_mode,
            buy_quantity=config.buy_quantity,
            cash_allocation_pct=config.cash_allocation_pct,
            updated_at=config.updated_at,
        )

    def resolve_daily_sync_codes(self) -> list[str]:
        market_data_service = MarketDataService(self.session, self.twstock_client)
        all_codes: list[str] = []
        for user in self.user_repository.list_users():
            try:
                selection = market_data_service.resolve_sync_targets(codes=None, user_id=user.id)
            except Exception:
                continue
            all_codes.extend(selection.codes)

        if not all_codes:
            all_codes.extend(market_data_service.list_default_sync_pool_codes())

        return market_data_service._normalize_codes(all_codes)

    def run_daily_automation(self) -> AutomationRunSummary:
        strategy_service = StrategyService(self.session)
        market_data_service = MarketDataService(self.session, self.twstock_client)
        processed_users = 0
        applied_users = 0
        failed_users: list[int] = []
        execution_details: list[dict[str, object]] = []

        for config in self.user_repository.list_enabled_automation_configs():
            processed_users += 1
            try:
                target_codes = market_data_service.resolve_trading_target_codes(user_id=config.user_id)
                succeeded = 0
                for code in target_codes:
                    try:
                        result = strategy_service.run_strategy(
                            code=code,
                            strategy_name=config.strategy_name,
                            user_id=config.user_id,
                            execute_trade=True,
                            position_sizing_mode=config.position_sizing_mode,
                            buy_quantity=config.buy_quantity,
                            cash_allocation_pct=config.cash_allocation_pct,
                            twstock_client=self.twstock_client,
                        )
                        execution_details.append(
                            {
                                "user_id": config.user_id,
                                "code": code,
                                "strategy_name": config.strategy_name,
                                "position_sizing_mode": config.position_sizing_mode,
                                "cash_allocation_pct": config.cash_allocation_pct,
                                "signal": result.signal,
                                "signal_reason": result.signal_reason,
                                "execution": {
                                    "applied": result.execution.applied if result.execution else False,
                                    "action": result.execution.action if result.execution else "NONE",
                                    "quantity": result.execution.quantity if result.execution else 0,
                                    "status": result.execution.status if result.execution else "UNKNOWN",
                                    "message": result.execution.message if result.execution else "Execution result unavailable.",
                                },
                            }
                        )
                        succeeded += 1
                    except StrategyServiceError as exc:
                        execution_details.append(
                            {
                                "user_id": config.user_id,
                                "code": code,
                                "strategy_name": config.strategy_name,
                                "position_sizing_mode": config.position_sizing_mode,
                                "cash_allocation_pct": config.cash_allocation_pct,
                                "signal": "ERROR",
                                "signal_reason": None,
                                "execution": {
                                    "applied": False,
                                    "action": "NONE",
                                    "quantity": 0,
                                    "status": "FAILED",
                                    "message": str(exc),
                                },
                            }
                        )
                        continue
                if succeeded > 0:
                    applied_users += 1
                else:
                    failed_users.append(config.user_id)
            except Exception as exc:
                execution_details.append(
                    {
                        "user_id": config.user_id,
                        "code": None,
                        "strategy_name": config.strategy_name,
                        "position_sizing_mode": config.position_sizing_mode,
                        "cash_allocation_pct": config.cash_allocation_pct,
                        "signal": "ERROR",
                        "signal_reason": None,
                        "execution": {
                            "applied": False,
                            "action": "NONE",
                            "quantity": 0,
                            "status": "FAILED",
                            "message": str(exc),
                        },
                    }
                )
                failed_users.append(config.user_id)

        return AutomationRunSummary(
            processed_users=processed_users,
            applied_users=applied_users,
            failed_users=failed_users,
            execution_details=execution_details,
        )
