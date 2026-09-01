from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pytest

from receivables_reconciliation.erp_xls import ErpXlsHeaderError
from receivables_reconciliation.models import (
    DepositNotice,
    ErpRegistration,
    MatchStatus,
    UnparsedDepositNotice,
)
from receivables_reconciliation.outlook_reader import OutlookComUnavailableError
from receivables_reconciliation.service import (
    ReceivablesReconciliationService,
    ReconciliationPipelineError,
    ReconciliationRequest,
)


@dataclass(frozen=True, slots=True)
class FakeOutlookReader:
    notices: tuple[DepositNotice | UnparsedDepositNotice, ...]

    def read(
        self,
        start_date: date,
        end_date: date,
    ) -> tuple[DepositNotice | UnparsedDepositNotice, ...]:
        assert start_date == date(2026, 8, 14)
        assert end_date == date(2026, 8, 15)
        return self.notices


@dataclass(frozen=True, slots=True)
class FailingOutlookReader:
    def read(
        self,
        start_date: date,
        end_date: date,
    ) -> tuple[DepositNotice | UnparsedDepositNotice, ...]:
        raise OutlookComUnavailableError("classic COM unavailable")


def test_run_returns_counts_and_only_actionable_rows_when_sources_match() -> None:
    # Given
    request = ReconciliationRequest(date(2026, 8, 14), date(2026, 8, 15), Path("erp.xls"))
    received_at = datetime(2026, 8, 14, 9, 30)
    notices = (
        DepositNotice("registered", date(2026, 8, 14), "Acme", 10, "registered", received_at),
        DepositNotice("unregistered", date(2026, 8, 14), "Beta", 20, "unregistered", received_at),
        DepositNotice("duplicate", date(2026, 8, 15), "Gamma", None, "duplicate", received_at),
        UnparsedDepositNotice("unparsed", received_at, "needs review", "missing name"),
    )
    registrations = (
        ErpRegistration(2, date(2026, 8, 14), "Acme", None, False),
        ErpRegistration(3, date(2026, 8, 15), "Gamma", None, False),
        ErpRegistration(4, date(2026, 8, 15), "Other", "Gamma", False),
    )
    service = ReceivablesReconciliationService(
        FakeOutlookReader(notices),
        lambda path: registrations,
    )

    # When
    report = service.run(request)

    # Then
    assert report.summary.registered_count == 1
    assert report.summary.erp_registration_count == 3
    assert report.summary.unregistered_count == 1
    assert report.summary.review_needed_count == 2
    assert report.summary.unparsed_count == 1
    assert report.summary.actionable_count == 3
    assert tuple(row.message_id for row in report.actionable_rows) == (
        "unregistered",
        "duplicate",
        "unparsed",
    )
    assert tuple(row.status for row in report.actionable_rows) == (
        MatchStatus.UNREGISTERED,
        MatchStatus.REVIEW_NEEDED,
        MatchStatus.REVIEW_NEEDED,
    )
    assert report.actionable_rows[2].reason == "missing name"
    assert report.source_erp_path == Path("erp.xls")


def test_run_returns_empty_success_when_sources_have_no_candidates() -> None:
    # Given
    request = ReconciliationRequest(date(2026, 8, 14), date(2026, 8, 15), Path("empty.xls"))
    service = ReceivablesReconciliationService(FakeOutlookReader(()), lambda path: ())

    # When
    report = service.run(request)

    # Then
    assert report.summary.total_candidates == 0
    assert report.summary.actionable_count == 0
    assert report.actionable_rows == ()


def test_run_raises_typed_error_when_outlook_adapter_fails() -> None:
    # Given
    request = ReconciliationRequest(date(2026, 8, 14), date(2026, 8, 15), Path("erp.xls"))
    service = ReceivablesReconciliationService(FailingOutlookReader(), lambda path: ())

    # When
    with pytest.raises(ReconciliationPipelineError, match="Outlook"):
        service.run(request)


def test_run_raises_typed_error_when_erp_parser_fails() -> None:
    # Given
    request = ReconciliationRequest(date(2026, 8, 14), date(2026, 8, 15), Path("erp.xls"))

    def failing_erp_reader(path: Path) -> tuple[ErpRegistration, ...]:
        raise ErpXlsHeaderError("Sheet1", "missing headers")

    service = ReceivablesReconciliationService(FakeOutlookReader(()), failing_erp_reader)

    # When
    with pytest.raises(ReconciliationPipelineError, match="ERP"):
        service.run(request)


def test_run_filters_both_sources_by_inclusive_period() -> None:
    # Given
    request = ReconciliationRequest(date(2026, 8, 14), date(2026, 8, 15), Path("erp.xls"))
    notices = (
        DepositNotice("before", date(2026, 8, 13), "Before", 1, "before", datetime(2026, 8, 14)),
        DepositNotice("inside", date(2026, 8, 15), "Inside", 1, "inside", datetime(2026, 8, 15)),
        DepositNotice("after", date(2026, 8, 16), "After", 1, "after", datetime(2026, 8, 15)),
        UnparsedDepositNotice("unparsed-before", datetime(2026, 8, 13, 23, 59), "old", "old"),
    )
    registrations = (
        ErpRegistration(2, date(2026, 8, 13), "Before", None, False),
        ErpRegistration(3, date(2026, 8, 15), "Inside", None, False),
        ErpRegistration(4, date(2026, 8, 16), "After", None, False),
    )
    service = ReceivablesReconciliationService(
        FakeOutlookReader(notices),
        lambda path: registrations,
    )

    # When
    report = service.run(request)

    # Then
    assert report.summary.total_candidates == 1
    assert report.summary.erp_registration_count == 1
    assert report.summary.registered_count == 1
    assert report.actionable_rows == ()


def test_run_rejects_reversed_date_range_before_reading_sources() -> None:
    # Given
    request = ReconciliationRequest(date(2026, 8, 15), date(2026, 8, 14), Path("erp.xls"))
    service = ReceivablesReconciliationService(FakeOutlookReader(()), lambda path: ())

    # When / Then
    with pytest.raises(ReconciliationPipelineError, match="시작일은 종료일보다 늦을 수 없습니다"):
        service.run(request)
