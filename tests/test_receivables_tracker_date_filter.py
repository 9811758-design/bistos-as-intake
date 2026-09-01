from datetime import date, datetime

import pytest

from receivables_reconciliation.tracker_date_filter import (
    InvalidDepositDateRangeError,
    filter_tasks_by_deposit_date,
    parse_deposit_date_range,
)
from receivables_reconciliation.tracker_models import DepositTask, EntryStatus


def _task(message_id: str, deposit_date: date | None) -> DepositTask:
    return DepositTask(
        message_id=message_id,
        deposit_date=deposit_date,
        depositor_name="입금자",
        amount=10_000,
        subject="국내입금",
        received_at=datetime(2026, 8, 24, 9, 0),
        note="",
        status=EntryStatus.PENDING,
    )


def test_date_range_includes_both_boundaries() -> None:
    # Given
    tasks = (
        _task("before", date(2026, 6, 10)),
        _task("start", date(2026, 6, 11)),
        _task("end", date(2026, 8, 20)),
        _task("after", date(2026, 8, 21)),
        _task("unparsed", None),
    )
    date_range = parse_deposit_date_range("2026-06-11", "2026-08-20")

    # When
    result = filter_tasks_by_deposit_date(tasks, date_range)

    # Then
    assert tuple(task.message_id for task in result) == ("start", "end")


@pytest.mark.parametrize("start,end", [("2026/06/11", ""), ("", "2026-13-01")])
def test_date_range_rejects_invalid_date_format(start: str, end: str) -> None:
    with pytest.raises(InvalidDepositDateRangeError, match="YYYY-MM-DD"):
        parse_deposit_date_range(start, end)


def test_date_range_rejects_start_after_end() -> None:
    with pytest.raises(InvalidDepositDateRangeError, match="시작일"):
        parse_deposit_date_range("2026-08-21", "2026-08-20")
