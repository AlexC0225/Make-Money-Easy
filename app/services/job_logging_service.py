import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.config import get_settings


class JobLoggingService:
    JOB_METADATA: dict[str, dict[str, str]] = {
        "run-daily-workspace-automation": {
            "task_name": "Daily workspace automation",
            "task_description": "Evaluate automation rules and apply resulting trade actions to each workspace.",
        },
        "sync-stock-universe": {
            "task_name": "Sync stock universe",
            "task_description": "Refresh the stock universe so the local database matches the latest supported symbols.",
        },
        "sync-workspace-close-data": {
            "task_name": "Sync workspace close data",
            "task_description": "Update close-price history for the symbols required by workspace automation.",
        },
    }

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
        serialized_payload = self._serialize(payload or {})
        record = self._build_record(
            job_name=job_name,
            status=status,
            event=event,
            timestamp=timestamp,
            payload=serialized_payload,
        )
        target = self.log_dir / f"jobs-{timestamp.date().isoformat()}.log"
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")
        return target

    def _build_record(
        self,
        job_name: str,
        status: str,
        event: str,
        timestamp: datetime,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        task_name, task_description = self._resolve_task_metadata(job_name)
        return {
            "timestamp": timestamp.isoformat(),
            "time": {
                "date": timestamp.date().isoformat(),
                "time": timestamp.strftime("%H:%M:%S"),
                "timezone": self.timezone.key,
            },
            "job_name": job_name,
            "task_name": task_name,
            "task_description": task_description,
            "event": event,
            "status": status,
            "summary": self._build_summary(job_name=job_name, status=status, event=event, payload=payload),
            "updates": self._build_updates(job_name=job_name, status=status, event=event, payload=payload),
            "completion": {
                "finished": status != "RUNNING",
                "successful": status == "SUCCESS",
            },
            "payload": payload,
        }

    def _resolve_task_metadata(self, job_name: str) -> tuple[str, str]:
        metadata = self.JOB_METADATA.get(job_name)
        if metadata is not None:
            return metadata["task_name"], metadata["task_description"]
        fallback_name = job_name.replace("-", " ").strip().title()
        fallback_description = f"Execute the `{job_name}` background job."
        return fallback_name, fallback_description

    def _build_summary(
        self,
        job_name: str,
        status: str,
        event: str,
        payload: dict[str, Any],
    ) -> str:
        if status == "RUNNING" or event == "started":
            return "Task started."

        if status == "FAILED":
            error = payload.get("error")
            if error:
                return f"Task failed: {error}"
            return "Task failed."

        if status == "SKIPPED":
            reason = payload.get("reason")
            if reason:
                return f"Task skipped: {reason}"
            return "Task skipped."

        if job_name == "run-daily-workspace-automation":
            processed_users = payload.get("processed_users", 0)
            applied_users = payload.get("applied_users", 0)
            return (
                "Task completed. "
                f"Processed {processed_users} workspace users and applied automation for {applied_users} users."
            )

        if job_name == "sync-stock-universe":
            synced_count = payload.get("synced_count", 0)
            return f"Task completed. Synced {synced_count} stock records."

        if job_name == "sync-workspace-close-data":
            synced_codes = payload.get("synced_codes", 0)
            synced_rows = payload.get("synced_rows", 0)
            return (
                "Task completed. "
                f"Synced close data for {synced_codes} symbols and {synced_rows} daily rows."
            )

        return "Task completed."

    def _build_updates(
        self,
        job_name: str,
        status: str,
        event: str,
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if status == "RUNNING" or event == "started":
            return [{"label": "state", "value": "started"}]

        updates: list[dict[str, Any]] = []

        if job_name == "run-daily-workspace-automation":
            self._append_if_present(updates, "processed_users", payload, "processed_users")
            self._append_if_present(updates, "applied_users", payload, "applied_users")
            self._append_if_present(updates, "failed_users", payload, "failed_users")

            execution_details = payload.get("execution_details")
            if isinstance(execution_details, list):
                execution_statuses = {
                    "total": len(execution_details),
                    "applied": 0,
                    "skipped": 0,
                    "failed": 0,
                }
                for detail in execution_details:
                    execution = detail.get("execution", {}) if isinstance(detail, dict) else {}
                    status_name = execution.get("status")
                    if status_name == "APPLIED":
                        execution_statuses["applied"] += 1
                    elif status_name == "FAILED":
                        execution_statuses["failed"] += 1
                    else:
                        execution_statuses["skipped"] += 1
                updates.append({"label": "execution_summary", "value": execution_statuses})

        if job_name == "sync-stock-universe":
            self._append_if_present(updates, "synced_count", payload, "synced_count")

        if job_name == "sync-workspace-close-data":
            if "year" in payload and "month" in payload:
                updates.append(
                    {
                        "label": "target_period",
                        "value": {
                            "year": payload["year"],
                            "month": payload["month"],
                        },
                    }
                )

            codes = payload.get("codes")
            if isinstance(codes, list):
                updates.append(
                    {
                        "label": "requested_codes",
                        "value": {
                            "count": len(codes),
                            "sample": codes[:10],
                        },
                    }
                )

            self._append_if_present(updates, "synced_codes", payload, "synced_codes")
            self._append_if_present(updates, "synced_rows", payload, "synced_rows")

            skipped_codes = payload.get("skipped_codes")
            if isinstance(skipped_codes, list):
                updates.append(
                    {
                        "label": "skipped_codes",
                        "value": {
                            "count": len(skipped_codes),
                            "codes": skipped_codes[:10],
                        },
                    }
                )

            failed_codes = payload.get("failed_codes")
            if isinstance(failed_codes, list):
                updates.append(
                    {
                        "label": "failed_codes",
                        "value": {
                            "count": len(failed_codes),
                            "codes": failed_codes[:10],
                        },
                    }
                )

        if "reason" in payload:
            updates.append({"label": "reason", "value": payload["reason"]})
        if "error" in payload:
            updates.append({"label": "error", "value": payload["error"]})

        return updates

    def _append_if_present(
        self,
        updates: list[dict[str, Any]],
        label: str,
        payload: dict[str, Any],
        key: str,
    ) -> None:
        if key in payload:
            updates.append({"label": label, "value": payload[key]})

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
