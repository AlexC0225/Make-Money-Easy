from pydantic import BaseModel, Field


class StockUniverseSyncResponse(BaseModel):
    synced_count: int


class HistorySyncRequest(BaseModel):
    codes: list[str] | None = None
    user_id: int | None = Field(default=None, ge=1)
    year: int = Field(ge=1990, le=2100)
    month: int = Field(ge=1, le=12)


class HistoryRangeSyncRequest(BaseModel):
    codes: list[str] | None = None
    user_id: int | None = Field(default=None, ge=1)
    start_date: str
    end_date: str


class SyncTargetPreviewResponse(BaseModel):
    selection_mode: str
    codes: list[str]
    watchlist_codes: list[str]
    benchmark_codes: list[str]
    source_url: str | None = None
    announce_date: str | None = None
    trade_date: str | None = None


class HistorySyncResponse(SyncTargetPreviewResponse):
    year: int
    month: int
    synced_codes: int
    synced_rows: int
    failed_codes: list[str]


class HistoryRangeSyncResponse(SyncTargetPreviewResponse):
    start_date: str
    end_date: str
    synced_codes: int
    synced_rows: int
    failed_codes: list[str]
