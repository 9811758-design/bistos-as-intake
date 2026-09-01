from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from .domain import (
    DEFAULT_COMPANY_KEYWORDS,
    CustomerClass,
    ServiceRecord,
    ValidationError,
    classify_customer,
    parse_completion_date,
    parse_receipt_date,
)
from .validation_rules import build_validation_plan

RawDate = str | int | float | date | datetime


class CustomerConfigLike(Protocol):
    @property
    def overrides(self) -> dict[str, CustomerClass]: ...

    @property
    def company_keywords(self) -> tuple[str, ...]: ...


@dataclass(frozen=True, slots=True)
class RecordFields:
    service_number: str
    receiver: str
    requester: str
    hospital: str
    model: str
    defect_category: str
    service_details: str
    processing_details: str
    processor: str
    completion_date: RawDate
    completion_month: str


def build_service_record(
    fields: RecordFields,
    config: CustomerConfigLike | None = None,
) -> ServiceRecord:
    service_number = fields.service_number.strip()
    receipt_date = parse_receipt_date(service_number)
    requester = fields.requester.strip()
    hospital = fields.hospital.strip()
    keywords = config.company_keywords if config and config.company_keywords else None
    customer = classify_customer(
        requester,
        hospital,
        keywords=keywords or DEFAULT_COMPANY_KEYWORDS,
        override=config.overrides.get(requester) if config else None,
    )
    completion_date = parse_completion_date(fields.completion_date, receipt_date.year)
    month = fields.completion_month.strip().replace("월", "")
    if month.isdigit() and int(month) != completion_date.month:
        raise ValidationError(f"{service_number}: 처리완료월과 처리완료일이 일치하지 않습니다.")
    record = ServiceRecord(
        service_number=service_number,
        receipt_date=receipt_date,
        receiver=fields.receiver.strip(),
        requester=requester,
        hospital=hospital,
        customer=customer,
        model=fields.model.strip(),
        defect_category=fields.defect_category.strip(),
        service_details=fields.service_details.strip(),
        processing_details=fields.processing_details.strip(),
        completion_date=completion_date,
        processor=fields.processor.strip(),
    )
    build_validation_plan(record)
    return record
