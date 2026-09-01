from datetime import date
from pathlib import Path

import pytest

from service_validation.domain import (
    CustomerClass,
    ServiceRecord,
    ValidationError,
    classify_customer,
    parse_completion_date,
    parse_receipt_date,
    safe_filename,
    unique_output_path,
)


def test_parse_receipt_date_when_valid() -> None:
    assert parse_receipt_date("DS26070603") == date(2026, 7, 6)


def test_parse_receipt_date_when_invalid() -> None:
    with pytest.raises(ValidationError):
        parse_receipt_date("DS26073201")


@pytest.mark.parametrize(
    ("requester", "hospital", "category", "display"),
    [
        ("국제메디칼", "미즈피아병원", CustomerClass.DEALER, "국제메디칼(미즈피아병원)"),
        ("메디렌", "000병원", CustomerClass.DEALER, "메디렌(000병원)"),
        ("세진", "새봄병원", CustomerClass.DEALER, "세진(새봄병원)"),
        ("서울병원", "미즈피아병원", CustomerClass.DEALER, "서울병원(미즈피아병원)"),
        ("", "미즈피아병원", CustomerClass.HOSPITAL, "미즈피아병원"),
        ("장진영(개인고객)", "미즈피아병원", CustomerClass.PERSONAL, "장진영(개인고객)"),
        ("장진영", "", CustomerClass.PERSONAL, "장진영(개인고객)"),
    ],
)
def test_classify_customer_when_supported(
    requester: str,
    hospital: str,
    category: CustomerClass,
    display: str,
) -> None:
    customer = classify_customer(requester, hospital)
    assert customer.category is category
    assert customer.display_name == display


def test_parse_completion_date_when_month_day() -> None:
    assert parse_completion_date("7/6", 2026) == date(2026, 7, 6)


def test_unique_output_path_when_duplicate(tmp_path: Path) -> None:
    record = ServiceRecord(
        "DS26070601",
        date(2026, 7, 6),
        "장진영",
        "국제메디칼",
        "미즈피아병원",
        classify_customer("국제메디칼", "미즈피아병원"),
        "BT380",
        "화면불량",
        "화면이나오지 않음",
        "Display cable 교체",
        date(2026, 7, 6),
        "장진영",
    )
    filename = safe_filename(record)
    assert filename == "서비스검증결과서_DS26070601_국제메디칼(미즈피아병원).xlsx"
    (tmp_path / filename).touch()
    assert unique_output_path(tmp_path, filename).name.endswith(" (2).xlsx")
