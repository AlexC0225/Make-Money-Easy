from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.schemas.user import UserCreate, UserLoginRequest, UserLoginResponse, UserWithAccountRead
from app.services.portfolio_service import PortfolioService
from app.services.user_service import UserService, UserServiceError

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserWithAccountRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db_session),
) -> UserWithAccountRead:
    service = UserService(db)
    try:
        user = service.create_user(payload)
        db.commit()
        db.refresh(user)
    except UserServiceError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return UserWithAccountRead.model_validate(user)


@router.post("/login", response_model=UserLoginResponse)
def login_user(
    payload: UserLoginRequest,
    db: Session = Depends(get_db_session),
) -> UserLoginResponse:
    service = UserService(db)
    try:
        user = service.authenticate(payload.login)
    except UserServiceError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    return UserLoginResponse(
        user=UserWithAccountRead.model_validate(user),
        active_user_id=user.id,
    )


@router.get("/{user_id}", response_model=UserWithAccountRead)
def get_user(
    user_id: int,
    db: Session = Depends(get_db_session),
) -> UserWithAccountRead:
    service = PortfolioService(db)
    try:
        account = service._get_account(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    user = account.user
    return UserWithAccountRead.model_validate(user)
