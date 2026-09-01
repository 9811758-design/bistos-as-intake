from __future__ import annotations

import csv
from io import StringIO
from typing import Final

from .domain import ServiceRecord, ValidationError
from .record_builder import RecordFields, build_service_record
from .workbook import CustomerConfig

MINIMUM_COLUMN_COUNT: Final = 23


def parse_pasted_row(text: str, config: CustomerConfig | None = None) -> ServiceRecord:
    rows = [
        tuple(cell.strip() for cell in row)
        for row in csv.reader(StringIO(text), delimiter="\t")
        if any(cell.strip() for cell in row)
    ]
    if not rows:
        raise ValidationError("구글시트에서 행 전체를 복사해 붙여넣으세요.")
    if len(rows) != 1:
        raise ValidationError("빠른 발행에는 한 행만 붙여넣을 수 있습니다.")
    row = rows[0]
    if len(row) < MINIMUM_COLUMN_COUNT:
        raise ValidationError(
            f"구글시트 행은 최소 {MINIMUM_COLUMN_COUNT}개 열이어야 합니다. 현재 {len(row)}개입니다."
        )
    return build_service_record(
        RecordFields(
            service_number=row[0],
            receiver=row[2],
            requester=row[4],
            hospital=row[5],
            model=row[7],
            defect_category=row[14],
            service_details=row[15],
            processing_details=row[19],
            processor=row[17],
            completion_date=row[21],
            completion_month=row[22],
        ),
        config,
    )
