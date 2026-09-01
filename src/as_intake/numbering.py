from __future__ import annotations

import re
from datetime import date
from typing import Final

SERVICE_NUMBER_PATTERN: Final = re.compile(r"^DS(?P<date>\d{6})(?P<sequence>\d{2})$")
BCM_SERVICE_NUMBER_PATTERN: Final = re.compile(
    r"^(?P<year>\d{4})\.(?P<month>\d{2})\.(?P<day>\d{2})$"
)


class DailySequenceExhaustedError(ValueError):
    pass


def next_service_number(receipt_date: date, existing_numbers: tuple[str, ...]) -> str:
    date_part = receipt_date.strftime("%y%m%d")
    used_sequences = []
    for value in existing_numbers:
        match = SERVICE_NUMBER_PATTERN.fullmatch(value.strip())
        if match is not None and match.group("date") == date_part:
            used_sequences.append(int(match.group("sequence")))
    next_sequence = max(used_sequences, default=0) + 1
    if next_sequence > 99:
        raise DailySequenceExhaustedError(
            f"{receipt_date.isoformat()} 접수번호가 99건을 초과했습니다."
        )
    return f"DS{date_part}{next_sequence:02d}"


def service_number_date(value: str) -> date | None:
    text = value.strip()
    bcm_match = BCM_SERVICE_NUMBER_PATTERN.fullmatch(text)
    if bcm_match is not None:
        return _safe_date(
            int(bcm_match.group("year")),
            int(bcm_match.group("month")),
            int(bcm_match.group("day")),
        )

    match = SERVICE_NUMBER_PATTERN.fullmatch(text)
    if match is None:
        return None
    date_part = match.group("date")
    return _safe_date(
        2000 + int(date_part[:2]),
        int(date_part[2:4]),
        int(date_part[4:6]),
    )


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None
