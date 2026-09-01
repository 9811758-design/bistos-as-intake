from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final, Protocol, TypeAlias

from receivables_reconciliation.models import DepositNotice, UnparsedDepositNotice
from receivables_reconciliation.outlook_reader import (
    MissingOutlookProfileError,
    OutlookActivationDeniedError,
    OutlookComUnavailableError,
)
from receivables_reconciliation.tracker_models import (
    EntryStatus,
    RefreshResult,
    TaskFilter,
    TaskSnapshot,
)
from receivables_reconciliation.tracker_store import SqliteTaskStore

NoticeCandidate: TypeAlias = DepositNotice | UnparsedDepositNotice
INITIAL_LOOKBACK_DAYS: Final = 90


class OutlookNoticeReader(Protocol):
    def read(
        self,
        start_date: date,
        end_date: date,
    ) -> tuple[NoticeCandidate, ...]: ...


@dataclass(frozen=True, slots=True)
class TrackerPipelineError(Exception):
    stage: str
    detail: str

    def __str__(self) -> str:
        return f"{self.stage} 자료를 읽을 수 없습니다: {self.detail}"


class TrackerService(Protocol):
    def load(self, task_filter: TaskFilter) -> TaskSnapshot: ...

    def refresh(self, task_filter: TaskFilter) -> RefreshResult: ...

    def set_status(
        self,
        message_id: str,
        status: EntryStatus,
        task_filter: TaskFilter,
    ) -> TaskSnapshot: ...

    def set_statuses(
        self,
        message_ids: tuple[str, ...],
        status: EntryStatus,
        task_filter: TaskFilter,
    ) -> TaskSnapshot: ...


class ReceivablesTrackerService:
    def __init__(
        self,
        outlook_reader: OutlookNoticeReader,
        store: SqliteTaskStore,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._outlook_reader = outlook_reader
        self._store = store
        self._today = today

    def load(self, task_filter: TaskFilter) -> TaskSnapshot:
        return TaskSnapshot(self._store.list_tasks(task_filter), self._store.summary())

    def refresh(self, task_filter: TaskFilter) -> RefreshResult:
        end_date = self._today()
        latest = self._store.latest_received_at()
        start_date = (
            latest.date() - timedelta(days=1)
            if latest is not None
            else end_date - timedelta(days=INITIAL_LOOKBACK_DAYS)
        )
        try:
            notices = self._outlook_reader.read(start_date, end_date)
        except (
            MissingOutlookProfileError,
            OutlookActivationDeniedError,
            OutlookComUnavailableError,
        ) as exc:
            raise TrackerPipelineError("Outlook", str(exc)) from exc
        added_count = self._store.upsert_notices(notices)
        return RefreshResult(self.load(task_filter), added_count, len(notices))

    def set_status(
        self,
        message_id: str,
        status: EntryStatus,
        task_filter: TaskFilter,
    ) -> TaskSnapshot:
        self._store.set_status(message_id, status)
        return self.load(task_filter)

    def set_statuses(
        self,
        message_ids: tuple[str, ...],
        status: EntryStatus,
        task_filter: TaskFilter,
    ) -> TaskSnapshot:
        self._store.set_statuses(message_ids, status)
        return self.load(task_filter)
