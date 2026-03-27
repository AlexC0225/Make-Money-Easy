from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate


class UserServiceError(Exception):
    pass


class UserService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.user_repository = UserRepository(session)

    def create_user(self, payload: UserCreate):
        existing_user = self.user_repository.get_by_identity(payload.username, payload.email)
        if existing_user is not None:
            raise UserServiceError("Username or email already exists.")

        user = self.user_repository.create_user(
            username=payload.username,
            email=payload.email,
            hashed_password=hash_password(f"passwordless::{payload.username}::{payload.email}"),
        )
        self.user_repository.create_account(user_id=user.id, initial_cash=payload.initial_cash)
        self.session.flush()
        self.session.refresh(user)
        return user

    def authenticate(self, login: str):
        user = self.user_repository.get_by_login(login)
        if user is None:
            raise UserServiceError("User not found.")
        return user
