from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pytest

from receivables_reconciliation.app import (
    FailureEvent,
    ReceivablesReconciliationApp,
    SuccessEvent,
)
from receivables_reconciliation.main import create_root
from receivables_reconciliation.models import MatchStatus
from receivables_reconciliation.service import (
    ReconciliationReport,
    ReconciliationRequest,
    ReconciliationRow,
    ReconciliationSummary,
)


@dataclass(frozen=True, slots=True)
class UnexpectedWorkerError(TypeError):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class MissingRuntimeDependencyError(ModuleNotFoundError):
    detail: str

    def __str__(self) -> str:
        return self.detail


def _report(path: Path) -> ReconciliationReport:
    request = ReconciliationRequest(date(2026, 8, 14), date(2026, 8, 14), path)
    summary = ReconciliationSummary(3, 2, 1, 1, 1, 0, 2)
    rows = (
        ReconciliationRow(
            MatchStatus.UNREGISTERED,
            "message-1",
            date(2026, 8, 14),
            "장진영",
            150_000,
            "입금 알림",
            datetime(2026, 8, 14, 9, 30),
            "no_erp_registration",
        ),
        ReconciliationRow(
            MatchStatus.REVIEW_NEEDED,
            "message-2",
            None,
            "",
            None,
            "송금 알림",
            datetime(2026, 8, 14, 10, 0),
            "입금자 이름을 찾을 수 없습니다.",
        ),
    )
    return ReconciliationReport(request, summary, rows, path)


def test_app_enables_compare_only_for_valid_period_and_existing_xls(tmp_path: Path) -> None:
    erp_path = tmp_path / "erp.xls"
    erp_path.touch()
    root = create_root()
    root.withdraw()
    try:
        app = ReceivablesReconciliationApp(root, lambda request: _report(erp_path))
        app.start_date.set("2026-08-14")
        app.end_date.set("2026-08-14")
        app.erp_path.set(str(erp_path))
        root.update_idletasks()
        assert app.compare_button.instate(("!disabled",))

        app.start_date.set("2026-08-15")
        root.update_idletasks()
        assert app.compare_button.instate(("disabled",))
    finally:
        root.destroy()


def test_app_renders_summary_actionable_rows_and_korean_headings(tmp_path: Path) -> None:
    erp_path = tmp_path / "erp.xls"
    root = create_root()
    root.withdraw()
    try:
        app = ReceivablesReconciliationApp(root, lambda request: _report(erp_path))
        app._handle_event(SuccessEvent(_report(erp_path)))

        assert app.summary_values["outlook"].get() == "3"
        assert app.summary_values["erp"].get() == "2"
        assert app.summary_values["registered"].get() == "1"
        assert app.summary_values["unregistered"].get() == "1"
        assert app.summary_values["review"].get() == "1"
        assert len(app.tree.get_children()) == 2
        assert app.tree.heading("status", "text") == "상태"
        assert app.tree.heading("name", "text") == "입금자명"
        first_values = app.tree.item(app.tree.get_children()[0], "values")
        assert first_values[:4] == ("미등록", "2026-08-14", "150,000원", "장진영")
    finally:
        root.destroy()


def test_app_surfaces_failure_and_restores_button(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "receivables_reconciliation.app.messagebox.showerror",
        lambda title, detail: shown.append((title, detail)),
    )
    root = create_root()
    root.withdraw()
    try:
        app = ReceivablesReconciliationApp(root, lambda request: _report(tmp_path / "erp.xls"))
        app._handle_event(FailureEvent("Outlook 접근 오류"))

        assert app.status.get() == "대조에 실패했습니다: Outlook 접근 오류"
        assert app.compare_button.instate(("!disabled",))
        assert shown == [("수금 대조 실패", "Outlook 접근 오류")]
    finally:
        root.destroy()


def test_app_worker_surfaces_unexpected_errors_instead_of_staying_loading(tmp_path: Path) -> None:
    # Given
    def failing_runner(_request: ReconciliationRequest) -> ReconciliationReport:
        raise UnexpectedWorkerError("can't compare offset-naive and offset-aware datetimes")

    root = create_root()
    root.withdraw()
    try:
        app = ReceivablesReconciliationApp(root, failing_runner)
        request = ReconciliationRequest(date(2026, 8, 14), date(2026, 8, 14), tmp_path / "erp.xls")

        # When
        app._run(request)

        # Then
        assert app._events.get_nowait() == FailureEvent(
            "can't compare offset-naive and offset-aware datetimes"
        )
    finally:
        root.destroy()


def test_app_worker_surfaces_missing_packaged_dependency(tmp_path: Path) -> None:
    # Given
    def failing_runner(_request: ReconciliationRequest) -> ReconciliationReport:
        raise MissingRuntimeDependencyError("No module named 'win32timezone'")

    root = create_root()
    root.withdraw()
    try:
        app = ReceivablesReconciliationApp(root, failing_runner)
        request = ReconciliationRequest(date(2026, 8, 14), date(2026, 8, 14), tmp_path / "erp.xls")

        # When
        app._run(request)

        # Then
        assert app._events.get_nowait() == FailureEvent("No module named 'win32timezone'")
    finally:
        root.destroy()
