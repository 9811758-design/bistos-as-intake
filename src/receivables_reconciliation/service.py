from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Protocol, assert_never

from receivables_reconciliation.erp_xls import ErpXlsError, read_erp_registrations
from receivables_reconciliation.matching import reconcile
from receivables_reconciliation.models import (
    DepositNotice,
    ErpRegistration,
    MatchResult,
    MatchStatus,
    UnparsedDepositNotice,
)
from receivables_reconciliation.outlook_reader import (
    MissingOutlookProfileError,
    OutlookActivationDeniedError,
    OutlookComUnavailableError,
)

NoticeCandidate = DepositNotice | UnparsedDepositNotice
RegistrationReader = Callable[[Path], Sequence[ErpRegistration]]


class OutlookNoticeReader(Protocol):
    def read(
        self,
        start_date: date,
        end_date: date,
    ) -> tuple[NoticeCandidate, ...]: ...


@dataclass(frozen=True, slots=True)
class ReconciliationRequest:
    start_date: date
    end_date: date
    erp_path: Path


@dataclass(frozen=True, slots=True)
class ReconciliationSummary:
    total_candidates: int
    erp_registration_count: int
    registered_count: int
    unregistered_count: int
    review_needed_count: int
    unparsed_count: int
    actionable_count: int


@dataclass(frozen=True, slots=True)
class ReconciliationRow:
    status: MatchStatus
    message_id: str
    deposit_date: date | None
    depositor_name: str
    amount: int | None
    subject: str
    received_at: datetime
    reason: str


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    request: ReconciliationRequest
    summary: ReconciliationSummary
    actionable_rows: tuple[ReconciliationRow, ...]
    source_erp_path: Path


@dataclass(frozen=True, slots=True)
class ReconciliationPipelineError(Exception):
    stage: str
    detail: str

    def __str__(self) -> str:
        return f"{self.stage} 자료를 읽을 수 없습니다: {self.detail}"


class ReceivablesReconciliationService:
    def __init__(
        self,
        outlook_reader: OutlookNoticeReader,
        erp_reader: RegistrationReader = read_erp_registrations,
    ) -> None:
        self._outlook_reader = outlook_reader
        self._erp_reader = erp_reader

    def run(self, request: ReconciliationRequest) -> ReconciliationReport:
        if request.start_date > request.end_date:
            raise ReconciliationPipelineError("조회 기간", "시작일은 종료일보다 늦을 수 없습니다.")
        notices = self._read_outlook(request)
        registrations = self._read_erp(request)
        parsed_notices, unparsed_notices = _partition_notices(notices)
        match_results = reconcile(parsed_notices, registrations)
        actionable_rows = (
            *tuple(
                _row_from_match(result)
                for result in match_results
                if _is_actionable(result)
            ),
            *tuple(_row_from_unparsed(notice) for notice in unparsed_notices),
        )
        return ReconciliationReport(
            request=request,
            summary=_summary(
                match_results,
                unparsed_notices,
                actionable_rows,
                erp_registration_count=len(registrations),
            ),
            actionable_rows=actionable_rows,
            source_erp_path=request.erp_path,
        )

    def _read_outlook(self, request: ReconciliationRequest) -> tuple[NoticeCandidate, ...]:
        try:
            raw_notices = self._outlook_reader.read(request.start_date, request.end_date)
        except (
            MissingOutlookProfileError,
            OutlookActivationDeniedError,
            OutlookComUnavailableError,
        ) as error:
            raise ReconciliationPipelineError("Outlook", str(error)) from error
        return tuple(notice for notice in raw_notices if _notice_in_period(request, notice))

    def _read_erp(self, request: ReconciliationRequest) -> tuple[ErpRegistration, ...]:
        try:
            registrations = self._erp_reader(request.erp_path)
        except ErpXlsError as error:
            raise ReconciliationPipelineError("ERP", str(error)) from error
        return tuple(
            registration
            for registration in registrations
            if _date_in_period(request, registration.receipt_date)
        )


def _partition_notices(
    notices: tuple[NoticeCandidate, ...],
) -> tuple[tuple[DepositNotice, ...], tuple[UnparsedDepositNotice, ...]]:
    parsed: list[DepositNotice] = []
    unparsed: list[UnparsedDepositNotice] = []
    for notice in notices:
        match notice:
            case DepositNotice():
                parsed.append(notice)
            case UnparsedDepositNotice():
                unparsed.append(notice)
            case unreachable:
                assert_never(unreachable)
    return (tuple(parsed), tuple(unparsed))


def _notice_in_period(request: ReconciliationRequest, notice: NoticeCandidate) -> bool:
    match notice:
        case DepositNotice(deposit_date=deposit_date):
            return _date_in_period(request, deposit_date)
        case UnparsedDepositNotice(received_at=received_at):
            return _date_in_period(request, received_at.date())
        case unreachable:
            assert_never(unreachable)


def _date_in_period(request: ReconciliationRequest, value: date) -> bool:
    return request.start_date <= value <= request.end_date


def _is_actionable(result: MatchResult) -> bool:
    match result.status:
        case MatchStatus.REGISTERED:
            return False
        case MatchStatus.UNREGISTERED | MatchStatus.REVIEW_NEEDED:
            return True
        case unreachable:
            assert_never(unreachable)


def _row_from_match(result: MatchResult) -> ReconciliationRow:
    notice = result.notice
    return ReconciliationRow(
        status=result.status,
        message_id=notice.message_id,
        deposit_date=notice.deposit_date,
        depositor_name=notice.depositor_name,
        amount=notice.amount,
        subject=notice.subject,
        received_at=notice.received_at,
        reason=result.reason,
    )


def _row_from_unparsed(notice: UnparsedDepositNotice) -> ReconciliationRow:
    return ReconciliationRow(
        status=MatchStatus.REVIEW_NEEDED,
        message_id=notice.message_id,
        deposit_date=None,
        depositor_name="",
        amount=None,
        subject=notice.subject,
        received_at=notice.received_at,
        reason=notice.reason,
    )


def _summary(
    results: tuple[MatchResult, ...],
    unparsed_notices: tuple[UnparsedDepositNotice, ...],
    actionable_rows: tuple[ReconciliationRow, ...],
    *,
    erp_registration_count: int,
) -> ReconciliationSummary:
    registered = _count_status(results, MatchStatus.REGISTERED)
    unregistered = _count_status(results, MatchStatus.UNREGISTERED)
    review_needed = _count_status(results, MatchStatus.REVIEW_NEEDED) + len(unparsed_notices)
    return ReconciliationSummary(
        total_candidates=len(results) + len(unparsed_notices),
        erp_registration_count=erp_registration_count,
        registered_count=registered,
        unregistered_count=unregistered,
        review_needed_count=review_needed,
        unparsed_count=len(unparsed_notices),
        actionable_count=len(actionable_rows),
    )


def _count_status(results: tuple[MatchResult, ...], status: MatchStatus) -> int:
    return sum(1 for result in results if result.status == status)
