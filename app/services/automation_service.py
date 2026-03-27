from dataclasses import dataclass

from app.db.repositories.user_repository import UserRepository
from app.schemas.strategy import AutomationConfigRead, AutomationConfigUpdateRequest
from app.services.etf_constituent_service import EtfConstituentService
from app.services.market_data_service import MarketDataService
from app.services.strategy_service import StrategyService, StrategyServiceError
from app.services.twstock_client import TwStockClient


class AutomationServiceError(Exception):
    pass


@dataclass
class AutomationRunSummary:
    processed_users: int
    applied_users: int
    failed_users: list[int]


class AutomationService:
    def __init__(self, session, twstock_client: TwStockClient, constituent_service: EtfConstituentService) -> None:
        self.session = session
        self.twstock_client = twstock_client
        self.constituent_service = constituent_service
        self.user_repository = UserRepository(session)

    def get_or_create_config(self, user_id: int) -> AutomationConfigRead:
        user = self.user_repository.get_user(user_id)
        if user is None:
            raise AutomationServiceError("User not found.")

        config = self.user_repository.get_automation_config_by_user_id(user_id)
        if config is None:
            config = self.user_repository.upsert_automation_config(
                user_id=user_id,
                strategy_name="connors_rsi2_long",
                buy_quantity=1000,
                enabled=True,
            )

        return AutomationConfigRead(
            user_id=config.user_id,
            enabled=config.enabled,
            strategy_name=config.strategy_name,
            buy_quantity=config.buy_quantity,
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
            buy_quantity=payload.buy_quantity,
        )
        return AutomationConfigRead(
            user_id=config.user_id,
            enabled=config.enabled,
            strategy_name=config.strategy_name,
            buy_quantity=config.buy_quantity,
            updated_at=config.updated_at,
        )

    def resolve_daily_sync_codes(self) -> list[str]:
        market_data_service = MarketDataService(self.session, self.twstock_client, self.constituent_service)
        all_codes: list[str] = []
        for user in self.user_repository.list_users():
            try:
                selection = market_data_service.resolve_sync_targets(codes=None, user_id=user.id)
            except Exception:
                continue
            all_codes.extend(selection.codes)

        if not all_codes:
            snapshot = self.constituent_service.get_0050_constituents()
            all_codes.extend(snapshot.codes)

        return market_data_service._normalize_codes(all_codes)

    def run_daily_automation(self) -> AutomationRunSummary:
        strategy_service = StrategyService(self.session)
        market_data_service = MarketDataService(self.session, self.twstock_client, self.constituent_service)
        processed_users = 0
        applied_users = 0
        failed_users: list[int] = []

        for config in self.user_repository.list_enabled_automation_configs():
            processed_users += 1
            try:
                selection = market_data_service.resolve_sync_targets(codes=None, user_id=config.user_id)
                succeeded = 0
                for code in selection.codes:
                    try:
                        strategy_service.run_strategy(
                            code=code,
                            strategy_name=config.strategy_name,
                            user_id=config.user_id,
                            execute_trade=True,
                            buy_quantity=config.buy_quantity,
                            twstock_client=self.twstock_client,
                        )
                        succeeded += 1
                    except StrategyServiceError:
                        continue
                if succeeded > 0:
                    applied_users += 1
                else:
                    failed_users.append(config.user_id)
            except Exception:
                failed_users.append(config.user_id)

        return AutomationRunSummary(
            processed_users=processed_users,
            applied_users=applied_users,
            failed_users=failed_users,
        )
