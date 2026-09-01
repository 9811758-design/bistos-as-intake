from __future__ import annotations

import os
import sqlite3
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Final, TypeAlias, assert_never

from receivables_reconciliation.models import DepositNotice, UnparsedDepositNotice
from receivables_reconciliation.tracker_models import (
    DepositTask,
    EntryStatus,
    TaskFilter,
    TaskSummary,
)

NoticeCandidate: TypeAlias = DepositNotice | UnparsedDepositNotice
_CURRENT_PARSE_VERSION: Final = 2
_SCHEMA: Final = (
    "CREATE TABLE IF NOT EXISTS deposit_tasks ("
    "message_id TEXT PRIMARY KEY, "
    "deposit_date TEXT, "
    "depositor_name TEXT NOT NULL, "
    "amount INTEGER, "
    "bank_name TEXT NOT NULL DEFAULT '', "
    "subject TEXT NOT NULL, "
    "received_at TEXT NOT NULL, "
    "note TEXT NOT NULL, "
    "parse_version INTEGER NOT NULL DEFAULT 2, "
    "status TEXT NOT NULL CHECK (status IN ('pending', 'completed'))"
    ")"
)
_UPSERT: Final = (
    "INSERT INTO deposit_tasks ("
    "message_id, deposit_date, depositor_name, amount, bank_name, subject, received_at, "
    "note, parse_version, status"
    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT(message_id) DO UPDATE SET "
    "deposit_date = excluded.deposit_date, "
    "depositor_name = excluded.depositor_name, "
    "amount = excluded.amount, "
    "bank_name = excluded.bank_name, "
    "subject = excluded.subject, "
    "received_at = excluded.received_at, "
    "note = excluded.note, "
    "parse_version = excluded.parse_version"
)


@dataclass(frozen=True, slots=True)
class TaskStoreError(Exception):
    detail: str

    def __str__(self) -> str:
        return f"입금메일 저장소 오류: {self.detail}"


@dataclass(frozen=True, slots=True)
class MissingTaskError(Exception):
    message_id: str

    def __str__(self) -> str:
        return f"목록에서 메일을 찾을 수 없습니다: {self.message_id}"


@dataclass(frozen=True, slots=True)
class _NoticeRecord:
    message_id: str
    deposit_date: str | None
    depositor_name: str
    amount: int | None
    bank_name: str
    subject: str
    received_at: str
    note: str

    def as_parameters(
        self,
    ) -> tuple[str, str | None, str, int | None, str, str, str, str, int, str]:
        return (
            self.message_id,
            self.deposit_date,
            self.depositor_name,
            self.amount,
            self.bank_name,
            self.subject,
            self.received_at,
            self.note,
            _CURRENT_PARSE_VERSION,
            EntryStatus.PENDING.value,
        )


class SqliteTaskStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def upsert_notices(self, notices: Sequence[NoticeCandidate]) -> int:
        records = tuple(_record_from_notice(notice) for notice in notices)
        if not records:
            return 0
        try:
            with closing(sqlite3.connect(self._path)) as connection, connection:
                before = _task_count(connection)
                connection.executemany(_UPSERT, (record.as_parameters() for record in records))
                return _task_count(connection) - before
        except sqlite3.Error as exc:
            raise TaskStoreError(str(exc)) from exc

    def list_tasks(self, task_filter: TaskFilter) -> tuple[DepositTask, ...]:
        query, parameters = _list_query(task_filter)
        try:
            with closing(sqlite3.connect(self._path)) as connection:
                rows = connection.execute(query, parameters).fetchall()
        except sqlite3.Error as exc:
            raise TaskStoreError(str(exc)) from exc
        return tuple(_task_from_row(row) for row in rows)

    def summary(self) -> TaskSummary:
        tasks = self.list_tasks(TaskFilter.ALL)
        return TaskSummary(
            total_count=len(tasks),
            pending_count=sum(task.status is EntryStatus.PENDING for task in tasks),
            completed_count=sum(task.status is EntryStatus.COMPLETED for task in tasks),
            review_count=sum(bool(task.note) for task in tasks),
        )

    def set_status(self, message_id: str, status: EntryStatus) -> None:
        self.set_statuses((message_id,), status)

    def set_statuses(self, message_ids: Sequence[str], status: EntryStatus) -> None:
        unique_message_ids = tuple(dict.fromkeys(message_ids))
        if not unique_message_ids:
            return
        placeholders = ", ".join("?" for _ in unique_message_ids)
        try:
            with closing(sqlite3.connect(self._path)) as connection, connection:
                rows = connection.execute(
                    f"SELECT message_id FROM deposit_tasks WHERE message_id IN ({placeholders})",
                    unique_message_ids,
                ).fetchall()
                existing_message_ids = {row[0] for row in rows}
                missing_message_id = next(
                    (
                        message_id
                        for message_id in unique_message_ids
                        if message_id not in existing_message_ids
                    ),
                    None,
                )
                if missing_message_id is not None:
                    raise MissingTaskError(missing_message_id)
                connection.execute(
                    f"UPDATE deposit_tasks SET status = ? WHERE message_id IN ({placeholders})",
                    (status.value, *unique_message_ids),
                )
        except sqlite3.Error as exc:
            raise TaskStoreError(str(exc)) from exc

    def latest_received_at(self) -> datetime | None:
        try:
            with closing(sqlite3.connect(self._path)) as connection:
                row = connection.execute(
                    "SELECT CASE WHEN EXISTS("
                    "SELECT 1 FROM deposit_tasks WHERE parse_version < ?"
                    ") THEN NULL ELSE MAX(received_at) END FROM deposit_tasks",
                    (_CURRENT_PARSE_VERSION,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise TaskStoreError(str(exc)) from exc
        latest = row[0] if row is not None else None
        return datetime.fromisoformat(latest) if isinstance(latest, str) else None

    def _initialize(self) -> None:
        try:
            with closing(sqlite3.connect(self._path)) as connection, connection:
                connection.execute(_SCHEMA)
                _migrate_schema(connection)
        except sqlite3.Error as exc:
            raise TaskStoreError(str(exc)) from exc


def default_store_path() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / ".receivables"
    return base / "ReceivablesReconciliation" / "deposit_tasks.db"


def _record_from_notice(notice: NoticeCandidate) -> _NoticeRecord:
    match notice:
        case DepositNotice():
            return _NoticeRecord(
                notice.message_id,
                notice.deposit_date.isoformat(),
                notice.depositor_name,
                notice.amount,
                notice.bank_name,
                notice.subject,
                notice.received_at.isoformat(timespec="seconds"),
                "",
            )
        case UnparsedDepositNotice():
            return _NoticeRecord(
                notice.message_id,
                None,
                "",
                None,
                "",
                notice.subject,
                notice.received_at.isoformat(timespec="seconds"),
                notice.reason,
            )
        case unreachable:
            assert_never(unreachable)


def _list_query(task_filter: TaskFilter) -> tuple[str, tuple[str, ...]]:
    base = (
        "SELECT message_id, deposit_date, depositor_name, amount, bank_name, subject, "
        "received_at, note, status FROM deposit_tasks"
    )
    match task_filter:
        case TaskFilter.ALL:
            return (f"{base} ORDER BY received_at DESC", ())
        case TaskFilter.PENDING:
            return (
                f"{base} WHERE status = ? ORDER BY received_at DESC",
                (EntryStatus.PENDING.value,),
            )
        case TaskFilter.COMPLETED:
            return (
                f"{base} WHERE status = ? ORDER BY received_at DESC",
                (EntryStatus.COMPLETED.value,),
            )
        case unreachable:
            assert_never(unreachable)


def _task_from_row(
    row: tuple[str, str | None, str, int | None, str, str, str, str, str],
) -> DepositTask:
    return DepositTask(
        message_id=row[0],
        deposit_date=date.fromisoformat(row[1]) if row[1] is not None else None,
        depositor_name=row[2],
        amount=row[3],
        bank_name=row[4],
        subject=row[5],
        received_at=datetime.fromisoformat(row[6]),
        note=row[7],
        status=EntryStatus(row[8]),
    )


def _migrate_schema(connection: sqlite3.Connection) -> None:
    columns = {row[1] for row in connection.execute("PRAGMA table_info(deposit_tasks)")}
    if "bank_name" not in columns:
        connection.execute(
            "ALTER TABLE deposit_tasks ADD COLUMN bank_name TEXT NOT NULL DEFAULT ''"
        )
    if "parse_version" not in columns:
        connection.execute(
            "ALTER TABLE deposit_tasks ADD COLUMN parse_version INTEGER NOT NULL DEFAULT 1"
        )


def _task_count(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT COUNT(*) FROM deposit_tasks").fetchone()
    return int(row[0]) if row is not None else 0
