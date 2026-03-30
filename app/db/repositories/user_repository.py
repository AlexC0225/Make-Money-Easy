from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models.automation import AutomationConfig
from app.db.models.user import Account, User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_user(self, user_id: int) -> User | None:
        statement = select(User).where(User.id == user_id)
        return self.session.scalar(statement)

    def list_users(self) -> list[User]:
        statement = select(User).order_by(User.id.asc())
        return list(self.session.scalars(statement))

    def get_single_user(self) -> User | None:
        statement = select(User).order_by(User.id.asc()).limit(1)
        return self.session.scalar(statement)

    def get_by_identity(self, username: str, email: str) -> User | None:
        statement = select(User).where(or_(User.username == username, User.email == email))
        return self.session.scalar(statement)

    def get_by_login(self, login: str) -> User | None:
        statement = select(User).where(or_(User.username == login, User.email == login))
        return self.session.scalar(statement)

    def create_user(self, username: str, email: str, hashed_password: str) -> User:
        user = User(username=username, email=email, hashed_password=hashed_password)
        self.session.add(user)
        self.session.flush()
        return user

    def create_account(self, user_id: int, initial_cash: float) -> Account:
        account = Account(
            user_id=user_id,
            initial_cash=initial_cash,
            available_cash=initial_cash,
            frozen_cash=0,
            market_value=0,
            total_equity=initial_cash,
        )
        self.session.add(account)
        self.session.flush()
        return account

    def get_account_by_user_id(self, user_id: int) -> Account | None:
        statement = select(Account).where(Account.user_id == user_id)
        return self.session.scalar(statement)

    def get_automation_config_by_user_id(self, user_id: int) -> AutomationConfig | None:
        statement = select(AutomationConfig).where(AutomationConfig.user_id == user_id)
        return self.session.scalar(statement)

    def list_enabled_automation_configs(self) -> list[AutomationConfig]:
        statement = (
            select(AutomationConfig)
            .where(AutomationConfig.enabled.is_(True))
            .order_by(AutomationConfig.user_id.asc(), AutomationConfig.id.asc())
        )
        return list(self.session.scalars(statement))

    def upsert_automation_config(
        self,
        user_id: int,
        strategy_name: str,
        position_sizing_mode: str,
        buy_quantity: int,
        cash_allocation_pct: float,
        enabled: bool = True,
    ) -> AutomationConfig:
        config = self.get_automation_config_by_user_id(user_id)
        if config is None:
            config = AutomationConfig(
                user_id=user_id,
                enabled=enabled,
                strategy_name=strategy_name,
                position_sizing_mode=position_sizing_mode,
                buy_quantity=buy_quantity,
                cash_allocation_pct=cash_allocation_pct,
            )
            self.session.add(config)
            self.session.flush()
            return config

        config.enabled = enabled
        config.strategy_name = strategy_name
        config.position_sizing_mode = position_sizing_mode
        config.buy_quantity = buy_quantity
        config.cash_allocation_pct = cash_allocation_pct
        self.session.flush()
        return config
