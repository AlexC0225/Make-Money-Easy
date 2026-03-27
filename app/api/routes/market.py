from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.schemas.market import MarketOverviewRead
from app.services.market_service import MarketService, MarketServiceError

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/overview", response_model=MarketOverviewRead)
def get_market_overview(
    limit: int = Query(default=10, ge=1, le=20),
    db: Session = Depends(get_db_session),
) -> MarketOverviewRead:
    service = MarketService(db)
    try:
        return service.get_market_overview(limit=limit)
    except MarketServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
