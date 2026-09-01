from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Final, Literal, TypeAlias, assert_never

import xlrd

from .models import ErpRegistration

CellValue: TypeAlias = bool | float | int | str
HeaderName: TypeAlias = Literal["receipt_date", "customer", "note"]

PERSONAL_MARKERS: Final[frozenset[str]] = frozenset({"개인고객", "개인매출"})
REQUIRED_HEADERS: Final[tuple[HeaderName, ...]] = ("receipt_date", "customer", "note")
DATE_SEPARATORS: Final[re.Pattern[str]] = re.compile(r"[./-]")
HEADER_ALIASES: Final[dict[str, HeaderName]] = {
    "수금일자": "receipt_date",
    "고객": "customer",
    "거래처": "customer",
    "거래처명": "customer",
    "거래처코드명": "customer",
    "거래처코드명칭": "customer",
    "비고": "note",
    "참조비고": "note",
}


class ErpXlsError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ErpXlsFileError(ErpXlsError):
    path: Path
    reason: str

    def __str__(self) -> str:
        return f"ERP 엑셀 파일을 읽을 수 없습니다: {self.path} ({self.reason})"


@dataclass(frozen=True, slots=True)
class ErpXlsHeaderError(ErpXlsError):
    sheet_name: str
    message: str

    def __str__(self) -> str:
        return f"ERP 엑셀 필수 헤더 오류: {self.sheet_name} - {self.message}"


@dataclass(frozen=True, slots=True)
class ErpXlsCellError(ErpXlsError):
    sheet_name: str
    row_number: int
    header: str
    value: str

    def __str__(self) -> str:
        return (
            f"ERP 엑셀 셀 오류: {self.sheet_name} {self.row_number}행 {self.header}={self.value!r}"
        )


@dataclass(frozen=True, slots=True)
class HeaderSelection:
    sheet_name: str
    header_row_index: int
    columns: dict[HeaderName, int]


@dataclass(frozen=True, slots=True)
class CellContext:
    sheet_name: str
    row_number: int
    header: str


def read_erp_registrations(
    path: str | Path,
    *,
    sheet_name: str | None = None,
) -> list[ErpRegistration]:
    workbook_path = Path(path)
    workbook = _open_workbook(workbook_path)
    sheet_names = (sheet_name,) if sheet_name is not None else tuple(workbook.sheet_names())

    for candidate_name in sheet_names:
        try:
            sheet = workbook.sheet_by_name(candidate_name)
        except xlrd.biffh.XLRDError as error:
            raise ErpXlsHeaderError(candidate_name, "시트를 찾을 수 없습니다") from error

        selection = _find_header(sheet)
        if selection is None:
            if sheet_name is not None:
                raise ErpXlsHeaderError(
                    candidate_name,
                    "필수 헤더가 없습니다: 수금일자, 고객, 비고",
                )
            continue

        return _parse_sheet(sheet, selection)

    raise ErpXlsHeaderError(", ".join(sheet_names), "필수 헤더가 없습니다: 수금일자, 고객, 비고")


def _open_workbook(path: Path):
    try:
        return xlrd.open_workbook(str(path), on_demand=True)
    except FileNotFoundError as error:
        raise ErpXlsFileError(path, "파일이 없습니다") from error
    except PermissionError as error:
        raise ErpXlsFileError(path, "접근 권한이 없습니다") from error
    except xlrd.biffh.XLRDError as error:
        raise ErpXlsFileError(path, "손상되었거나 지원하지 않는 .xls 형식입니다") from error


def _find_header(sheet) -> HeaderSelection | None:
    for row_index in range(sheet.nrows):
        columns = _semantic_columns(sheet.row_values(row_index))
        if _has_all_required(columns):
            return HeaderSelection(sheet.name, row_index, columns)
    return None


def _semantic_columns(values: list[CellValue]) -> dict[HeaderName, int]:
    columns: dict[HeaderName, int] = {}
    duplicates: list[str] = []
    for column_index, value in enumerate(values):
        header = _semantic_header(_cell_text(value))
        if header is None:
            continue
        if header in columns:
            duplicates.append(_display_header(header))
            continue
        columns[header] = column_index
    if duplicates:
        duplicate_names = ", ".join(sorted(set(duplicates)))
        raise ErpXlsHeaderError("헤더 행", f"중복 필수 헤더: {duplicate_names}")
    return columns


def _has_all_required(columns: dict[HeaderName, int]) -> bool:
    return all(header in columns for header in REQUIRED_HEADERS)


def _parse_sheet(sheet, selection: HeaderSelection) -> list[ErpRegistration]:
    registrations: list[ErpRegistration] = []
    for row_index in range(selection.header_row_index + 1, sheet.nrows):
        values = sheet.row_values(row_index)
        if _is_blank_row(values):
            continue
        row_number = row_index + 1
        receipt_date = _parse_receipt_date(
            _cell_value(values, selection.columns["receipt_date"]),
            CellContext(selection.sheet_name, row_number, "수금일자"),
        )
        customer_name = _cell_text(_cell_value(values, selection.columns["customer"]))
        note = _cell_text(_cell_value(values, selection.columns["note"]))
        if customer_name == "":
            continue
        is_personal = customer_name in PERSONAL_MARKERS
        registrations.append(
            ErpRegistration(
                row_number=row_number,
                receipt_date=receipt_date,
                customer_name=customer_name,
                depositor_name=_depositor_name(customer_name, note),
                is_personal=is_personal,
            )
        )
    return registrations


def _parse_receipt_date(value: CellValue, context: CellContext) -> date:
    match value:
        case bool():
            raise ErpXlsCellError(
                context.sheet_name,
                context.row_number,
                context.header,
                str(value),
            )
        case int() | float():
            try:
                return xlrd.xldate.xldate_as_datetime(float(value), 0).date()
            except xlrd.xldate.XLDateError as error:
                raise ErpXlsCellError(
                    context.sheet_name,
                    context.row_number,
                    context.header,
                    str(value),
                ) from error
        case str():
            return _parse_receipt_date_text(value, context)
        case unreachable:
            assert_never(unreachable)


def _parse_receipt_date_text(value: str, context: CellContext) -> date:
    text = value.strip()
    compact = text if text.isdecimal() else DATE_SEPARATORS.sub("", text)
    if len(compact) != 8 or not compact.isdecimal():
        raise ErpXlsCellError(context.sheet_name, context.row_number, context.header, value)
    try:
        return datetime.strptime(compact, "%Y%m%d").date()
    except ValueError as error:
        raise ErpXlsCellError(
            context.sheet_name,
            context.row_number,
            context.header,
            value,
        ) from error


def _depositor_name(customer_name: str, note: str) -> str | None:
    if customer_name not in PERSONAL_MARKERS:
        return customer_name
    if "/" not in note:
        return None
    final_segment = note.rsplit("/", maxsplit=1)[-1].strip()
    return final_segment or None


def _cell_value(values: list[CellValue], column_index: int) -> CellValue:
    if column_index >= len(values):
        return ""
    return values[column_index]


def _is_blank_row(values: list[CellValue]) -> bool:
    return all(_cell_text(value) == "" for value in values)


def _cell_text(value: CellValue) -> str:
    match value:
        case str():
            return value.strip()
        case int() | float():
            if float(value).is_integer():
                return str(int(value))
            return str(value).strip()
        case bool():
            return str(value)
        case unreachable:
            assert_never(unreachable)


def _semantic_header(value: str) -> HeaderName | None:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    key = re.sub(r"[\s/·._()\-]+", "", normalized)
    return HEADER_ALIASES.get(key)


def _display_header(header: HeaderName) -> str:
    match header:
        case "receipt_date":
            return "수금일자"
        case "customer":
            return "고객"
        case "note":
            return "비고"
        case unreachable:
            assert_never(unreachable)
