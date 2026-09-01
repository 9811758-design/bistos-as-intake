from __future__ import annotations

from datetime import date

import pytest

from as_intake.columns import SheetField
from as_intake.google_transport import GoogleRequestError
from as_intake.recommendation import RecommendationQuery
from as_intake.records import RecordDraft, SheetRow
from as_intake.service import (
    ASIntakeService,
    DuplicateServiceNumberError,
    SearchQuery,
    ServiceAnalyticsReadError,
)


class FakeSheetGateway:
    def __init__(self, rows: tuple[SheetRow, ...] = ()) -> None:
        self.rows = list(rows)
        self.rows_by_year: dict[int, tuple[SheetRow, ...]] = {}
        self.missing_years: set[int] = set()
        self.google_errors_by_year: dict[int, GoogleRequestError] = {}
        self.read_years: list[int] = []
        self.inserted: list[tuple[int, SheetRow]] = []
        self.overwritten: list[tuple[int, int, SheetRow]] = []

    def read_rows(self, year: int) -> tuple[SheetRow, ...]:
        self.read_years.append(year)
        google_error = self.google_errors_by_year.get(year)
        if google_error is not None:
            raise google_error
        if year in self.missing_years:
            raise LookupError(f"missing tab: {year}")
        if self.rows_by_year:
            return self.rows_by_year.get(year, ())
        return tuple(self.rows)

    def insert_row(self, year: int, row: SheetRow) -> SheetRow:
        stored = SheetRow(row.values, row_number=5)
        self.rows.insert(0, stored)
        self.inserted.append((year, stored))
        return stored

    def overwrite_row(self, year: int, row_number: int, row: SheetRow) -> SheetRow:
        stored = SheetRow(row.values, row_number=row_number)
        self.overwritten.append((year, row_number, stored))
        self.rows = [stored if item.row_number == row_number else item for item in self.rows]
        return stored


def _row(row_number: int, number: str, requester: str, model: str) -> SheetRow:
    draft = RecordDraft.create(
        receipt_date=date(2026, 8, 24),
        values={SheetField.REQUESTER: requester, SheetField.MODEL: model},
    )
    return SheetRow(draft.to_sheet_row(number).values, row_number=row_number)


def test_register_generates_number_and_inserts_complete_row() -> None:
    gateway = FakeSheetGateway((_row(5, "DS26082401", "국제메디칼", "BT350L"),))
    service = ASIntakeService(gateway)
    draft = RecordDraft.create(
        receipt_date=date(2026, 8, 24),
        values={SheetField.REQUESTER: "대신메디케어", SheetField.MODEL: "BT710"},
    )

    stored = service.register(draft)

    assert stored.value(SheetField.SERVICE_NUMBER) == "DS26082402"
    assert gateway.inserted == [(2026, stored)]


def test_register_bcm_uses_receipt_date_and_forces_serial_and_production_na() -> None:
    gateway = FakeSheetGateway()
    draft = RecordDraft.create(
        receipt_date=date(2026, 8, 25),
        values={
            SheetField.MODEL: "BCM350N",
            SheetField.SERIAL_NUMBER: "SHOULD-BE-REMOVED",
            SheetField.PRODUCTION_MONTH: "2026-01",
        },
    )

    stored = ASIntakeService(gateway).register(draft)

    assert stored.value(SheetField.SERVICE_NUMBER) == "2026.08.25"
    assert stored.value(SheetField.SERIAL_NUMBER) == "N/A"
    assert stored.value(SheetField.PRODUCTION_MONTH) == "N/A"
    assert gateway.inserted == [(2026, stored)]


def test_search_matches_service_requester_hospital_model_serial_and_symptom() -> None:
    first = _row(5, "DS26082402", "대신메디케어", "BT710")
    second = _row(6, "DS26082401", "국제메디칼", "BT350L")
    service = ASIntakeService(FakeSheetGateway((first, second)))

    assert service.search(SearchQuery(year=2026, text="대신")) == (first,)


def test_search_matches_requester_phone_number() -> None:
    # Given
    matching = _row(5, "DS26082402", "대신메디케어", "BT710").with_value(
        SheetField.REQUESTER_CONTACT,
        "010-3294-1032",
    )
    other = _row(6, "DS26082401", "국제메디칼", "BT350L").with_value(
        SheetField.REQUESTER_CONTACT,
        "010-5555-7777",
    )
    service = ASIntakeService(FakeSheetGateway((matching, other)))

    # When
    result = service.search(SearchQuery(year=2026, text="3294"))

    # Then
    assert result == (matching,)


def test_update_re_resolves_service_number_and_overwrites_full_row() -> None:
    original = _row(12, "DS26082401", "국제메디칼", "BT350L")
    gateway = FakeSheetGateway((original,))
    changed = original.with_value(SheetField.SYMPTOM, "수정된 증상")

    stored = ASIntakeService(gateway).update("DS26082401", changed)

    assert stored.row_number == 12
    assert stored.value(SheetField.SYMPTOM) == "수정된 증상"
    assert gateway.overwritten == [(2026, 12, stored)]


def test_update_rejects_duplicate_service_numbers() -> None:
    duplicate = _row(5, "DS26082401", "A", "BT350L")
    gateway = FakeSheetGateway((duplicate, SheetRow(duplicate.values, row_number=6)))
    changed_without_selected_row = SheetRow(duplicate.values)

    with pytest.raises(DuplicateServiceNumberError):
        ASIntakeService(gateway).update("DS26082401", changed_without_selected_row)


def test_update_uses_selected_row_number_when_bcm_date_number_is_duplicated() -> None:
    first = _row(5, "2026.08.25", "A", "BCM350")
    second = _row(6, "2026.08.25", "B", "BCM700")
    gateway = FakeSheetGateway((first, second))
    changed = second.with_value(SheetField.SYMPTOM, "수정된 BCM 증상")

    stored = ASIntakeService(gateway).update("2026.08.25", changed)

    assert stored.row_number == 6
    assert stored.value(SheetField.SYMPTOM) == "수정된 BCM 증상"
    assert stored.value(SheetField.SERIAL_NUMBER) == "N/A"
    assert stored.value(SheetField.PRODUCTION_MONTH) == "N/A"
    assert gateway.overwritten == [(2026, 6, stored)]


def test_search_preserves_unusual_unicode_and_ignores_formula_commands() -> None:
    original = _row(5, "DS26082401", "고객 🩺", "=DELETE(ALL)")
    service = ASIntakeService(FakeSheetGateway((original,)))

    assert service.search(SearchQuery(year=2026, text="🩺")) == (original,)
    assert service.search(SearchQuery(year=2026, text="=delete")) == (original,)


def test_recommend_reads_the_selected_year_and_returns_matching_history() -> None:
    # Given
    resolved = _row(5, "DS26082401", "국제메디칼", "BT350L")
    resolved = resolved.with_value(SheetField.SYMPTOM, "전원이 켜지지 않음")
    resolved = resolved.with_value(SheetField.FAILURE_CAUSE, "DC JACK 불량")
    resolved = resolved.with_value(SheetField.ACTION, "DC JACK 교체")
    service = ASIntakeService(FakeSheetGateway((resolved,)))

    # When
    report = service.recommend(
        RecommendationQuery(2026, "전원 안켜짐", "DC JACK 불량", "BT350L")
    )

    # Then
    assert report.analyzed_rows == 1
    assert report.recommendations[0].source == resolved


def test_analytics_report_reads_single_year_once_without_writes() -> None:
    # Given
    row = _row(5, "DS26082401", "국제메디칼", "BT350L")
    row = row.with_value(SheetField.FAILURE_CAUSE, "배터리 불량")
    gateway = FakeSheetGateway()
    gateway.rows_by_year = {2026: (row,)}
    service = ASIntakeService(gateway)

    # When
    report = service.analytics_report(
        date(2026, 8, 1),
        date(2026, 8, 31),
        today=date(2026, 8, 31),
    )

    # Then
    assert gateway.read_years == [2026]
    assert gateway.inserted == []
    assert gateway.overwritten == []
    assert report.included_row_count == 1
    assert report.monthly_failure_causes[0].failure_cause == "배터리 불량"


def test_analytics_report_reads_cross_year_range_once_per_year() -> None:
    # Given
    first = _row(5, "DS26123101", "국제메디칼", "BT350L")
    second = _row(5, "DS27010101", "국제메디칼", "BT350L")
    gateway = FakeSheetGateway()
    gateway.rows_by_year = {2026: (first,), 2027: (second,)}

    # When
    report = ASIntakeService(gateway).analytics_report(
        date(2026, 12, 31),
        date(2027, 1, 1),
        today=date(2027, 1, 8),
    )

    # Then
    assert gateway.read_years == [2026, 2027]
    assert report.included_row_count == 2
    assert gateway.inserted == []
    assert gateway.overwritten == []


def test_analytics_report_reversed_range_reads_no_rows() -> None:
    # Given
    gateway = FakeSheetGateway((_row(5, "DS26082401", "국제메디칼", "BT350L"),))

    # When / Then
    with pytest.raises(ValueError, match="시작일"):
        ASIntakeService(gateway).analytics_report(
            date(2026, 8, 31),
            date(2026, 8, 1),
            today=date(2026, 8, 31),
        )
    assert gateway.read_years == []
    assert gateway.inserted == []
    assert gateway.overwritten == []


def test_analytics_report_missing_year_tab_is_user_facing_error() -> None:
    # Given
    gateway = FakeSheetGateway()
    gateway.rows_by_year = {2026: (_row(5, "DS26123101", "국제메디칼", "BT350L"),)}
    gateway.missing_years = {2027}

    # When / Then
    with pytest.raises(ServiceAnalyticsReadError, match="2027"):
        ASIntakeService(gateway).analytics_report(
            date(2026, 12, 31),
            date(2027, 1, 1),
            today=date(2027, 1, 8),
        )
    assert gateway.read_years == [2026, 2027]
    assert gateway.inserted == []
    assert gateway.overwritten == []


def test_analytics_report_google_missing_range_is_user_facing_error() -> None:
    # Given
    gateway = FakeSheetGateway()
    gateway.rows_by_year = {2026: (_row(5, "DS26123101", "국제메디칼", "BT350L"),)}
    gateway.google_errors_by_year = {
        2027: GoogleRequestError(
            "Google Sheets API 오류 400: "
            '{"error":{"code":400,"message":"Unable to parse range: '
            "'2027 국내 서비스 접수/처리 내역'!A5:AJ\","
            '"status":"INVALID_ARGUMENT"}}'
        )
    }

    # When / Then
    with pytest.raises(ServiceAnalyticsReadError, match="2027"):
        ASIntakeService(gateway).analytics_report(
            date(2026, 12, 31),
            date(2027, 1, 1),
            today=date(2027, 1, 8),
        )
    assert gateway.read_years == [2026, 2027]
    assert gateway.inserted == []
    assert gateway.overwritten == []


def test_analytics_report_does_not_mislabel_unrelated_google_errors() -> None:
    # Given
    gateway = FakeSheetGateway()
    gateway.google_errors_by_year = {
        2026: GoogleRequestError(
            'Google Sheets API 오류 403: {"error":{"message":"Permission denied"}}'
        )
    }

    # When / Then
    with pytest.raises(GoogleRequestError, match="Permission denied"):
        ASIntakeService(gateway).analytics_report(
            date(2026, 8, 1),
            date(2026, 8, 31),
            today=date(2026, 8, 31),
        )
    assert gateway.read_years == [2026]
    assert gateway.inserted == []
    assert gateway.overwritten == []


def test_current_year_overdue_report_uses_injected_today() -> None:
    # Given
    overdue = _row(5, "DS26082401", "국제메디칼", "BT350L")
    recent = _row(6, "DS26082501", "국제메디칼", "BT350L")
    completed = _row(7, "DS26082001", "국제메디칼", "BT350L").with_value(
        SheetField.COMPLETION_DATE,
        "2026-08-26",
    )
    gateway = FakeSheetGateway()
    gateway.rows_by_year = {2026: (overdue, recent, completed)}

    # When
    report = ASIntakeService(gateway).current_year_overdue_report(
        today=date(2026, 8, 31)
    )

    # Then
    assert gateway.read_years == [2026]
    assert tuple(row.service_number for row in report.overdue_rows) == ("DS26082401",)
    assert gateway.inserted == []
    assert gateway.overwritten == []
