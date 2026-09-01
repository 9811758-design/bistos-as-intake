from __future__ import annotations

from .columns import SheetField
from .records import SheetRow


class DemoSheetGateway:
    def __init__(self) -> None:
        self.insert_calls = 0
        self.overwrite_calls = 0
        rows = [
            _row(
                "DS26081401",
                "국제메디칼",
                "BT350L",
                "BT350-26001",
                "전원이 간헐적으로 꺼짐",
                "Battery",
                "배터리 교체",
                warranty="내",
            ),
            _row(
                "DS26081601",
                "서울메디칼",
                "BT350L",
                "BT350-26002",
                "충전 불량",
                "Battery",
                "충전 회로 점검",
                warranty="외",
            ),
            _row(
                "DS26081901",
                "부산메디칼",
                "BT200L",
                "BT200-26001",
                "케이블 인식 안 됨",
                "Cable",
                "케이블 교체",
                warranty="내",
            ),
            _row(
                "DS26082001",
                "대전병원",
                "BT220C",
                "BT220-26001",
                "소리 출력 불량",
                "Speaker",
                "스피커 교체",
                completion_date="2026-08-22",
                warranty="내",
            ),
            _row(
                "DS26082301",
                "광주병원",
                "BT700",
                "BT700-26001",
                "부팅 지연",
                "Firmware",
                "펌웨어 업데이트",
                warranty="외",
            ),
            _row(
                "DS26072401",
                "국제메디칼",
                "BT350L",
                "BT350-26003",
                "전원이 간헐적으로 꺼짐",
                "Battery",
                "배터리 교체",
                completion_date="2026-07-30",
                warranty="외",
            ),
        ]
        self.rows = [SheetRow(row.values, row_number=index + 5) for index, row in enumerate(rows)]

    def read_rows(self, year: int) -> tuple[SheetRow, ...]:
        if year != 2026:
            return ()
        return tuple(self.rows)

    def insert_row(self, year: int, row: SheetRow) -> SheetRow:
        self.insert_calls += 1
        shifted = [SheetRow(existing.values, index + 6) for index, existing in enumerate(self.rows)]
        inserted = SheetRow(row.values, row_number=5)
        self.rows = [inserted, *shifted]
        return inserted

    def overwrite_row(self, year: int, row_number: int, row: SheetRow) -> SheetRow:
        self.overwrite_calls += 1
        changed = SheetRow(row.values, row_number=row_number)
        for index, existing in enumerate(self.rows):
            if existing.row_number == row_number:
                self.rows[index] = changed
                return changed
        raise LookupError(f"행을 찾을 수 없습니다: {row_number}")


def _row(
    service_number: str,
    requester: str,
    model: str,
    serial_number: str,
    symptom: str,
    failure_cause: str,
    action: str,
    *,
    completion_date: str = "",
    warranty: str,
) -> SheetRow:
    values = [""] * 36
    values[SheetField.SERVICE_NUMBER] = service_number
    values[SheetField.RECEIPT_MONTH] = f"{int(service_number[6:8])}월"
    values[SheetField.RECEIVER] = "장진영"
    values[SheetField.REQUESTER] = requester
    values[SheetField.HOSPITAL] = f"{requester} 병원"
    values[SheetField.MODEL] = model
    values[SheetField.SERIAL_NUMBER] = serial_number
    values[SheetField.PRODUCTION_MONTH] = "2025-08"
    values[SheetField.WARRANTY] = warranty
    values[SheetField.SYMPTOM] = symptom
    values[SheetField.PROCESSOR] = "장진영"
    values[SheetField.FAILURE_CAUSE] = failure_cause
    values[SheetField.ACTION] = action
    values[SheetField.COMPLETION_DATE] = completion_date
    return SheetRow(tuple(values), row_number=5)
