from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest

from as_intake.analytics import (
    AnalyticsDateRange,
    ModelServiceCount,
    WarrantyCount,
    build_analytics_report,
)
from as_intake.columns import SheetField
from as_intake.records import SheetRow


@dataclass(frozen=True, slots=True)
class RowSpec:
    service_number: str
    warranty: str = ""
    model: str = ""
    failure_cause: str = ""
    completion_date: str = ""
    close_status: str = ""


def _row(spec: RowSpec) -> SheetRow:
    values = [""] * 36
    values[SheetField.SERVICE_NUMBER] = spec.service_number
    values[SheetField.WARRANTY] = spec.warranty
    values[SheetField.MODEL] = spec.model
    values[SheetField.FAILURE_CAUSE] = spec.failure_cause
    values[SheetField.COMPLETION_DATE] = spec.completion_date
    values[SheetField.CLOSE_STATUS] = spec.close_status
    return SheetRow(tuple(values))


def test_report_counts_rows_when_date_range_boundaries_are_inclusive() -> None:
    # Given
    rows = (
        _row(RowSpec("DS26073101", warranty="내")),
        _row(RowSpec("DS26080101", warranty="내")),
        _row(RowSpec("DS26083101", warranty="외")),
        _row(RowSpec("DS26090101", warranty="외")),
    )
    date_range = AnalyticsDateRange(date(2026, 8, 1), date(2026, 8, 31))

    # When
    report = build_analytics_report(rows, date_range, today=date(2026, 8, 25))

    # Then
    assert report.included_row_count == 2
    assert report.warranty_counts == (WarrantyCount("내", 1), WarrantyCount("외", 1))


def test_report_rejects_reversed_date_range_before_reading_rows() -> None:
    # Given / When / Then
    with pytest.raises(ValueError, match="시작일"):
        AnalyticsDateRange(date(2026, 8, 31), date(2026, 8, 1))


def test_report_excludes_unparseable_service_dates() -> None:
    # Given
    rows = (
        _row(RowSpec("DS26080101", warranty="내")),
        _row(RowSpec("DS26083201", warranty="외")),
        _row(RowSpec("2026.08.01", warranty="N/A")),
    )
    date_range = AnalyticsDateRange(date(2026, 8, 1), date(2026, 8, 31))

    # When
    report = build_analytics_report(rows, date_range, today=date(2026, 8, 25))

    # Then
    assert report.included_row_count == 2
    assert report.date_unparseable_excluded_count == 1
    assert report.warranty_counts == (WarrantyCount("N/A", 1), WarrantyCount("내", 1))


def test_report_marks_only_blank_completion_rows_overdue_at_seven_day_boundary() -> None:
    # Given
    rows = (
        _row(RowSpec("DS26081901", model="BT350L")),
        _row(RowSpec("DS26081801", model="BT350L")),
        _row(RowSpec("DS26081701", model="BT350L", completion_date="2026-08-24")),
        _row(RowSpec("DS26081601", model="BT350L", close_status="종료")),
    )
    date_range = AnalyticsDateRange(date(2026, 8, 1), date(2026, 8, 31))

    # When
    report = build_analytics_report(rows, date_range, today=date(2026, 8, 25))

    # Then
    assert [(row.service_number, row.age_days) for row in report.overdue_rows] == [
        ("DS26081801", 7),
        ("DS26081601", 9),
    ]


def test_report_groups_repeats_by_normalized_exact_model_and_nonblank_cause() -> None:
    # Given
    rows = (
        _row(RowSpec("DS26080101", model=" bt350l ", failure_cause="Battery")),
        _row(RowSpec("DS26080201", model="BT350L", failure_cause="Battery")),
        _row(RowSpec("DS26080301", model="BT350L", failure_cause="")),
        _row(RowSpec("DS26080401", model="BT200", failure_cause="Battery")),
        _row(RowSpec("DS26080501", model="BT200", failure_cause="Battery")),
        _row(RowSpec("DS26080601", model="BT100", failure_cause="Cable")),
    )
    date_range = AnalyticsDateRange(date(2026, 8, 1), date(2026, 8, 31))

    # When
    report = build_analytics_report(rows, date_range, today=date(2026, 8, 25))

    # Then
    assert [(item.model, item.failure_cause, item.count) for item in report.repeat_failures] == [
        ("BT200", "Battery", 2),
        ("BT350L", "Battery", 2),
    ]


def test_report_sorts_monthly_failure_causes_by_count_month_then_cause() -> None:
    # Given
    rows = (
        _row(RowSpec("DS26080101", failure_cause="Battery")),
        _row(RowSpec("DS26080201", failure_cause="Battery")),
        _row(RowSpec("DS26080301", failure_cause="Cable")),
        _row(RowSpec("DS26090101", failure_cause="Cable")),
        _row(RowSpec("DS26090201", failure_cause="Battery")),
        _row(RowSpec("DS26090301", failure_cause=" ")),
    )
    date_range = AnalyticsDateRange(date(2026, 8, 1), date(2026, 9, 30))

    # When
    report = build_analytics_report(rows, date_range, today=date(2026, 9, 30))

    # Then
    assert [
        (item.month, item.failure_cause, item.count) for item in report.monthly_failure_causes
    ] == [
        ("2026-08", "Battery", 2),
        ("2026-08", "Cable", 1),
        ("2026-09", "Battery", 1),
        ("2026-09", "Cable", 1),
    ]


def test_report_counts_models_by_completion_date_not_receipt_date() -> None:
    rows = (
        _row(RowSpec("DS26073101", model="BT350L", completion_date="8/1")),
        _row(RowSpec("DS26090101", model="BT350L", completion_date="8/31")),
        _row(RowSpec("DS26080101", model="BT700", completion_date="7/31")),
        _row(RowSpec("2026.08.15", model="BCM350", completion_date="2026-08-15")),
        _row(RowSpec("DS26080201", model=" ", completion_date="8/20")),
    )

    report = build_analytics_report(
        rows,
        AnalyticsDateRange(date(2026, 8, 1), date(2026, 8, 31)),
        today=date(2026, 8, 31),
    )

    assert report.model_service_counts == (
        ModelServiceCount("BT350L", 2),
        ModelServiceCount("BCM350", 1),
    )
