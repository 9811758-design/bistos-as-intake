from datetime import date, datetime

from receivables_reconciliation.tracker_models import DepositTask, EntryStatus
from receivables_reconciliation.tracker_name_filter import filter_tasks_by_depositor_name


def _task(message_id: str, depositor_name: str) -> DepositTask:
    return DepositTask(
        message_id=message_id,
        deposit_date=date(2026, 8, 24),
        depositor_name=depositor_name,
        amount=10_000,
        subject="국내입금",
        received_at=datetime(2026, 8, 24, 9, 0),
        note="",
        status=EntryStatus.PENDING,
    )


def test_name_filter_is_case_and_space_insensitive() -> None:
    tasks = (
        _task("one", "장 진영"),
        _task("two", "김민수"),
        _task("three", ""),
    )

    result = filter_tasks_by_depositor_name(tasks, "장진영")

    assert tuple(task.message_id for task in result) == ("one",)


def test_name_filter_blank_returns_all_tasks() -> None:
    tasks = (_task("one", "장진영"), _task("two", ""))

    result = filter_tasks_by_depositor_name(tasks, "")

    assert tuple(task.message_id for task in result) == ("one", "two")
