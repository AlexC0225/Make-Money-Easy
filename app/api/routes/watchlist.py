from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_twstock_client
from app.schemas.watchlist import WatchlistCreateRequest, WatchlistItemRead
from app.services.twstock_client import TwStockClient
from app.services.watchlist_service import WatchlistService, WatchlistServiceError

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("", response_model=list[WatchlistItemRead])
def list_watchlist(
    user_id: int = Query(..., ge=1),
    db: Session = Depends(get_db_session),
    client: TwStockClient = Depends(get_twstock_client),
) -> list[WatchlistItemRead]:
    return WatchlistService(db, client).list_items(user_id=user_id)


@router.post("", response_model=WatchlistItemRead, status_code=status.HTTP_201_CREATED)
def add_watchlist_item(
    payload: WatchlistCreateRequest,
    db: Session = Depends(get_db_session),
    client: TwStockClient = Depends(get_twstock_client),
) -> WatchlistItemRead:
    service = WatchlistService(db, client)
    try:
        item = service.add_item(user_id=payload.user_id, code=payload.code, note=payload.note)
        db.commit()
        return item
    except WatchlistServiceError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/{code}", status_code=status.HTTP_204_NO_CONTENT)
def remove_watchlist_item(
    code: str,
    user_id: int = Query(..., ge=1),
    db: Session = Depends(get_db_session),
    client: TwStockClient = Depends(get_twstock_client),
) -> None:
    service = WatchlistService(db, client)
    try:
        service.remove_item(user_id=user_id, code=code)
        db.commit()
    except WatchlistServiceError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
