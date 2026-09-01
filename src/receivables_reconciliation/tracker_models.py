from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class EntryStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"


class TaskFilter(StrEnum):
    ALL = "all"
    PENDING = "pending"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class DepositTask:
    message_id: str
    deposit_date: date | None
    depositor_name: str
    amount: int | None
    subject: str
    received_at: datetime
    note: str
    status: EntryStatus
    bank_name: str = ""


@dataclass(frozen=True, slots=True)
class TaskSummary:
    total_count: int
    pending_count: int
    completed_count: int
    review_count: int


@dataclass(frozen=True, slots=True)
class TaskSnapshot:
    tasks: tuple[DepositTask, ...]
    summary: TaskSummary


@dataclass(frozen=True, slots=True)
class RefreshResult:
    snapshot: TaskSnapshot
    added_count: int
    scanned_count: int
