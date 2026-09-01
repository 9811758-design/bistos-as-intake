from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pytest

from receivables_reconciliation.models import DepositNotice, UnparsedDepositNotice
from receivables_reconciliation.outlook_reader import OutlookComUnavailableError
from receivables_reconciliation.tracker_models import EntryStatus, TaskFilter
from receivables_reconciliation.tracker_service import (
    ReceivablesTrackerService,
    TrackerPipelineError,
)
from receivables_reconciliation.tracker_store import SqliteTaskStore


@dataclass(frozen=True, slots=True)
class RecordingReader:
    notices: tuple[DepositNotice | UnparsedDepositNotice, ...]
    calls: list[tuple[date, date]]

    def read(
        self,
        start_date: date,
        end_date: date,
    ) -> tuple[DepositNotice | UnparsedDepositNotice, ...]:
        self.calls.append((start_date, end_date))
        return self.notices


@dataclass(frozen=True, slots=True)
class FailingReader:
    def read(
        self,
        start_date: date,
        end_date: date,
    ) -> tuple[DepositNotice | UnparsedDepositNotice, ...]:
        raise OutlookComUnavailableError("classic COM unavailable")


def _notice(message_id: str, received_at: datetime) -> DepositNotice:
    return DepositNotice(
        message_id=message_id,
        deposit_date=received_at.date(),
        depositor_name="장진영",
        amount=150_000,
        subject="국내입금",
        received_at=received_at,
    )


def test_refresh_reads_initial_lookback_and_returns_new_task_count(tmp_path: Path) -> None:
    # Given
    reader = RecordingReader((_notice("new", datetime(2026, 8, 24, 9, 0)),), [])
    service = ReceivablesTrackerService(
        reader,
        SqliteTaskStore(tmp_path / "tasks.db"),
        today=lambda: date(2026, 8, 24),
    )

    # When
    result = service.refresh(TaskFilter.ALL)

    # Then
    assert reader.calls == [(date(2026, 5, 26), date(2026, 8, 24))]
    assert result.added_count == 1
    assert result.snapshot.summary.pending_count == 1


def test_refresh_uses_latest_saved_mail_for_incremental_scan(tmp_path: Path) -> None:
    # Given
    store = SqliteTaskStore(tmp_path / "tasks.db")
    store.upsert_notices((_notice("saved", datetime(2026, 8, 20, 9, 0)),))
    reader = RecordingReader((), [])
    service = ReceivablesTrackerService(
        reader,
        store,
        today=lambda: date(2026, 8, 24),
    )

    # When
    service.refresh(TaskFilter.ALL)

    # Then
    assert reader.calls == [(date(2026, 8, 19), date(2026, 8, 24))]


def test_set_status_updates_snapshot_counts_and_filter(tmp_path: Path) -> None:
    # Given
    store = SqliteTaskStore(tmp_path / "tasks.db")
    store.upsert_notices((_notice("mail-1", datetime(2026, 8, 24, 9, 0)),))
    service = ReceivablesTrackerService(
        RecordingReader((), []),
        store,
        today=lambda: date(2026, 8, 24),
    )

    # When
    snapshot = service.set_status("mail-1", EntryStatus.COMPLETED, TaskFilter.COMPLETED)

    # Then
    assert snapshot.summary.completed_count == 1
    assert tuple(task.message_id for task in snapshot.tasks) == ("mail-1",)


def test_set_statuses_updates_multiple_tasks_in_one_snapshot(tmp_path: Path) -> None:
    # Given
    store = SqliteTaskStore(tmp_path / "tasks.db")
    store.upsert_notices(
        (
            _notice("mail-1", datetime(2026, 8, 24, 9, 0)),
            _notice("mail-2", datetime(2026, 8, 24, 10, 0)),
        )
    )
    service = ReceivablesTrackerService(
        RecordingReader((), []),
        store,
        today=lambda: date(2026, 8, 24),
    )

    # When
    snapshot = service.set_statuses(
        ("mail-1", "mail-2"), EntryStatus.COMPLETED, TaskFilter.COMPLETED
    )

    # Then
    assert snapshot.summary.completed_count == 2
    assert tuple(task.message_id for task in snapshot.tasks) == ("mail-2", "mail-1")


def test_refresh_keeps_saved_tasks_when_outlook_fails(tmp_path: Path) -> None:
    # Given
    store = SqliteTaskStore(tmp_path / "tasks.db")
    store.upsert_notices((_notice("saved", datetime(2026, 8, 24, 9, 0)),))
    service = ReceivablesTrackerService(
        FailingReader(),
        store,
        today=lambda: date(2026, 8, 24),
    )

    # When
    # Then
    with pytest.raises(TrackerPipelineError, match="Outlook"):
        service.refresh(TaskFilter.ALL)
    assert service.load(TaskFilter.ALL).summary.total_count == 1
