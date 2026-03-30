from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_twstock_client
from app.schemas.portfolio import (
    PortfolioBootstrapRequest,
    PortfolioBootstrapResponse,
    PortfolioSummaryRead,
    PositionRead,
    TradeRead,
)
from app.services.portfolio_service import PortfolioService
from app.services.order_service import OrderService
from app.services.twstock_client import TwStockClient

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.post("/bootstrap", response_model=PortfolioBootstrapResponse)
def bootstrap_portfolio(
    payload: PortfolioBootstrapRequest,
    db: Session = Depends(get_db_session),
    client: TwStockClient = Depends(get_twstock_client),
) -> PortfolioBootstrapResponse:
    service = PortfolioService(db)
    try:
        result = service.bootstrap_portfolio(payload, client)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return result


@router.get("", response_model=PortfolioSummaryRead)
def get_portfolio_summary(
    user_id: int = Query(..., ge=1),
    db: Session = Depends(get_db_session),
) -> PortfolioSummaryRead:
    service = PortfolioService(db)
    try:
        return service.get_summary(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/positions", response_model=list[PositionRead])
def list_positions(
    user_id: int = Query(..., ge=1),
    include_closed: bool = Query(default=False),
    db: Session = Depends(get_db_session),
) -> list[PositionRead]:
    service = PortfolioService(db)
    try:
        return service.list_positions(user_id=user_id, include_closed=include_closed)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/trades", response_model=list[TradeRead])
def list_trades(
    user_id: int = Query(..., ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db_session),
    client: TwStockClient = Depends(get_twstock_client),
) -> list[TradeRead]:
    trades = OrderService(db, client).list_trades(user_id=user_id)
    return [
        TradeRead(
            id=trade.id,
            order_id=trade.order_id,
            stock_code=trade.stock.code,
            stock_name=trade.stock.name,
            side=trade.side,
            fill_price=trade.fill_price,
            fill_quantity=trade.fill_quantity,
            fee=trade.fee,
            tax=trade.tax,
            executed_at=trade.executed_at,
        )
        for trade in trades[:limit]
    ]
