from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_twstock_client
from app.schemas.job import (
    HistoryRangeSyncRequest,
    HistoryRangeSyncResponse,
    HistorySyncRequest,
    HistorySyncResponse,
    StockUniverseSyncResponse,
    SyncTargetPreviewResponse,
)
from app.services.market_data_service import MarketDataService, MarketDataServiceError
from app.services.twstock_client import TwStockClient, TwStockClientError

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _serialize_default_pool_items(selection) -> list[dict[str, str | None]]:
    return [
        {
            "code": item.code,
            "name": item.name,
            "industry": item.industry,
        }
        for item in selection.default_pool_items
    ]


@router.post("/sync/stocks", response_model=StockUniverseSyncResponse)
def sync_stock_universe(
    db: Session = Depends(get_db_session),
    client: TwStockClient = Depends(get_twstock_client),
) -> StockUniverseSyncResponse:
    service = MarketDataService(db, client)
    synced_count = service.sync_stock_universe()
    db.commit()
    return StockUniverseSyncResponse(synced_count=synced_count)


@router.get("/sync/targets", response_model=SyncTargetPreviewResponse)
def get_sync_targets(
    user_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db_session),
    client: TwStockClient = Depends(get_twstock_client),
) -> SyncTargetPreviewResponse:
    service = MarketDataService(db, client)
    try:
        selection = service.resolve_sync_targets(codes=None, user_id=user_id)
    except MarketDataServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return SyncTargetPreviewResponse(
        selection_mode=selection.selection_mode,
        codes=selection.codes,
        watchlist_codes=selection.watchlist_codes,
        default_pool_codes=selection.default_pool_codes,
        default_pool_industries=selection.default_pool_industries,
        default_pool_items=_serialize_default_pool_items(selection),
    )


@router.post("/sync/history", response_model=HistorySyncResponse)
def sync_history_batch(
    payload: HistorySyncRequest,
    db: Session = Depends(get_db_session),
    client: TwStockClient = Depends(get_twstock_client),
) -> HistorySyncResponse:
    service = MarketDataService(db, client)
    try:
        selection, synced_codes, synced_rows, failed_codes = service.sync_history_batch(
            codes=payload.codes,
            year=payload.year,
            month=payload.month,
            user_id=payload.user_id,
        )
        db.commit()
    except (TwStockClientError, MarketDataServiceError) as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return HistorySyncResponse(
        selection_mode=selection.selection_mode,
        codes=selection.codes,
        watchlist_codes=selection.watchlist_codes,
        default_pool_codes=selection.default_pool_codes,
        default_pool_industries=selection.default_pool_industries,
        default_pool_items=_serialize_default_pool_items(selection),
        year=payload.year,
        month=payload.month,
        synced_codes=synced_codes,
        synced_rows=synced_rows,
        failed_codes=failed_codes,
    )


@router.post("/sync/history-range", response_model=HistoryRangeSyncResponse)
def sync_history_range_batch(
    payload: HistoryRangeSyncRequest,
    db: Session = Depends(get_db_session),
    client: TwStockClient = Depends(get_twstock_client),
) -> HistoryRangeSyncResponse:
    service = MarketDataService(db, client)
    try:
        start_date = date.fromisoformat(payload.start_date)
        end_date = date.fromisoformat(payload.end_date)
        selection, synced_codes, synced_rows, failed_codes = service.sync_history_range_batch(
            codes=payload.codes,
            start_date=start_date,
            end_date=end_date,
            user_id=payload.user_id,
        )
        db.commit()
    except (TwStockClientError, ValueError, MarketDataServiceError) as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return HistoryRangeSyncResponse(
        selection_mode=selection.selection_mode,
        codes=selection.codes,
        watchlist_codes=selection.watchlist_codes,
        default_pool_codes=selection.default_pool_codes,
        default_pool_industries=selection.default_pool_industries,
        default_pool_items=_serialize_default_pool_items(selection),
        start_date=payload.start_date,
        end_date=payload.end_date,
        synced_codes=synced_codes,
        synced_rows=synced_rows,
        failed_codes=failed_codes,
    )
