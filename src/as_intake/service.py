from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Final, Protocol

from .analytics import AnalyticsDateRange, AnalyticsReport, build_analytics_report
from .columns import SEARCH_FIELDS, SheetField
from .errors import GoogleRequestError
from .numbering import next_service_number, service_number_date
from .policy import NO_PRODUCTION_MONTH_STATUS, is_bcm_model
from .recommendation import (
    CaseRecommendation,
    RecommendationQuery,
    RecommendationReport,
    recommend_cases,
)
from .records import RecordDraft, SheetRow

if TYPE_CHECKING:
    from .feedback import RecommendationFeedbackStore

_MISSING_RANGE_ERROR_MARKER: Final = "Unable to parse range"
_HTTP_BAD_REQUEST_MARKER: Final = "Google Sheets API 오류 400:"


class SheetGateway(Protocol):
    def read_rows(self, year: int) -> tuple[SheetRow, ...]: ...

    def insert_row(self, year: int, row: SheetRow) -> SheetRow: ...

    def overwrite_row(self, year: int, row_number: int, row: SheetRow) -> SheetRow: ...


class ServiceRecordNotFoundError(LookupError):
    pass


class DuplicateServiceNumberError(LookupError):
    pass


class InvalidServiceNumberError(ValueError):
    pass


class ServiceAnalyticsReadError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class SearchQuery:
    year: int
    text: str = ""
    close_status: str = ""
    start_date: date | None = None
    end_date: date | None = None


class ASIntakeService:
    def __init__(
        self,
        gateway: SheetGateway,
        feedback: RecommendationFeedbackStore | None = None,
    ) -> None:
        self._gateway = gateway
        self._feedback = feedback

    def register(self, draft: RecordDraft) -> SheetRow:
        rows = self._gateway.read_rows(draft.receipt_date.year)
        existing = tuple(row.value(SheetField.SERVICE_NUMBER) for row in rows)
        model = draft.values[SheetField.MODEL]
        service_number = (
            draft.receipt_date.strftime("%Y.%m.%d")
            if is_bcm_model(model)
            else next_service_number(draft.receipt_date, existing)
        )
        row = _apply_model_defaults(draft.to_sheet_row(service_number))
        return self._gateway.insert_row(
            draft.receipt_date.year,
            row,
        )

    def search(self, query: SearchQuery) -> tuple[SheetRow, ...]:
        text = query.text.strip().casefold()
        filters_by_date = query.start_date is not None or query.end_date is not None
        matches = []
        for row in self._gateway.read_rows(query.year):
            if text and not any(text in row.value(field).casefold() for field in SEARCH_FIELDS):
                continue
            if query.close_status and row.value(SheetField.CLOSE_STATUS) != query.close_status:
                continue
            if filters_by_date:
                receipt_date = service_number_date(row.value(SheetField.SERVICE_NUMBER))
                if query.start_date is not None and (
                    receipt_date is None or receipt_date < query.start_date
                ):
                    continue
                if query.end_date is not None and (
                    receipt_date is None or receipt_date > query.end_date
                ):
                    continue
            matches.append(row)
        return tuple(matches)

    def recommend(self, query: RecommendationQuery) -> RecommendationReport:
        rows = self._gateway.read_rows(query.year)
        feedback_counts = self._feedback.counts() if self._feedback is not None else None
        return recommend_cases(rows, query, feedback_counts)

    def learn_from_recommendation(self, recommendation: CaseRecommendation) -> bool:
        if self._feedback is None:
            return False
        self._feedback.record(recommendation.source)
        return True

    def analytics_report(
        self,
        start_date: date,
        end_date: date,
        *,
        today: date,
    ) -> AnalyticsReport:
        date_range = AnalyticsDateRange(start_date, end_date)
        rows: list[SheetRow] = []
        for year in range(start_date.year, end_date.year + 1):
            try:
                rows.extend(self._gateway.read_rows(year))
            except GoogleRequestError as exc:
                if not _is_missing_range_error(exc):
                    raise
                raise ServiceAnalyticsReadError(
                    f"{year}년 Google 시트 탭을 읽을 수 없습니다."
                ) from exc
            except LookupError as exc:
                raise ServiceAnalyticsReadError(
                    f"{year}년 Google 시트 탭을 읽을 수 없습니다."
                ) from exc
        return build_analytics_report(rows, date_range, today)

    def current_year_overdue_report(self, *, today: date) -> AnalyticsReport:
        return self.analytics_report(date(today.year, 1, 1), today, today=today)

    def update(self, original_service_number: str, changed: SheetRow) -> SheetRow:
        year = _infer_year(original_service_number)
        matches = tuple(
            row
            for row in self._gateway.read_rows(year)
            if row.value(SheetField.SERVICE_NUMBER) == original_service_number
        )
        if not matches:
            raise ServiceRecordNotFoundError(
                f"서비스번호 {original_service_number} 행을 찾을 수 없습니다."
            )
        matched_row = _resolve_update_row(
            original_service_number,
            matches,
            changed.row_number,
        )
        row_number = matched_row.row_number
        if row_number is None:
            raise ServiceRecordNotFoundError("Google 시트 행 번호가 없습니다.")
        preserved_key = _apply_model_defaults(
            changed.with_value(SheetField.SERVICE_NUMBER, original_service_number)
        )
        return self._gateway.overwrite_row(year, row_number, preserved_key)


def _resolve_update_row(
    service_number: str,
    matches: tuple[SheetRow, ...],
    selected_row_number: int | None,
) -> SheetRow:
    if not matches:
        raise ServiceRecordNotFoundError(
            f"서비스번호 {service_number} 행을 찾을 수 없습니다."
        )
    if selected_row_number is not None:
        selected = tuple(row for row in matches if row.row_number == selected_row_number)
        if len(selected) == 1:
            return selected[0]
        raise ServiceRecordNotFoundError(
            f"서비스번호 {service_number}의 선택한 행을 다시 찾을 수 없습니다."
        )
    if len(matches) > 1:
        raise DuplicateServiceNumberError(
            f"서비스번호 {service_number}가 {len(matches)}개 있습니다."
        )
    return next(iter(matches))


def _apply_model_defaults(row: SheetRow) -> SheetRow:
    if not is_bcm_model(row.value(SheetField.MODEL)):
        return row
    return row.with_value(
        SheetField.SERIAL_NUMBER,
        NO_PRODUCTION_MONTH_STATUS,
    ).with_value(
        SheetField.PRODUCTION_MONTH,
        NO_PRODUCTION_MONTH_STATUS,
    )


def _infer_year(service_number: str) -> int:
    parsed_date = service_number_date(service_number)
    if parsed_date is not None:
        return parsed_date.year
    legacy_match = re.match(r"^(?P<year>20\d{2})", service_number.strip())
    if legacy_match is not None:
        return int(legacy_match.group("year"))
    raise InvalidServiceNumberError(f"연도를 확인할 수 없습니다: {service_number}")


def _is_missing_range_error(error: GoogleRequestError) -> bool:
    message = str(error)
    return (
        _HTTP_BAD_REQUEST_MARKER in message
        and _MISSING_RANGE_ERROR_MARKER in message
    )
