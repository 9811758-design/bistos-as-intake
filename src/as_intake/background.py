from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from datetime import date
from typing import Protocol, TypeVar

from .analytics import AnalyticsDateRange, AnalyticsReport
from .dashboard_dialog import DashboardDialog
from .service import ASIntakeService
from .ui_tokens import BRAND_BLUE, ERROR, MUTED, SURFACE_SUBTLE, WARNING

T = TypeVar("T")


class TkBackgroundRunner(Protocol):
    def submit(
        self,
        work: Callable[[], T],
        on_success: Callable[[T], None],
        on_error: Callable[[Exception], None],
    ) -> None: ...

    def close(self) -> None: ...


class TkScheduler(Protocol):
    def after(self, ms: int, callback: Callable[[], None], /) -> str: ...


class BackgroundTkRunner:
    def __init__(self, root: TkScheduler, executor: Executor | None = None) -> None:
        self._root = root
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="as-intake",
        )
        self._closed = False

    def submit(
        self,
        work: Callable[[], T],
        on_success: Callable[[T], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        if self._closed:
            return
        future: Future[T] = self._executor.submit(work)
        future.add_done_callback(lambda done: self._schedule(done, on_success, on_error))

    def close(self) -> None:
        self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _schedule(
        self,
        future: Future[T],
        on_success: Callable[[T], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        if self._closed:
            return
        try:
            self._root.after(0, lambda: self._deliver(future, on_success, on_error))
        except tk.TclError:
            self.close()

    def _deliver(
        self,
        future: Future[T],
        on_success: Callable[[T], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        if self._closed:
            return
        try:
            on_success(future.result())
        except Exception as exc:
            on_error(exc)


class OverdueAlertBanner:
    def __init__(
        self,
        parent: tk.Misc,
        view_command: Callable[[], None],
        dashboard_command: Callable[[], DashboardDialog | None],
        retry_command: Callable[[], None],
    ) -> None:
        self.text = tk.StringVar(value="미처리 확인 중")
        self.frame = tk.Frame(parent, background=SURFACE_SUBTLE, padx=12, pady=8)
        self.label = tk.Label(
            self.frame,
            textvariable=self.text,
            background=SURFACE_SUBTLE,
            foreground=WARNING,
            font=("맑은 고딕", 10, "bold"),
        )
        self.label.pack(side="left", fill="x", expand=True, anchor="w")
        self.view_button = tk.Button(self.frame, text="미처리 보기", command=view_command)
        self.view_button.pack(side="right", padx=(8, 0))
        self.dashboard_button = tk.Button(
            self.frame,
            text="통계 대시보드",
            command=dashboard_command,
        )
        self.dashboard_button.pack(side="right", padx=(8, 0))
        self.retry_button = tk.Button(self.frame, text="재시도", command=retry_command)
        self.retry_button.pack(side="right")

    def pack(self) -> None:
        self.frame.pack(fill="x", pady=(0, 12))

    def set_loading(self) -> None:
        self.label.configure(foreground=BRAND_BLUE)
        self.text.set("미처리 확인 중")
        self.retry_button.configure(state="disabled")

    def render(self, report: AnalyticsReport) -> None:
        count = len(report.overdue_rows)
        self.label.configure(foreground=WARNING if count else MUTED)
        suffix = " · 지연 없음" if count == 0 else ""
        self.text.set(f"미처리 {count:,}건{suffix}")
        self.retry_button.configure(state="normal")

    def set_error(self, message: str) -> None:
        self.label.configure(foreground=ERROR)
        self.text.set(f"미처리 집계 실패 · {message}")
        self.retry_button.configure(state="normal")

    def mark_selected(self) -> None:
        self.label.configure(foreground=BRAND_BLUE)
        self.text.set(f"{self.text.get()} · 대시보드 미처리 탭")


class ASIntakeBackgroundCoordinator:
    def __init__(
        self,
        parent: tk.Misc,
        root: tk.Tk,
        service: ASIntakeService,
        runner: TkBackgroundRunner | None,
        today_provider: Callable[[], date],
        set_status: Callable[[str, str], None],
    ) -> None:
        self._root = root
        self._service = service
        self._runner = runner or BackgroundTkRunner(root)
        self._today = today_provider
        self._set_status = set_status
        self._closed = False
        self.dashboard: DashboardDialog | None = None
        self.banner = OverdueAlertBanner(
            parent,
            self.show_overdue,
            self.open_dashboard,
            self.refresh_overdue,
        )
        self.banner.pack()

    def replace_service(self, service: ASIntakeService) -> None:
        self._service = service
        self.refresh_overdue()

    def refresh_overdue(self) -> None:
        if not self._can_update():
            return
        self.banner.set_loading()
        self._runner.submit(
            lambda: self._service.current_year_overdue_report(today=self._today()),
            self._render_overdue,
            self._show_overdue_error,
        )

    def show_overdue(self) -> None:
        dialog = self.open_dashboard()
        if dialog is not None:
            dialog.notebook.select(0)
            self.banner.mark_selected()

    def open_dashboard(self) -> DashboardDialog | None:
        if not self._can_update():
            return None
        if self.dashboard is not None and self.dashboard.winfo_exists():
            self.dashboard.lift()
            return self.dashboard
        self.dashboard = DashboardDialog(
            self._root,
            self._load_dashboard,
            today=self._today(),
            close_command=self._dashboard_closed,
        )
        self.dashboard.refresh()
        return self.dashboard

    def close(self) -> None:
        self._closed = True
        self._runner.close()

    def _load_dashboard(self, date_range: AnalyticsDateRange) -> None:
        self._runner.submit(
            lambda: self._service.analytics_report(
                date_range.start,
                date_range.end,
                today=self._today(),
            ),
            self._render_dashboard,
            self._show_dashboard_error,
        )

    def _render_overdue(self, report: AnalyticsReport) -> None:
        if self._can_update():
            self.banner.render(report)

    def _show_overdue_error(self, error: Exception) -> None:
        if self._can_update():
            self.banner.set_error(str(error))
            self._set_status(f"미처리 경고 실패 · {error}", "ErrorStatus.TLabel")

    def _render_dashboard(self, report: AnalyticsReport) -> None:
        if self._can_update() and self.dashboard is not None and self.dashboard.winfo_exists():
            self.dashboard.render(report)

    def _show_dashboard_error(self, error: Exception) -> None:
        if self._can_update() and self.dashboard is not None and self.dashboard.winfo_exists():
            self.dashboard.set_error(f"대시보드 조회 실패 · {error}")

    def _dashboard_closed(self) -> None:
        self.dashboard = None

    def _can_update(self) -> bool:
        try:
            return not self._closed and bool(self._root.winfo_exists())
        except tk.TclError:
            return False
