from pathlib import Path

import pytest

from service_validation.domain import CustomerClass, ValidationError
from service_validation.pasted_row import parse_pasted_row
from service_validation.workbook import load_overrides

SAMPLE_ROW = (
    "DS26070601\t7월\t장진영\t\t국제메디칼\t미즈피아병원\t010-2377-3710\t"
    "BT380\tAKRB0021\t25년11월\t내\tN\tBT380 1개\t입고(7/2)\t화면불량\t"
    "화면이나오지 않음\tX\t장진영\t화면불량\tDisplay cable 교체\tOK\t7/6\t7"
)


def test_parse_pasted_row_builds_existing_service_record() -> None:
    # Given: 구글시트에서 복사한 한 행
    # When: 빠른 발행 입력으로 해석
    record = parse_pasted_row(SAMPLE_ROW)

    # Then: 기존 생성기가 사용하는 동일한 도메인 값이 만들어진다.
    assert record.service_number == "DS26070601"
    assert record.receipt_date.isoformat() == "2026-07-06"
    assert record.customer.category is CustomerClass.DEALER
    assert record.customer.display_name == "국제메디칼(미즈피아병원)"
    assert record.model == "BT380"
    assert record.service_details == "화면이나오지 않음"
    assert record.processing_details == "Display cable 교체"
    assert record.completion_date.isoformat() == "2026-07-06"


def test_parse_pasted_row_uses_customer_override(tmp_path: Path) -> None:
    # Given: 의뢰자를 병원으로 고정한 기존 예외 설정
    config_path = tmp_path / "customer_overrides.json"
    config_path.write_text('{"overrides":{"국제메디칼":"병원"}}', encoding="utf-8")

    # When: 같은 행을 설정과 함께 해석
    record = parse_pasted_row(SAMPLE_ROW, load_overrides(config_path))

    # Then: 임의 재판단 없이 기존 예외 설정을 따른다.
    assert record.customer.category is CustomerClass.HOSPITAL


def test_parse_pasted_row_classifies_personal_marker_in_hospital_column() -> None:
    # Given: 개인고객 표식이 병원명 열에 들어간 실제 구글시트 행
    cells = SAMPLE_ROW.split("\t")
    cells[4] = "이나경"
    cells[5] = "개인고객"

    # When: 빠른 발행 입력으로 해석
    record = parse_pasted_row("\t".join(cells))

    # Then: 병원이 아니라 개인고객으로 분류한다.
    assert record.customer.category is CustomerClass.PERSONAL
    assert record.customer.display_name == "이나경(개인고객)"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (SAMPLE_ROW + "\n" + SAMPLE_ROW, "한 행만"),
        ("DS26070601\t7월\t장진영", "23개 열"),
        ("", "붙여넣으세요"),
    ],
)
def test_parse_pasted_row_rejects_invalid_clipboard_shape(text: str, message: str) -> None:
    # Given: 한 행 전체가 아닌 붙여넣기 데이터
    # When / Then: 생성 전에 구체적인 입력 오류로 차단한다.
    with pytest.raises(ValidationError, match=message):
        parse_pasted_row(text)
