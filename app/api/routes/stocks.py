from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_twstock_client
from app.db.repositories.stock_repository import StockRepository
from app.schemas.stock import (
    HistoricalRangeResponse,
    HistoricalPricesResponse,
    RealtimeQuoteRead,
    StockLookupRead,
    StockRead,
    StockSyncResponse,
)
from app.services.twstock_client import TwStockClient, TwStockClientError

router = APIRouter(prefix="/stocks", tags=["stocks"])


def _history_range_needs_sync(prices: list, start_date: date, end_date: date) -> bool:
    if not prices:
        return True

    # Daily prices only exist on trading days, so weekend or holiday boundaries
    # should not force a full re-sync when cached rows already cover nearby sessions.
    max_boundary_gap_days = 7
    start_gap_days = (prices[0].trade_date - start_date).days
    end_gap_days = (end_date - prices[-1].trade_date).days
    return start_gap_days > max_boundary_gap_days or end_gap_days > max_boundary_gap_days


@router.get("", response_model=list[StockRead])
def list_stocks(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
) -> list[StockRead]:
    repository = StockRepository(db)
    stocks = repository.list_stocks(limit=limit, offset=offset)
    return [StockRead.model_validate(stock) for stock in stocks]


@router.get("/search", response_model=list[StockLookupRead])
def search_stocks(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=10, ge=1, le=20),
    db: Session = Depends(get_db_session),
) -> list[StockLookupRead]:
    repository = StockRepository(db)
    rows = repository.search_stocks(q, limit=limit)
    return [
        StockLookupRead(
            code=stock.code,
            name=stock.name,
            market=stock.market,
            industry=stock.industry,
            latest_price=repository.get_latest_price(stock.id),
        )
        for stock in rows
    ]


@router.get("/{code}/history", response_model=HistoricalPricesResponse)
def get_stock_history(
    code: str,
    year: int = Query(..., ge=1990, le=2100),
    month: int = Query(..., ge=1, le=12),
    client: TwStockClient = Depends(get_twstock_client),
) -> HistoricalPricesResponse:
    try:
        return HistoricalPricesResponse(
            code=code,
            year=year,
            month=month,
            prices=client.get_history(code=code, year=year, month=month),
        )
    except TwStockClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get("/{code}/history-range", response_model=HistoricalRangeResponse)
def get_stock_history_range(
    code: str,
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db_session),
    client: TwStockClient = Depends(get_twstock_client),
) -> HistoricalRangeResponse:
    repository = StockRepository(db)
    stock = repository.get_by_code(code)
    if stock is None:
        metadata = client.get_stock_metadata(code)
        stock = repository.upsert_stock(**metadata)

    prices = repository.get_daily_prices(stock.id, start_date=start_date, end_date=end_date)
    if _history_range_needs_sync(prices, start_date=start_date, end_date=end_date):
        try:
            synced_prices = client.get_history_range(code=code, start_date=start_date, end_date=end_date)
        except TwStockClientError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc

        if not synced_prices:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No historical prices found for this date range.",
            )

        repository.upsert_daily_prices(stock_id=stock.id, prices=synced_prices)
        db.commit()
        prices = repository.get_daily_prices(stock.id, start_date=start_date, end_date=end_date)

    return HistoricalRangeResponse(
        code=code,
        start_date=start_date,
        end_date=end_date,
        prices=[
            {
                "trade_date": price.trade_date,
                "open_price": price.open_price,
                "high_price": price.high_price,
                "low_price": price.low_price,
                "close_price": price.close_price,
                "volume": price.volume,
                "turnover": price.turnover,
                "transaction_count": price.transaction_count,
            }
            for price in prices
        ],
    )


@router.get("/{code}/quote", response_model=RealtimeQuoteRead)
def get_realtime_quote(
    code: str,
    persist: bool = Query(default=False),
    force_refresh: bool = Query(default=False),
    db: Session = Depends(get_db_session),
    client: TwStockClient = Depends(get_twstock_client),
) -> RealtimeQuoteRead:
    try:
        quote = client.get_realtime_quote(code=code, force_refresh=force_refresh)
        if persist:
            repository = StockRepository(db)
            stock = repository.upsert_stock(**client.get_stock_metadata(code))
            repository.save_realtime_quote(stock_id=stock.id, quote=quote)
            db.commit()
        return quote
    except TwStockClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.post("/{code}/sync", response_model=StockSyncResponse)
def sync_stock_history(
    code: str,
    year: int = Query(..., ge=1990, le=2100),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db_session),
    client: TwStockClient = Depends(get_twstock_client),
) -> StockSyncResponse:
    try:
        metadata = client.get_stock_metadata(code)
        history = client.get_history(code=code, year=year, month=month)
    except TwStockClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    repository = StockRepository(db)
    stock = repository.upsert_stock(**metadata)
    synced_count = repository.upsert_daily_prices(stock_id=stock.id, prices=history)
    db.commit()

    return StockSyncResponse(
        code=stock.code,
        name=stock.name,
        year=year,
        month=month,
        synced_count=synced_count,
    )
