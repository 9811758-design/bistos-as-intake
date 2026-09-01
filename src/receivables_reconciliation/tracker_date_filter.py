from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from receivables_reconciliation.tracker_models import DepositTask


@dataclass(frozen=True, slots=True)
class InvalidDepositDateRangeError(Exception):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class DepositDateRange:
    start: date | None
    end: date | None

    def includes(self, task: DepositTask) -> bool:
        if self.start is None and self.end is None:
            return True
        if task.deposit_date is None:
            return False
        if self.start is not None and task.deposit_date < self.start:
            return False
        return self.end is None or task.deposit_date <= self.end


def parse_deposit_date_range(start_text: str, end_text: str) -> DepositDateRange:
    try:
        start = date.fromisoformat(start_text.strip()) if start_text.strip() else None
        end = date.fromisoformat(end_text.strip()) if end_text.strip() else None
    except ValueError as exc:
        raise InvalidDepositDateRangeError(
            "입금일은 YYYY-MM-DD 형식으로 입력하세요."
        ) from exc
    if start is not None and end is not None and start > end:
        raise InvalidDepositDateRangeError("시작일은 종료일보다 늦을 수 없습니다.")
    return DepositDateRange(start, end)


def filter_tasks_by_deposit_date(
    tasks: Sequence[DepositTask],
    date_range: DepositDateRange,
) -> tuple[DepositTask, ...]:
    return tuple(task for task in tasks if date_range.includes(task))
