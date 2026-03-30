from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_twstock_client
from app.schemas.job import (
    HistoryRangeSyncRequest,
    HistoryRangeSyncResponse,
    HistorySyncRequest,
    HistorySyncResponse,
    StockUniverseSyncResponse,
    SyncProgressResponse,
    SyncTargetPreviewResponse,
)
from app.services.sync_progress_service import SyncProgressService
from app.services.market_data_service import MarketDataService, MarketDataServiceError
from app.services.twstock_client import TwStockClient, TwStockClientError

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _raise_database_http_exception(exc: SQLAlchemyError) -> None:
    message = str(exc).lower()
    if "database is locked" in message:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is busy. Please retry the sync in a few seconds.",
        ) from exc
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


def _serialize_default_pool_items(selection) -> list[dict[str, str | None]]:
    return [
        {
            "code": item.code,
            "name": item.name,
            "industry": item.industry,
        }
        for item in selection.default_pool_items
    ]


def _serialize_tradable_pool_items(selection) -> list[dict[str, str | None]]:
    return [
        {
            "code": item.code,
            "name": item.name,
            "industry": item.industry,
        }
        for item in selection.tradable_pool_items
    ]


@router.post("/sync/stocks", response_model=StockUniverseSyncResponse)
def sync_stock_universe(
    run_id: str | None = Query(default=None, min_length=1),
    db: Session = Depends(get_db_session),
    client: TwStockClient = Depends(get_twstock_client),
) -> StockUniverseSyncResponse:
    service = MarketDataService(db, client)
    progress_service = SyncProgressService()
    try:
        synced_count = service.sync_stock_universe(progress_run_id=run_id)
    except SQLAlchemyError as exc:
        db.rollback()
        if run_id:
            progress_service.fail_run(run_id, str(exc))
        _raise_database_http_exception(exc)
    except Exception as exc:
        db.rollback()
        if run_id:
            progress_service.fail_run(run_id, str(exc))
        raise
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
        tradable_pool_codes=selection.tradable_pool_codes,
        tradable_pool_items=_serialize_tradable_pool_items(selection),
    )


@router.post("/sync/history", response_model=HistorySyncResponse)
def sync_history_batch(
    payload: HistorySyncRequest,
    db: Session = Depends(get_db_session),
    client: TwStockClient = Depends(get_twstock_client),
) -> HistorySyncResponse:
    service = MarketDataService(db, client)
    progress_service = SyncProgressService()
    try:
        selection, synced_codes, synced_rows, skipped_codes, failed_codes = service.sync_history_batch(
            codes=payload.codes,
            year=payload.year,
            month=payload.month,
            user_id=payload.user_id,
            progress_run_id=payload.run_id,
        )
    except (TwStockClientError, MarketDataServiceError) as exc:
        db.rollback()
        if payload.run_id:
            progress_service.fail_run(payload.run_id, str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        if payload.run_id:
            progress_service.fail_run(payload.run_id, str(exc))
        _raise_database_http_exception(exc)

    return HistorySyncResponse(
        selection_mode=selection.selection_mode,
        codes=selection.codes,
        watchlist_codes=selection.watchlist_codes,
        default_pool_codes=selection.default_pool_codes,
        default_pool_industries=selection.default_pool_industries,
        default_pool_items=_serialize_default_pool_items(selection),
        tradable_pool_codes=selection.tradable_pool_codes,
        tradable_pool_items=_serialize_tradable_pool_items(selection),
        year=payload.year,
        month=payload.month,
        synced_codes=synced_codes,
        synced_rows=synced_rows,
        skipped_codes=skipped_codes,
        failed_codes=failed_codes,
    )


@router.post("/sync/history-range", response_model=HistoryRangeSyncResponse)
def sync_history_range_batch(
    payload: HistoryRangeSyncRequest,
    db: Session = Depends(get_db_session),
    client: TwStockClient = Depends(get_twstock_client),
) -> HistoryRangeSyncResponse:
    service = MarketDataService(db, client)
    progress_service = SyncProgressService()
    try:
        start_date = date.fromisoformat(payload.start_date)
        end_date = date.fromisoformat(payload.end_date)
        selection, synced_codes, synced_rows, skipped_codes, failed_codes = service.sync_history_range_batch(
            codes=payload.codes,
            start_date=start_date,
            end_date=end_date,
            user_id=payload.user_id,
            progress_run_id=payload.run_id,
        )
    except (TwStockClientError, ValueError, MarketDataServiceError) as exc:
        db.rollback()
        if payload.run_id:
            progress_service.fail_run(payload.run_id, str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        if payload.run_id:
            progress_service.fail_run(payload.run_id, str(exc))
        _raise_database_http_exception(exc)

    return HistoryRangeSyncResponse(
        selection_mode=selection.selection_mode,
        codes=selection.codes,
        watchlist_codes=selection.watchlist_codes,
        default_pool_codes=selection.default_pool_codes,
        default_pool_industries=selection.default_pool_industries,
        default_pool_items=_serialize_default_pool_items(selection),
        tradable_pool_codes=selection.tradable_pool_codes,
        tradable_pool_items=_serialize_tradable_pool_items(selection),
        start_date=payload.start_date,
        end_date=payload.end_date,
        synced_codes=synced_codes,
        synced_rows=synced_rows,
        skipped_codes=skipped_codes,
        failed_codes=failed_codes,
    )


@router.get("/sync/progress/{run_id}", response_model=SyncProgressResponse)
def get_sync_progress(run_id: str) -> SyncProgressResponse:
    state = SyncProgressService().get_run(run_id)
    if state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sync progress not found.")
    return SyncProgressResponse(
        run_id=state.run_id,
        job_name=state.job_name,
        status=state.status,
        total_codes=state.total_codes,
        completed_codes=state.completed_codes,
        synced_codes=state.synced_codes,
        synced_rows=state.synced_rows,
        skipped_codes=state.skipped_codes,
        failed_codes=state.failed_codes,
        current_code=state.current_code,
        started_at=state.started_at,
        finished_at=state.finished_at,
        error_message=state.error_message,
    )
