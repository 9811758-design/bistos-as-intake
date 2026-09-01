from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook

from receivables_reconciliation.tracker_export import export_tasks
from receivables_reconciliation.tracker_models import DepositTask, EntryStatus


def test_export_tasks_writes_status_and_deposit_fields(tmp_path: Path) -> None:
    # Given
    task = DepositTask(
        message_id="mail-1",
        deposit_date=date(2026, 8, 24),
        depositor_name="장진영",
        amount=150_000,
        bank_name="기업018(원화)",
        subject="8/24 국내입금",
        received_at=datetime(2026, 8, 24, 9, 30),
        note="",
        status=EntryStatus.COMPLETED,
    )
    output_path = tmp_path / "입금메일_정리.xlsx"

    # When
    export_tasks(output_path, (task,))

    # Then
    workbook = load_workbook(output_path, read_only=True, data_only=True)
    sheet = workbook.worksheets[0]
    assert tuple(cell.value for cell in sheet[1]) == (
        "입력 상태",
        "입금일",
        "입금액",
        "입금자명",
        "금융기관",
        "메일 제목",
        "수신 시각",
        "확인 메모",
    )
    assert tuple(cell.value for cell in sheet[2])[:4] == (
        "입력 완료",
        datetime(2026, 8, 24),
        150_000,
        "장진영",
    )
    assert sheet["E2"].value == "기업018(원화)"
    workbook.close()
