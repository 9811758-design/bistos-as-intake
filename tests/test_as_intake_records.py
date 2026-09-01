from __future__ import annotations

from datetime import date

from as_intake.columns import SheetField
from as_intake.records import RecordDraft, SheetRow


def test_draft_builds_complete_aj_row_and_keeps_af_as_spacer() -> None:
    draft = RecordDraft.create(
        receipt_date=date(2026, 8, 24),
        values={
            SheetField.RECEIVER: "장진영",
            SheetField.REQUESTER: "국제메디칼",
            SheetField.HOSPITAL: "목포미즈아이",
            SheetField.MODEL: "BT350L",
            SheetField.SYMPTOM: "전원이 켜지지 않음",
            SheetField.NOTE: "전화 안내 후 입고",
            SheetField.TRACKING_NUMBER: "44986199182",
            SheetField.CLOSE_STATUS: "종료",
        },
    )

    row = draft.to_sheet_row("DS26082401")

    assert len(row.values) == 36
    assert row.value(SheetField.SERVICE_NUMBER) == "DS26082401"
    assert row.value(SheetField.RECEIPT_MONTH) == "8월"
    assert row.value(SheetField.RECEIVER) == "장진영"
    assert row.value(SheetField.SPACER) == ""
    assert row.value(SheetField.TRACKING_NUMBER) == "44986199182"
    assert row.value(SheetField.CLOSE_STATUS) == "종료"


def test_sheet_row_normalizes_short_google_values_to_all_columns() -> None:
    row = SheetRow.from_google_values(9, ("DS26082401", "8월", "장진영"))

    assert len(row.values) == 36
    assert row.row_number == 9
    assert row.value(SheetField.RECEIVER) == "장진영"
    assert row.value(SheetField.CLOSE_STATUS) == ""
