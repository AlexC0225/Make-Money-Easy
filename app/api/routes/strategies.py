from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_twstock_client
from app.schemas.strategy import (
    AutomationConfigRead,
    AutomationConfigUpdateRequest,
    StrategyDefinitionRead,
    StrategyRunRequest,
    StrategySignalRead,
)
from app.services.automation_service import AutomationService, AutomationServiceError
from app.services.strategy_service import StrategyService, StrategyServiceError
from app.services.twstock_client import TwStockClient

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("/catalog", response_model=list[StrategyDefinitionRead])
def list_strategy_catalog(
    db: Session = Depends(get_db_session),
) -> list[StrategyDefinitionRead]:
    return StrategyService(db).list_strategy_definitions()


@router.post("/run", response_model=StrategySignalRead)
def run_strategy(
    payload: StrategyRunRequest,
    db: Session = Depends(get_db_session),
    client: TwStockClient = Depends(get_twstock_client),
) -> StrategySignalRead:
    service = StrategyService(db)
    try:
        result = service.run_strategy(
            code=payload.code.strip(),
            strategy_name=payload.strategy_name,
            user_id=payload.user_id,
            execute_trade=payload.execute_trade,
            position_sizing_mode=payload.position_sizing_mode,
            buy_quantity=payload.buy_quantity,
            cash_allocation_pct=payload.cash_allocation_pct,
            twstock_client=client,
        )
        db.commit()
        return result
    except StrategyServiceError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/automation/{user_id}", response_model=AutomationConfigRead)
def get_automation_config(
    user_id: int,
    db: Session = Depends(get_db_session),
    client: TwStockClient = Depends(get_twstock_client),
) -> AutomationConfigRead:
    service = AutomationService(db, client)
    try:
        config = service.get_or_create_config(user_id)
        db.commit()
        return config
    except AutomationServiceError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("/automation/{user_id}", response_model=AutomationConfigRead)
def update_automation_config(
    user_id: int,
    payload: AutomationConfigUpdateRequest,
    db: Session = Depends(get_db_session),
    client: TwStockClient = Depends(get_twstock_client),
) -> AutomationConfigRead:
    service = AutomationService(db, client)
    try:
        config = service.update_config(user_id, payload)
        db.commit()
        return config
    except AutomationServiceError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/signals", response_model=list[StrategySignalRead])
def list_signals(
    strategy_name: str | None = Query(default=None),
    industry: str | None = Query(default=None),
    latest_only: bool = Query(default=False),
    limit: int | None = Query(default=None, ge=1, le=1000),
    db: Session = Depends(get_db_session),
) -> list[StrategySignalRead]:
    service = StrategyService(db)
    return service.list_signals(
        strategy_name=strategy_name,
        industry=industry,
        latest_only=latest_only,
        limit=limit,
    )
