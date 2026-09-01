from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Final

from .columns import SheetField
from .numbering import service_number_date
from .records import SheetRow


class InvalidAnalyticsDateRangeError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AnalyticsDateRange:
    start: date
    end: date

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise InvalidAnalyticsDateRangeError("시작일은 종료일보다 늦을 수 없습니다.")

    def includes(self, value: date) -> bool:
        return self.start <= value <= self.end


@dataclass(frozen=True, slots=True)
class WarrantyCount:
    warranty: str
    count: int


@dataclass(frozen=True, slots=True)
class OverdueRow:
    service_number: str
    received_date: date
    age_days: int
    model: str
    failure_cause: str


@dataclass(frozen=True, slots=True)
class RepeatFailure:
    model: str
    failure_cause: str
    count: int


@dataclass(frozen=True, slots=True)
class MonthlyFailureCause:
    month: str
    failure_cause: str
    count: int


@dataclass(frozen=True, slots=True)
class ModelServiceCount:
    model: str
    count: int


@dataclass(frozen=True, slots=True)
class AnalyticsReport:
    date_range: AnalyticsDateRange
    included_row_count: int
    date_unparseable_excluded_count: int
    overdue_rows: tuple[OverdueRow, ...]
    warranty_counts: tuple[WarrantyCount, ...]
    repeat_failures: tuple[RepeatFailure, ...]
    monthly_failure_causes: tuple[MonthlyFailureCause, ...]
    model_service_counts: tuple[ModelServiceCount, ...]


_FULL_DATE_PATTERN: Final = re.compile(
    r"^(?P<year>\d{4})[-./](?P<month>\d{1,2})[-./](?P<day>\d{1,2})$"
)
_MONTH_DAY_PATTERN: Final = re.compile(r"^(?P<month>\d{1,2})/(?P<day>\d{1,2})$")


def build_analytics_report(
    rows: Iterable[SheetRow],
    date_range: AnalyticsDateRange,
    today: date,
) -> AnalyticsReport:
    all_rows = tuple(rows)
    included_rows: list[tuple[SheetRow, date]] = []
    date_unparseable_excluded_count = 0

    for row in all_rows:
        received_date = service_number_date(row.value(SheetField.SERVICE_NUMBER))
        if received_date is None:
            date_unparseable_excluded_count += 1
            continue
        if date_range.includes(received_date):
            included_rows.append((row, received_date))

    return AnalyticsReport(
        date_range=date_range,
        included_row_count=len(included_rows),
        date_unparseable_excluded_count=date_unparseable_excluded_count,
        overdue_rows=_overdue_rows(included_rows, today),
        warranty_counts=_warranty_counts(row for row, _received_date in included_rows),
        repeat_failures=_repeat_failures(row for row, _received_date in included_rows),
        monthly_failure_causes=_monthly_failure_causes(included_rows),
        model_service_counts=_model_service_counts(all_rows, date_range),
    )


def _overdue_rows(rows: Iterable[tuple[SheetRow, date]], today: date) -> tuple[OverdueRow, ...]:
    overdue_rows: list[OverdueRow] = []
    for row, received_date in rows:
        age_days = (today - received_date).days
        if age_days >= 7 and row.value(SheetField.COMPLETION_DATE).strip() == "":
            overdue_rows.append(
                OverdueRow(
                    service_number=row.value(SheetField.SERVICE_NUMBER),
                    received_date=received_date,
                    age_days=age_days,
                    model=_normalized_model(row),
                    failure_cause=_normalized_text(row.value(SheetField.FAILURE_CAUSE)),
                )
            )
    return tuple(overdue_rows)


def _warranty_counts(rows: Iterable[SheetRow]) -> tuple[WarrantyCount, ...]:
    counts = Counter(row.value(SheetField.WARRANTY) for row in rows)
    return tuple(
        WarrantyCount(warranty=warranty, count=count)
        for warranty, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    )


def _repeat_failures(rows: Iterable[SheetRow]) -> tuple[RepeatFailure, ...]:
    counts: Counter[tuple[str, str]] = Counter()
    for row in rows:
        model = _normalized_model(row)
        failure_cause = _normalized_text(row.value(SheetField.FAILURE_CAUSE))
        if model != "" and failure_cause != "":
            counts[(model, failure_cause)] += 1
    return tuple(
        RepeatFailure(model=model, failure_cause=failure_cause, count=count)
        for (model, failure_cause), count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1]),
        )
        if count >= 2
    )


def _monthly_failure_causes(
    rows: Iterable[tuple[SheetRow, date]],
) -> tuple[MonthlyFailureCause, ...]:
    counts: Counter[tuple[str, str]] = Counter()
    for row, received_date in rows:
        failure_cause = _normalized_text(row.value(SheetField.FAILURE_CAUSE))
        if failure_cause != "":
            counts[(received_date.strftime("%Y-%m"), failure_cause)] += 1
    return tuple(
        MonthlyFailureCause(month=month, failure_cause=failure_cause, count=count)
        for (month, failure_cause), count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1]),
        )
    )


def _model_service_counts(
    rows: Iterable[SheetRow],
    date_range: AnalyticsDateRange,
) -> tuple[ModelServiceCount, ...]:
    counts: Counter[str] = Counter()
    for row in rows:
        receipt_date = service_number_date(row.value(SheetField.SERVICE_NUMBER))
        fallback_year = receipt_date.year if receipt_date is not None else None
        completion_date = _parse_completion_date(
            row.value(SheetField.COMPLETION_DATE),
            fallback_year,
        )
        model = _normalized_model(row)
        if completion_date is not None and date_range.includes(completion_date) and model != "":
            counts[model] += 1
    return tuple(
        ModelServiceCount(model=model, count=count)
        for model, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    )


def _parse_completion_date(value: str, fallback_year: int | None) -> date | None:
    text = value.strip()
    full_match = _FULL_DATE_PATTERN.fullmatch(text)
    if full_match is not None:
        return _safe_date(
            int(full_match.group("year")),
            int(full_match.group("month")),
            int(full_match.group("day")),
        )
    month_day_match = _MONTH_DAY_PATTERN.fullmatch(text)
    if month_day_match is None or fallback_year is None:
        return None
    return _safe_date(
        fallback_year,
        int(month_day_match.group("month")),
        int(month_day_match.group("day")),
    )


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _normalized_model(row: SheetRow) -> str:
    return _normalized_text(row.value(SheetField.MODEL)).upper()


def _normalized_text(value: str) -> str:
    return " ".join(value.split())
