from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final

from openpyxl.utils.datetime import from_excel


class CustomerClass(StrEnum):
    DEALER = "대리점"
    HOSPITAL = "병원"
    PERSONAL = "개인고객"


@dataclass(frozen=True, slots=True)
class Customer:
    category: CustomerClass
    display_name: str


@dataclass(frozen=True, slots=True)
class ServiceRecord:
    service_number: str
    receipt_date: date
    receiver: str
    requester: str
    hospital: str
    customer: Customer
    model: str
    defect_category: str
    service_details: str
    processing_details: str
    completion_date: date
    processor: str


class ValidationError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message


DEFAULT_COMPANY_KEYWORDS: Final = (
    "메디칼",
    "메디컬",
    "메디렌",
    "의료",
    "상사",
    "산업",
    "주식회사",
    "(주)",
    "센터",
    "병원",
    "대리점",
)
SERVICE_NUMBER_PATTERN: Final = re.compile(r"^DS(?P<date>\d{6})(?P<seq>\d{2})$")
INVALID_FILENAME: Final = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value).strip()


def parse_receipt_date(service_number: str) -> date:
    match = SERVICE_NUMBER_PATTERN.fullmatch(service_number.strip())
    if match is None:
        raise ValidationError("서비스번호는 DSYYMMDDNN 형식이어야 합니다.")
    try:
        return datetime.strptime(match.group("date"), "%y%m%d").date()
    except ValueError as exc:
        raise ValidationError("서비스번호의 날짜가 올바르지 않습니다.") from exc


def parse_completion_date(value: str | int | float | date | datetime, receipt_year: int) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        parsed = from_excel(value)
        return parsed.date() if isinstance(parsed, datetime) else parsed
    raw = str(value).strip()
    for pattern in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, pattern).date()
        except ValueError:
            continue
    try:
        return datetime.strptime(f"{receipt_year}/{raw}", "%Y/%m/%d").date()
    except ValueError as exc:
        raise ValidationError("처리완료일을 날짜로 해석할 수 없습니다.") from exc


def classify_customer(
    requester: str,
    hospital: str,
    keywords: tuple[str, ...] = DEFAULT_COMPANY_KEYWORDS,
    override: CustomerClass | None = None,
) -> Customer:
    requester = requester.strip()
    hospital = hospital.strip()
    if override is not None:
        category = override
    elif "개인고객" in requester or "개인고객" in hospital:
        category = CustomerClass.PERSONAL
        requester = requester.replace("(개인고객)", "").replace("개인고객", "").strip()
        hospital = hospital.replace("(개인고객)", "").replace("개인고객", "").strip()
    elif hospital:
        category = CustomerClass.DEALER if requester else CustomerClass.HOSPITAL
    elif requester and any(keyword in requester for keyword in keywords):
        category = CustomerClass.DEALER
    elif requester and re.fullmatch(r"[가-힣]{2,4}\d*", requester):
        category = CustomerClass.PERSONAL
    else:
        raise ValidationError("고객 구분을 확정할 수 없습니다. 설정의 예외 규칙을 확인하세요.")
    if category is CustomerClass.PERSONAL:
        display = f"{requester}(개인고객)"
    elif hospital and requester:
        display = f"{requester}({hospital})"
    else:
        display = hospital or requester
    return Customer(category=category, display_name=display)


def safe_filename(record: ServiceRecord) -> str:
    name = f"서비스검증결과서_{record.service_number}_{record.customer.display_name}.xlsx"
    cleaned = INVALID_FILENAME.sub("", name).rstrip(" .")
    if not cleaned:
        raise ValidationError("출력 파일명을 만들 수 없습니다.")
    return cleaned


def unique_output_path(folder: Path, filename: str) -> Path:
    candidate = folder / filename
    counter = 2
    while candidate.exists():
        candidate = folder / f"{Path(filename).stem} ({counter}){Path(filename).suffix}"
        counter += 1
    return candidate
