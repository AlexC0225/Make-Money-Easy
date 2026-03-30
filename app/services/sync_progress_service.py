from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock


@dataclass(slots=True)
class SyncProgressState:
    run_id: str
    job_name: str
    status: str
    total_codes: int
    completed_codes: int = 0
    synced_codes: int = 0
    synced_rows: int = 0
    failed_codes: list[str] = field(default_factory=list)
    current_code: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    error_message: str | None = None


class SyncProgressService:
    _states: dict[str, SyncProgressState] = {}
    _lock = Lock()

    def start_run(self, run_id: str, job_name: str, total_codes: int) -> SyncProgressState:
        state = SyncProgressState(
            run_id=run_id,
            job_name=job_name,
            status="running",
            total_codes=total_codes,
        )
        with self._lock:
            self._states[run_id] = state
        return deepcopy(state)

    def set_current_code(self, run_id: str, code: str | None) -> SyncProgressState | None:
        with self._lock:
            state = self._states.get(run_id)
            if state is None:
                return None
            state.current_code = code
            return deepcopy(state)

    def mark_code_success(self, run_id: str, code: str | None, synced_rows: int = 0) -> SyncProgressState | None:
        with self._lock:
            state = self._states.get(run_id)
            if state is None:
                return None
            state.current_code = code
            state.completed_codes += 1
            state.synced_codes += 1
            state.synced_rows += synced_rows
            return deepcopy(state)

    def mark_code_failure(self, run_id: str, code: str | None, error_message: str | None = None) -> SyncProgressState | None:
        with self._lock:
            state = self._states.get(run_id)
            if state is None:
                return None
            state.current_code = code
            state.completed_codes += 1
            if code and code not in state.failed_codes:
                state.failed_codes.append(code)
            if error_message:
                state.error_message = error_message
            return deepcopy(state)

    def complete_run(self, run_id: str) -> SyncProgressState | None:
        with self._lock:
            state = self._states.get(run_id)
            if state is None:
                return None
            state.status = "completed"
            state.finished_at = datetime.now(timezone.utc)
            state.current_code = None
            return deepcopy(state)

    def fail_run(self, run_id: str, error_message: str) -> SyncProgressState | None:
        with self._lock:
            state = self._states.get(run_id)
            if state is None:
                return None
            state.status = "failed"
            state.error_message = error_message
            state.finished_at = datetime.now(timezone.utc)
            return deepcopy(state)

    def get_run(self, run_id: str) -> SyncProgressState | None:
        with self._lock:
            state = self._states.get(run_id)
            return deepcopy(state) if state is not None else None
