from dataclasses import replace
from pathlib import Path

from openpyxl import load_workbook

from service_validation.domain import classify_customer
from service_validation.report_writer import generate_workbook
from service_validation.workbook import read_source

SOURCE = Path(r"C:\Users\User\Downloads\엑셀시트.xlsx")
TEMPLATE = Path(r"C:\Users\User\Downloads\서비스검증결과서 양식.xlsx")


def test_generate_workbook_marks_dealer_when_company_and_hospital_are_present(
    tmp_path: Path,
) -> None:
    # Given: 임의 업체가 병원 고객을 의뢰한 서비스 기록
    base = next(
        record
        for record in read_source(SOURCE).records
        if record.service_number == "DS26070601"
    )
    record = replace(
        base,
        requester="세진",
        hospital="새봄병원",
        customer=classify_customer("세진", "새봄병원"),
    )

    # When: 실제 검증결과서 양식으로 파일을 생성한다
    output = generate_workbook(TEMPLATE, tmp_path, record)

    # Then: 고객 구분은 대리점으로 체크되고 파일명에도 고객명이 유지된다
    workbook = load_workbook(output, data_only=True)
    sheet = workbook["BT380"]
    assert sheet["O5"].value == "■대리점      □병원      □개인고객"
    assert sheet["BE5"].value == "세진(새봄병원)"
    assert output.name == "서비스검증결과서_DS26070601_세진(새봄병원).xlsx"
    workbook.close()
