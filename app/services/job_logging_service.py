import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.config import get_settings


class JobLoggingService:
    def __init__(self, log_dir: str | None = None, timezone: str | None = None) -> None:
        settings = get_settings()
        self.timezone = ZoneInfo(timezone or settings.scheduler_timezone)
        configured_dir = log_dir or settings.job_log_dir
        self.log_dir = Path(configured_dir)
        if not self.log_dir.is_absolute():
            self.log_dir = Path.cwd() / self.log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def log_event(
        self,
        job_name: str,
        status: str,
        payload: dict[str, Any] | None = None,
        event: str = "completed",
        occurred_at: datetime | None = None,
    ) -> Path:
        timestamp = self._normalize_datetime(occurred_at)
        record = {
            "timestamp": timestamp.isoformat(),
            "job_name": job_name,
            "event": event,
            "status": status,
            "payload": self._serialize(payload or {}),
        }
        target = self.log_dir / f"jobs-{timestamp.date().isoformat()}.log"
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")
        return target

    def _normalize_datetime(self, value: datetime | None) -> datetime:
        if value is None:
            return datetime.now(self.timezone)
        if value.tzinfo is None:
            return value.replace(tzinfo=self.timezone)
        return value.astimezone(self.timezone)

    def _serialize(self, value: Any) -> Any:
        if is_dataclass(value):
            return self._serialize(asdict(value))
        if isinstance(value, dict):
            return {str(key): self._serialize(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._serialize(item) for item in value]
        if isinstance(value, datetime):
            return self._normalize_datetime(value).isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, Path):
            return str(value)
        return value
