from pydantic import BaseModel, Field


class SyncTargetStockRead(BaseModel):
    code: str
    name: str
    industry: str | None = None


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
    default_pool_codes: list[str]
    default_pool_industries: list[str]
    default_pool_items: list[SyncTargetStockRead] = Field(default_factory=list)


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
