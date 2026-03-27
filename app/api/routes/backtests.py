from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.schemas.strategy import BacktestResultRead, BacktestRunRequest
from app.services.backtest_service import BacktestService, BacktestServiceError, BacktestSpec

router = APIRouter(prefix="/backtests", tags=["backtests"])


@router.post("/run", response_model=BacktestResultRead, status_code=status.HTTP_201_CREATED)
def run_backtest(
    payload: BacktestRunRequest,
    db: Session = Depends(get_db_session),
) -> BacktestResultRead:
    service = BacktestService(db)
    try:
        result = service.run_backtest(
            BacktestSpec(
                code=payload.code.strip(),
                strategy_name=payload.strategy_name,
                start_date=payload.start_date,
                end_date=payload.end_date,
                initial_cash=payload.initial_cash,
                lot_size=payload.lot_size,
            )
        )
        db.commit()
        return result
    except BacktestServiceError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{result_id}", response_model=BacktestResultRead)
def get_backtest_result(
    result_id: int,
    db: Session = Depends(get_db_session),
) -> BacktestResultRead:
    service = BacktestService(db)
    try:
        return service.get_backtest_result(result_id)
    except BacktestServiceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("", response_model=list[BacktestResultRead])
def list_backtest_results(
    limit: int = 20,
    db: Session = Depends(get_db_session),
) -> list[BacktestResultRead]:
    return BacktestService(db).list_backtest_results(limit=limit)
