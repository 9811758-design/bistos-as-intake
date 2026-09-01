from __future__ import annotations

from datetime import date

import pytest

from as_intake.numbering import (
    DailySequenceExhaustedError,
    next_service_number,
    service_number_date,
)


def test_next_service_number_uses_date_and_next_daily_sequence() -> None:
    actual = next_service_number(
        date(2026, 8, 24),
        ("DS26082401", "DS26082403", "2026.08. 24", "DS26082399"),
    )

    assert actual == "DS26082404"


def test_next_service_number_starts_at_one_when_date_has_no_records() -> None:
    assert next_service_number(date(2026, 8, 25), ("DS26082401",)) == "DS26082501"


def test_next_service_number_rejects_more_than_99_receipts_per_day() -> None:
    existing = tuple(f"DS260824{sequence:02d}" for sequence in range(1, 100))

    with pytest.raises(DailySequenceExhaustedError):
        next_service_number(date(2026, 8, 24), existing)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("DS26082601", date(2026, 8, 26)),
        ("2026.08.25", date(2026, 8, 25)),
        ("2026.02.30", None),
    ],
)
def test_service_number_date_accepts_ds_and_bcm_date_numbers(
    value: str,
    expected: date | None,
) -> None:
    assert service_number_date(value) == expected
