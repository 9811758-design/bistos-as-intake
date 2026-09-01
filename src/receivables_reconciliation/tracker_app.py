from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Final, assert_never

from receivables_reconciliation.tracker_date_filter import (
    DepositDateRange,
    InvalidDepositDateRangeError,
    filter_tasks_by_deposit_date,
    parse_deposit_date_range,
)
from receivables_reconciliation.tracker_events import (
    RefreshFailureEvent,
    RefreshSuccessEvent,
    TrackerUiEvent,
)
from receivables_reconciliation.tracker_export_dialog import export_all_tasks
from receivables_reconciliation.tracker_models import (
    DepositTask,
    EntryStatus,
    TaskFilter,
    TaskSnapshot,
)
from receivables_reconciliation.tracker_name_filter import filter_tasks_by_depositor_name
from receivables_reconciliation.tracker_service import TrackerPipelineError, TrackerService
from receivables_reconciliation.tracker_store import MissingTaskError, TaskStoreError
from receivables_reconciliation.tracker_ui import (
    TrackerLayoutBindings,
    build_tracker_layout,
    status_label,
)
from service_validation.brand import BACKGROUND, configure_styles, set_window_icon

AUTO_REFRESH_MS: Final = 600_000


class ReceivablesTrackerApp:
    def __init__(self, root: tk.Tk, service: TrackerService) -> None:
        self.root = root
        self._service = service
        self._events: queue.Queue[TrackerUiEvent] = queue.Queue()
        self._tasks_by_item: dict[str, DepositTask] = {}
        self._busy = False
        self._icon: tk.PhotoImage | None = None
        self.root.title("Outlook 입금메일 정리")
        self.root.geometry("1180x740")
        self.root.minsize(940, 620)
        self.root.configure(background=BACKGROUND)
        configure_styles(root)
        self.status = tk.StringVar(value="저장된 입금메일 목록을 불러왔습니다.")
        self.filter_value = tk.StringVar(value=TaskFilter.ALL.value)
        self.start_date_value = tk.StringVar(value="")
        self.end_date_value = tk.StringVar(value="")
        self.depositor_name_value = tk.StringVar(value="")
        self._date_range = DepositDateRange(None, None)
        self.summary_values = {
            "total": tk.StringVar(value="0"),
            "pending": tk.StringVar(value="0"),
            "completed": tk.StringVar(value="0"),
            "review": tk.StringVar(value="0"),
        }
        self._build_ui()
        self._set_icon()
        self._render_snapshot(self._service.load(TaskFilter.ALL))
        self.root.after(100, self._poll_events)
        self.root.after(500, self._start_refresh)
        self.root.after(AUTO_REFRESH_MS, self._auto_refresh)

    def _build_ui(self) -> None:
        widgets = build_tracker_layout(
            self.root,
            TrackerLayoutBindings(
                status=self.status,
                filter_value=self.filter_value,
                start_date=self.start_date_value,
                end_date=self.end_date_value,
                depositor_name=self.depositor_name_value,
                summary_values=self.summary_values,
                refresh=self._start_refresh,
                apply_filter=self._apply_filter,
                clear_date_filter=self._clear_date_filter,
                clear_name_filter=self._clear_name_filter,
                select_all_visible=self._select_all_visible,
                clear_selection=self._clear_selection,
                mark_completed=lambda: self._set_selected_status(EntryStatus.COMPLETED),
                mark_pending=lambda: self._set_selected_status(EntryStatus.PENDING),
                export_excel=self._export_excel,
                selection_changed=self._selection_changed,
            ),
        )
        self.refresh_button = widgets.refresh_button
        self.complete_button = widgets.complete_button
        self.pending_button = widgets.pending_button
        self.export_button = widgets.export_button
        self.tree = widgets.tree

    def _set_icon(self) -> None:
        try:
            self._icon = set_window_icon(self.root)
        except (tk.TclError, OSError):
            self._icon = None

    def _current_filter(self) -> TaskFilter:
        return TaskFilter(self.filter_value.get())

    def _start_refresh(self) -> None:
        if self._busy:
            return
        self._busy = True
        self.refresh_button.configure(state="disabled")
        self.status.set("Outlook에서 새 입금메일을 확인하고 있습니다...")
        task_filter = self._current_filter()
        threading.Thread(target=self._run_refresh, args=(task_filter,), daemon=True).start()

    def _run_refresh(self, task_filter: TaskFilter) -> None:
        try:
            result = self._service.refresh(task_filter)
        except (
            ModuleNotFoundError,
            MissingTaskError,
            OSError,
            TaskStoreError,
            TrackerPipelineError,
            TypeError,
            ValueError,
        ) as exc:
            self._events.put(RefreshFailureEvent(str(exc)))
            return
        self._events.put(RefreshSuccessEvent(result))

    def _auto_refresh(self) -> None:
        self._start_refresh()
        self.root.after(AUTO_REFRESH_MS, self._auto_refresh)

    def _poll_events(self) -> None:
        while True:
            try:
                self._handle_event(self._events.get_nowait())
            except queue.Empty:
                break
        self.root.after(100, self._poll_events)

    def _handle_event(self, event: TrackerUiEvent) -> None:
        self._busy = False
        self.refresh_button.configure(state="normal")
        match event:
            case RefreshSuccessEvent(result=result):
                self._render_snapshot(result.snapshot)
                if result.added_count:
                    self.status.set(f"새 입금메일 {result.added_count:,}건을 추가했습니다.")
                else:
                    self.status.set("새 입금메일이 없습니다. 목록이 최신 상태입니다.")
            case RefreshFailureEvent(detail=detail):
                self.status.set(f"새로고침 실패: {detail}")
                messagebox.showerror("Outlook 새로고침 실패", detail)
            case unreachable:
                assert_never(unreachable)

    def _render_snapshot(self, snapshot: TaskSnapshot) -> None:
        summary = snapshot.summary
        self.summary_values["total"].set(f"{summary.total_count:,}")
        self.summary_values["pending"].set(f"{summary.pending_count:,}")
        self.summary_values["completed"].set(f"{summary.completed_count:,}")
        self.summary_values["review"].set(f"{summary.review_count:,}")
        self.tree.delete(*self.tree.get_children())
        self._tasks_by_item.clear()
        dated_tasks = filter_tasks_by_deposit_date(snapshot.tasks, self._date_range)
        visible_tasks = filter_tasks_by_depositor_name(dated_tasks, self.depositor_name_value.get())
        for index, task in enumerate(visible_tasks):
            item_id = f"task-{index}"
            self._tasks_by_item[item_id] = task
            self.tree.insert(
                "",
                "end",
                iid=item_id,
                values=(
                    status_label(task.status),
                    task.deposit_date.isoformat() if task.deposit_date else "-",
                    f"{task.amount:,}원" if task.amount is not None else "-",
                    task.depositor_name or "-",
                    task.bank_name or "-",
                    task.subject,
                    task.received_at.strftime("%Y-%m-%d %H:%M"),
                    task.note or "-",
                ),
                tags=(task.status.value,),
            )
        self.tree.xview_moveto(0.0)
        self.tree.yview_moveto(0.0)
        self._selection_changed()

    def _apply_filter(self) -> None:
        try:
            date_range = parse_deposit_date_range(
                self.start_date_value.get(), self.end_date_value.get()
            )
        except InvalidDepositDateRangeError as exc:
            self.status.set(str(exc))
            messagebox.showerror("입금일 기간 오류", str(exc))
            return
        try:
            snapshot = self._service.load(self._current_filter())
        except TaskStoreError as exc:
            messagebox.showerror("목록 불러오기 실패", str(exc))
            return
        self._date_range = date_range
        self._render_snapshot(snapshot)

    def _clear_date_filter(self) -> None:
        self.start_date_value.set("")
        self.end_date_value.set("")
        self._apply_filter()

    def _clear_name_filter(self) -> None:
        self.depositor_name_value.set("")
        self._apply_filter()

    def _selected_tasks(self) -> tuple[DepositTask, ...]:
        selected_items = set(self.tree.selection())
        return tuple(
            self._tasks_by_item[item_id]
            for item_id in self.tree.get_children()
            if item_id in selected_items
        )

    def _selection_changed(self) -> None:
        tasks = self._selected_tasks()
        if not tasks:
            self.complete_button.configure(state="disabled")
            self.pending_button.configure(state="disabled")
            return
        self.complete_button.configure(
            state="normal"
            if any(task.status is EntryStatus.PENDING for task in tasks)
            else "disabled"
        )
        self.pending_button.configure(
            state="normal"
            if any(task.status is EntryStatus.COMPLETED for task in tasks)
            else "disabled"
        )

    def _select_all_visible(self) -> None:
        self.tree.selection_set(*self.tree.get_children())
        self._selection_changed()

    def _clear_selection(self) -> None:
        self.tree.selection_remove(*self.tree.selection())
        self._selection_changed()

    def _set_selected_status(self, status: EntryStatus) -> None:
        tasks = self._selected_tasks()
        if not tasks:
            return
        try:
            snapshot = self._service.set_statuses(
                tuple(task.message_id for task in tasks), status, self._current_filter()
            )
        except (MissingTaskError, TaskStoreError) as exc:
            messagebox.showerror("상태 변경 실패", str(exc))
            return
        self._render_snapshot(snapshot)
        self.status.set(f"선택한 {len(tasks):,}건을 {status_label(status)}로 변경했습니다.")

    def _export_excel(self) -> None:
        export_all_tasks(self.root, self._service, self.status)
