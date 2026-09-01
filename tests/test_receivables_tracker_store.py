from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

import pytest

from receivables_reconciliation.models import DepositNotice, UnparsedDepositNotice
from receivables_reconciliation.tracker_models import EntryStatus, TaskFilter
from receivables_reconciliation.tracker_store import MissingTaskError, SqliteTaskStore


def _notice(message_id: str = "mail-1") -> DepositNotice:
    return DepositNotice(
        message_id=message_id,
        deposit_date=date(2026, 8, 24),
        depositor_name="장진영",
        amount=150_000,
        bank_name="기업018(원화)",
        subject="8/24 국내입금",
        received_at=datetime(2026, 8, 24, 9, 30),
    )


def test_store_persists_task_status_across_instances(tmp_path: Path) -> None:
    # Given
    database_path = tmp_path / "tasks.db"
    store = SqliteTaskStore(database_path)
    store.upsert_notices((_notice(),))

    # When
    store.set_status("mail-1", EntryStatus.COMPLETED)
    reopened = SqliteTaskStore(database_path)

    # Then
    assert reopened.list_tasks(TaskFilter.ALL)[0].status is EntryStatus.COMPLETED


def test_store_deduplicates_repeated_outlook_message_and_preserves_status(tmp_path: Path) -> None:
    # Given
    store = SqliteTaskStore(tmp_path / "tasks.db")
    store.upsert_notices((_notice(),))
    store.set_status("mail-1", EntryStatus.COMPLETED)

    # When
    added_count = store.upsert_notices((_notice(), _notice()))

    # Then
    tasks = store.list_tasks(TaskFilter.ALL)
    assert added_count == 0
    assert len(tasks) == 1
    assert tasks[0].status is EntryStatus.COMPLETED


def test_store_filters_pending_and_completed_tasks(tmp_path: Path) -> None:
    # Given
    store = SqliteTaskStore(tmp_path / "tasks.db")
    store.upsert_notices((_notice("pending"), _notice("completed")))
    store.set_status("completed", EntryStatus.COMPLETED)

    # When
    pending = store.list_tasks(TaskFilter.PENDING)
    completed = store.list_tasks(TaskFilter.COMPLETED)

    # Then
    assert tuple(task.message_id for task in pending) == ("pending",)
    assert tuple(task.message_id for task in completed) == ("completed",)


def test_store_updates_multiple_statuses_atomically(tmp_path: Path) -> None:
    # Given
    store = SqliteTaskStore(tmp_path / "tasks.db")
    store.upsert_notices((_notice("mail-1"), _notice("mail-2")))

    # When
    store.set_statuses(("mail-1", "mail-2"), EntryStatus.COMPLETED)

    # Then
    assert all(task.status is EntryStatus.COMPLETED for task in store.list_tasks(TaskFilter.ALL))


def test_store_rolls_back_batch_when_one_task_is_missing(tmp_path: Path) -> None:
    # Given
    store = SqliteTaskStore(tmp_path / "tasks.db")
    store.upsert_notices((_notice("mail-1"),))

    # When
    with pytest.raises(MissingTaskError, match="missing"):
        store.set_statuses(("mail-1", "missing"), EntryStatus.COMPLETED)

    # Then
    assert store.list_tasks(TaskFilter.ALL)[0].status is EntryStatus.PENDING


def test_store_keeps_unparsed_deposit_candidate_visible_for_review(tmp_path: Path) -> None:
    # Given
    store = SqliteTaskStore(tmp_path / "tasks.db")
    notice = UnparsedDepositNotice(
        message_id="unparsed",
        received_at=datetime(2026, 8, 24, 10, 0),
        subject="8/24 국내입금",
        reason="입금자를 찾을 수 없습니다.",
    )

    # When
    store.upsert_notices((notice,))

    # Then
    task = store.list_tasks(TaskFilter.ALL)[0]
    assert task.depositor_name == ""
    assert task.note == "입금자를 찾을 수 없습니다."
    assert task.status is EntryStatus.PENDING


def test_store_migrates_legacy_rows_and_requests_one_full_reparse(tmp_path: Path) -> None:
    # Given
    database_path = tmp_path / "legacy.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE deposit_tasks (message_id TEXT PRIMARY KEY, deposit_date TEXT, "
            "depositor_name TEXT NOT NULL, amount INTEGER, subject TEXT NOT NULL, "
            "received_at TEXT NOT NULL, note TEXT NOT NULL, status TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO deposit_tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "mail-1",
                None,
                "",
                None,
                "8/24 국내입금",
                "2026-08-24T09:30:00",
                "미해석",
                "pending",
            ),
        )

    # When
    store = SqliteTaskStore(database_path)
    first_scan_start = store.latest_received_at()
    store.upsert_notices((_notice(),))

    # Then
    task = store.list_tasks(TaskFilter.ALL)[0]
    assert first_scan_start is None
    assert task.bank_name == "기업018(원화)"
    assert task.note == ""
    assert store.latest_received_at() == datetime(2026, 8, 24, 9, 30)
