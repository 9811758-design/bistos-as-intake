from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Final


class SheetField(IntEnum):
    SERVICE_NUMBER = 0
    RECEIPT_MONTH = 1
    RECEIVER = 2
    REGION = 3
    REQUESTER = 4
    HOSPITAL = 5
    REQUESTER_CONTACT = 6
    MODEL = 7
    SERIAL_NUMBER = 8
    PRODUCTION_MONTH = 9
    WARRANTY = 10
    INITIAL_FAILURE = 11
    REQUESTED_ITEM = 12
    INBOUND_STATUS = 13
    DEFECT_CATEGORY = 14
    SYMPTOM = 15
    COMPLAINT = 16
    PROCESSOR = 17
    FAILURE_CAUSE = 18
    ACTION = 19
    RESULT = 20
    COMPLETION_DATE = 21
    COMPLETION_MONTH = 22
    VALIDATION = 23
    ERP_MATERIAL_DATE = 24
    BILLED_AMOUNT = 25
    INVOICE_DATE = 26
    PAID_AMOUNT = 27
    EXPECTED_OR_PAID_DATE = 28
    ERP_PAYMENT_DATE = 29
    NOTE = 30
    SPACER = 31
    TRACKING_NUMBER = 32
    SHIPPING_COST = 33
    OTHER_COST = 34
    CLOSE_STATUS = 35


class FormSection(Enum):
    RECEIPT = "접수정보"
    PROCESSING = "처리정보"
    COST_NOTE = "비용·비고"


@dataclass(frozen=True, slots=True)
class FieldSpec:
    field: SheetField
    label: str
    section: FormSection
    options: tuple[str, ...] = ()
    multiline: bool = False


def _spec(
    field: SheetField,
    label: str,
    section: FormSection,
    *,
    options: tuple[str, ...] = (),
    multiline: bool = False,
) -> FieldSpec:
    return FieldSpec(field, label, section, options, multiline)


FORM_SPECS: Final = (
    _spec(SheetField.RECEIVER, "접수자", FormSection.RECEIPT),
    _spec(SheetField.REGION, "지역", FormSection.RECEIPT),
    _spec(SheetField.REQUESTER, "의뢰자(고객/영업담당자)", FormSection.RECEIPT),
    _spec(SheetField.HOSPITAL, "병원명", FormSection.RECEIPT),
    _spec(SheetField.REQUESTER_CONTACT, "의뢰자 연락처", FormSection.RECEIPT),
    _spec(SheetField.MODEL, "Model", FormSection.RECEIPT),
    _spec(SheetField.SERIAL_NUMBER, "Serial Number", FormSection.RECEIPT),
    _spec(SheetField.PRODUCTION_MONTH, "생산년월", FormSection.RECEIPT),
    _spec(SheetField.WARRANTY, "보증기간", FormSection.RECEIPT, options=("내", "외", "N/A")),
    _spec(SheetField.INITIAL_FAILURE, "초기불량", FormSection.RECEIPT, options=("Y", "N")),
    _spec(SheetField.REQUESTED_ITEM, "의뢰물품 내역/수량", FormSection.RECEIPT),
    _spec(SheetField.INBOUND_STATUS, "물품 입고여부(입고일)", FormSection.RECEIPT),
    _spec(SheetField.DEFECT_CATEGORY, "불량대분류", FormSection.RECEIPT),
    _spec(SheetField.SYMPTOM, "증상/요청사항", FormSection.RECEIPT, multiline=True),
    _spec(SheetField.COMPLAINT, "불만여부", FormSection.RECEIPT, options=("X", "O")),
    _spec(SheetField.PROCESSOR, "처리자", FormSection.PROCESSING),
    _spec(SheetField.FAILURE_CAUSE, "불량원인", FormSection.PROCESSING, multiline=True),
    _spec(SheetField.ACTION, "대응조치", FormSection.PROCESSING, multiline=True),
    _spec(SheetField.RESULT, "처리결과", FormSection.PROCESSING, options=("OK", "NG", "N/A")),
    _spec(SheetField.COMPLETION_DATE, "처리완료일", FormSection.PROCESSING),
    _spec(SheetField.COMPLETION_MONTH, "처리완료월", FormSection.PROCESSING),
    _spec(SheetField.VALIDATION, "서비스(A/S) 후 검증", FormSection.PROCESSING),
    _spec(SheetField.ERP_MATERIAL_DATE, "ERP 자재출고 입력일", FormSection.PROCESSING),
    _spec(SheetField.INVOICE_DATE, "ERP 계산서 발행일", FormSection.PROCESSING),
    _spec(SheetField.EXPECTED_OR_PAID_DATE, "입금예정일 / 입금일", FormSection.PROCESSING),
    _spec(SheetField.ERP_PAYMENT_DATE, "ERP 수금 입력일", FormSection.PROCESSING),
    _spec(SheetField.BILLED_AMOUNT, "청구금액", FormSection.COST_NOTE),
    _spec(SheetField.PAID_AMOUNT, "입금액", FormSection.COST_NOTE),
    _spec(SheetField.NOTE, "비고", FormSection.COST_NOTE, multiline=True),
    _spec(SheetField.TRACKING_NUMBER, "운송장", FormSection.COST_NOTE),
    _spec(SheetField.SHIPPING_COST, "운송비", FormSection.COST_NOTE),
    _spec(SheetField.OTHER_COST, "기타비용", FormSection.COST_NOTE),
    _spec(SheetField.CLOSE_STATUS, "종료상태", FormSection.COST_NOTE, options=("", "종료")),
)

SEARCH_FIELDS: Final = (
    SheetField.SERVICE_NUMBER,
    SheetField.REQUESTER,
    SheetField.REQUESTER_CONTACT,
    SheetField.HOSPITAL,
    SheetField.MODEL,
    SheetField.SERIAL_NUMBER,
    SheetField.SYMPTOM,
)

COLUMN_COUNT: Final = 36
