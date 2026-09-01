from __future__ import annotations

from datetime import date, datetime

import pytest

from receivables_reconciliation.main import create_root
from receivables_reconciliation.tracker_app import (
    AUTO_REFRESH_MS,
    ReceivablesTrackerApp,
    RefreshFailureEvent,
    RefreshSuccessEvent,
)
from receivables_reconciliation.tracker_models import (
    DepositTask,
    EntryStatus,
    RefreshResult,
    TaskFilter,
    TaskSnapshot,
    TaskSummary,
)


class FakeTrackerService:
    def __init__(self, snapshot: TaskSnapshot) -> None:
        self.snapshot = snapshot
        self.refresh_filters: list[TaskFilter] = []
        self.status_changes: list[tuple[str, EntryStatus, TaskFilter]] = []
        self.status_batches: list[tuple[tuple[str, ...], EntryStatus, TaskFilter]] = []

    def load(self, task_filter: TaskFilter) -> TaskSnapshot:
        tasks = tuple(
            task
            for task in self.snapshot.tasks
            if task_filter is TaskFilter.ALL or task.status.value == task_filter.value
        )
        return TaskSnapshot(tasks, self.snapshot.summary)

    def refresh(self, task_filter: TaskFilter) -> RefreshResult:
        self.refresh_filters.append(task_filter)
        return RefreshResult(self.load(task_filter), added_count=1, scanned_count=2)

    def set_status(
        self,
        message_id: str,
        status: EntryStatus,
        task_filter: TaskFilter,
    ) -> TaskSnapshot:
        self.status_changes.append((message_id, status, task_filter))
        return self.load(task_filter)

    def set_statuses(
        self,
        message_ids: tuple[str, ...],
        status: EntryStatus,
        task_filter: TaskFilter,
    ) -> TaskSnapshot:
        self.status_batches.append((message_ids, status, task_filter))
        return self.load(task_filter)


def _snapshot() -> TaskSnapshot:
    tasks = (
        DepositTask(
            message_id="mail-1",
            deposit_date=date(2026, 8, 24),
            depositor_name="장진영",
            amount=150_000,
            bank_name="기업018(원화)",
            subject="8/24 국내입금",
            received_at=datetime(2026, 8, 24, 9, 30),
            note="",
            status=EntryStatus.PENDING,
        ),
        DepositTask(
            message_id="mail-2",
            deposit_date=date(2026, 8, 23),
            depositor_name="김민수",
            amount=90_000,
            bank_name="국민648(원화)",
            subject="8/23 국내입금",
            received_at=datetime(2026, 8, 23, 14, 0),
            note="",
            status=EntryStatus.COMPLETED,
        ),
    )
    return TaskSnapshot(tasks, TaskSummary(2, 1, 1, 0))


def test_app_loads_saved_tasks_and_renders_status_counts() -> None:
    # Given
    root = create_root()
    root.withdraw()
    service = FakeTrackerService(_snapshot())

    # When
    app = ReceivablesTrackerApp(root, service)
    root.update_idletasks()

    # Then
    try:
        assert app.summary_values["total"].get() == "2"
        assert app.summary_values["pending"].get() == "1"
        assert app.summary_values["completed"].get() == "1"
        assert len(app.tree.get_children()) == 2
        assert app.tree.heading("status", "text") == "입력 상태"
        first_values = app.tree.item(app.tree.get_children()[0], "values")
        assert first_values[:5] == (
            "미입력",
            "2026-08-24",
            "150,000원",
            "장진영",
            "기업018(원화)",
        )
    finally:
        root.destroy()


def test_app_resets_horizontal_scroll_when_rendering_snapshot() -> None:
    # Given
    root = create_root()
    root.withdraw()
    app = ReceivablesTrackerApp(root, FakeTrackerService(_snapshot()))
    app.tree.xview_moveto(1.0)
    app.tree.yview_moveto(1.0)

    # When
    app._render_snapshot(_snapshot())

    # Then
    try:
        assert app.tree.xview()[0] == 0.0
        assert app.tree.yview()[0] == 0.0
    finally:
        root.destroy()


def test_app_filters_tasks_by_inclusive_deposit_date_range() -> None:
    # Given
    root = create_root()
    root.withdraw()
    app = ReceivablesTrackerApp(root, FakeTrackerService(_snapshot()))
    app.start_date_value.set("2026-08-23")
    app.end_date_value.set("2026-08-23")
    app.depositor_name_value.set("김민수")

    # When
    app._apply_filter()

    # Then
    try:
        items = app.tree.get_children()
        assert len(items) == 1
        assert app.tree.item(items[0], "values")[1] == "2026-08-23"
        assert app.tree.item(items[0], "values")[3] == "김민수"
    finally:
        root.destroy()


def test_app_filters_tasks_by_depositor_name_search() -> None:
    # Given
    root = create_root()
    root.withdraw()
    app = ReceivablesTrackerApp(root, FakeTrackerService(_snapshot()))
    app.depositor_name_value.set("장진")

    # When
    app._apply_filter()

    # Then
    try:
        items = app.tree.get_children()
        assert len(items) == 1
        assert app.tree.item(items[0], "values")[3] == "장진영"
    finally:
        root.destroy()


def test_app_marks_selected_task_completed_with_button_action() -> None:
    # Given
    root = create_root()
    root.withdraw()
    service = FakeTrackerService(_snapshot())
    app = ReceivablesTrackerApp(root, service)
    first_item = app.tree.get_children()[0]
    app.tree.selection_set(first_item)

    # When
    app._set_selected_status(EntryStatus.COMPLETED)

    # Then
    try:
        assert service.status_batches == [(("mail-1",), EntryStatus.COMPLETED, TaskFilter.ALL)]
    finally:
        root.destroy()


def test_app_marks_multiple_selected_tasks_completed_in_one_batch() -> None:
    # Given
    root = create_root()
    root.withdraw()
    service = FakeTrackerService(_snapshot())
    app = ReceivablesTrackerApp(root, service)
    items = app.tree.get_children()
    app.tree.selection_set(items)

    # When
    app._set_selected_status(EntryStatus.COMPLETED)

    # Then
    try:
        assert str(app.tree.cget("selectmode")) == "extended"
        assert service.status_batches == [
            (("mail-1", "mail-2"), EntryStatus.COMPLETED, TaskFilter.ALL)
        ]
        assert app.status.get() == "선택한 2건을 입력 완료로 변경했습니다."
    finally:
        root.destroy()


def test_app_selects_and_clears_all_visible_tasks() -> None:
    # Given
    root = create_root()
    root.withdraw()
    app = ReceivablesTrackerApp(root, FakeTrackerService(_snapshot()))

    # When
    app._select_all_visible()

    # Then
    try:
        assert app.tree.selection() == app.tree.get_children()
        app._clear_selection()
        assert app.tree.selection() == ()
    finally:
        root.destroy()


def test_app_refresh_event_reports_new_mail_and_reenables_button() -> None:
    # Given
    root = create_root()
    root.withdraw()
    app = ReceivablesTrackerApp(root, FakeTrackerService(_snapshot()))
    app.refresh_button.configure(state="disabled")
    result = RefreshResult(_snapshot(), added_count=1, scanned_count=2)

    # When
    app._handle_event(RefreshSuccessEvent(result))

    # Then
    try:
        assert app.status.get() == "새 입금메일 1건을 추가했습니다."
        assert app.refresh_button.instate(("!disabled",))
    finally:
        root.destroy()


def test_app_refresh_failure_keeps_list_and_surfaces_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "receivables_reconciliation.tracker_app.messagebox.showerror",
        lambda title, detail: shown.append((title, detail)),
    )
    root = create_root()
    root.withdraw()
    app = ReceivablesTrackerApp(root, FakeTrackerService(_snapshot()))

    # When
    app._handle_event(RefreshFailureEvent("Outlook 접근 오류"))

    # Then
    try:
        assert len(app.tree.get_children()) == 2
        assert app.refresh_button.instate(("!disabled",))
        assert shown == [("Outlook 새로고침 실패", "Outlook 접근 오류")]
    finally:
        root.destroy()


def test_app_uses_ten_minute_auto_refresh_interval() -> None:
    # Given
    expected_interval = 10 * 60 * 1000

    # When
    actual_interval = AUTO_REFRESH_MS

    # Then
    assert actual_interval == expected_interval
