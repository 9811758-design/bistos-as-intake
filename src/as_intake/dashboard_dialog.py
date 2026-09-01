from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from datetime import date
from tkinter import ttk
from typing import Final, Literal

from .analytics import (
    AnalyticsDateRange,
    AnalyticsReport,
    InvalidAnalyticsDateRangeError,
    ModelServiceCount,
    MonthlyFailureCause,
    OverdueRow,
    RepeatFailure,
)
from .dashboard_view import is_empty, select_first_row, summary_text
from .ui_tokens import BRAND_BLUE, ERROR, MUTED, SURFACE, SURFACE_SUBTLE

TableKey = Literal["overdue", "model", "repeat", "monthly"]

DATE_FORMAT_HINT: Final = "날짜는 YYYY-MM-DD 형식으로 입력하세요."


class DashboardDialog(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        refresh_command: Callable[[AnalyticsDateRange], None],
        *,
        today: date,
        close_command: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master)
        self._refresh_command = refresh_command
        self._close_command = close_command
        self._trees: dict[TableKey, ttk.Treeview] = {}
        self.start_var = tk.StringVar(value=f"{today.year}-01-01")
        self.end_var = tk.StringVar(value=today.isoformat())
        self.status_var = tk.StringVar(value="조회할 날짜 구간을 입력하세요.")
        self.summary_var = tk.StringVar(
            value="총 접수 0건 · 미처리 0건 · 보증 내 0건 · 보증 외 0건"
        )
        self.excluded_var = tk.StringVar(value="날짜 판독 제외 0건")
        self.title("A/S 통계 대시보드")
        self.geometry("980x640")
        self.minsize(860, 560)
        self.transient(master.winfo_toplevel())
        self._build()
        self.bind("<Escape>", lambda _event: self.close())
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.start_entry.focus_set()

    def refresh(self) -> None:
        date_range = self._parse_range()
        if date_range is None:
            return
        self.set_loading(date_range)
        self._refresh_command(date_range)

    def set_loading(self, date_range: AnalyticsDateRange) -> None:
        self.refresh_button.configure(state="disabled", text="불러오는 중")
        self.status_label.configure(foreground=BRAND_BLUE)
        self.status_var.set(
            f"{date_range.start.isoformat()} ~ {date_range.end.isoformat()} 조회 중"
        )

    def render(self, report: AnalyticsReport) -> None:
        self.refresh_button.configure(state="normal", text="조회")
        self.status_label.configure(foreground=MUTED)
        self.summary_var.set(summary_text(report))
        self.excluded_var.set(f"날짜 판독 제외 {report.date_unparseable_excluded_count:,}건")
        self._render_overdue(report.overdue_rows)
        self._render_model_counts(report.model_service_counts)
        self._render_repeat(report.repeat_failures)
        self._render_monthly(report.monthly_failure_causes)
        if is_empty(report):
            self.status_var.set("조회 결과 없음")
            return
        self.status_var.set(
            f"{report.date_range.start.isoformat()} ~ {report.date_range.end.isoformat()} 조회 완료"
        )

    def set_error(self, message: str) -> None:
        self.refresh_button.configure(state="normal", text="조회")
        self.status_label.configure(foreground=ERROR)
        self.status_var.set(message)

    def close(self) -> None:
        if self._close_command is not None:
            self._close_command()
        self.destroy()

    def tab_labels(self) -> tuple[str, ...]:
        return tuple(self.notebook.tab(tab_id, option="text") for tab_id in self.notebook.tabs())

    def table_headings(self, key: TableKey) -> tuple[str, ...]:
        tree = self._trees[key]
        return tuple(str(tree.heading(column, option="text")) for column in tree["columns"])

    def table_values(self, key: TableKey) -> tuple[tuple[str, ...], ...]:
        tree = self._trees[key]
        return tuple(
            tuple(str(value) for value in tree.item(item, "values"))
            for item in tree.get_children()
        )

    def _build(self) -> None:
        header = ttk.Frame(self, style="Card.TFrame", padding=16)
        header.pack(fill="x")
        ttk.Label(header, text="A/S 통계 대시보드", style="Section.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="기간을 지정해 미처리, 완료 모델별 건수, 반복 고장, 월별 원인을 조회합니다.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(4, 0))
        self._build_filters(header)
        self._build_summary()
        self._build_tabs()

    def _build_filters(self, parent: ttk.Frame) -> None:
        filters = ttk.Frame(parent, style="Form.TFrame")
        filters.pack(fill="x", pady=(12, 0))
        ttk.Label(filters, text="시작일", background=SURFACE).grid(row=0, column=0, sticky="w")
        ttk.Label(filters, text="종료일", background=SURFACE).grid(row=0, column=1, sticky="w")
        self.start_entry = ttk.Entry(filters, textvariable=self.start_var, width=14)
        self.end_entry = ttk.Entry(filters, textvariable=self.end_var, width=14)
        self.start_entry.grid(row=1, column=0, sticky="ew", padx=(0, 8))
        self.end_entry.grid(row=1, column=1, sticky="ew", padx=(0, 8))
        self.refresh_button = ttk.Button(
            filters,
            text="조회",
            style="Primary.TButton",
            command=self.refresh,
        )
        self.refresh_button.grid(row=1, column=2, sticky="ew")
        self.status_label = ttk.Label(filters, textvariable=self.status_var, foreground=MUTED)
        self.status_label.grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self.start_entry.bind("<Return>", lambda _event: self.refresh())
        self.end_entry.bind("<Return>", lambda _event: self.refresh())

    def _build_summary(self) -> None:
        summary = ttk.Frame(self, style="Card.TFrame", padding=(16, 12))
        summary.pack(fill="x")
        ttk.Label(
            summary,
            textvariable=self.summary_var,
            background=SURFACE_SUBTLE,
            foreground=BRAND_BLUE,
            padding=(12, 8),
            font=("맑은 고딕", 10, "bold"),
        ).pack(fill="x")
        ttk.Label(summary, textvariable=self.excluded_var, style="Muted.TLabel").pack(
            anchor="w", pady=(6, 0)
        )

    def _build_tabs(self) -> None:
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self._trees["overdue"] = self._add_table(
            "미처리",
            ("number", "date", "age", "model", "cause"),
            ("접수번호", "접수일", "경과일", "모델", "불량원인"),
            (120, 100, 70, 120, 300),
        )
        self._trees["model"] = self._add_table(
            "모델별 A/S 발생건수",
            ("model", "count"),
            ("모델", "완료 A/S 건수"),
            (240, 120),
        )
        self._trees["repeat"] = self._add_table(
            "모델별 반복 고장",
            ("model", "cause", "count"),
            ("모델", "불량원인", "건수"),
            (140, 360, 70),
        )
        self._trees["monthly"] = self._add_table(
            "월별 불량원인",
            ("month", "cause", "count"),
            ("월", "불량원인", "건수"),
            (120, 360, 70),
        )

    def _add_table(
        self,
        title: str,
        columns: tuple[str, ...],
        headings: tuple[str, ...],
        widths: tuple[int, ...],
    ) -> ttk.Treeview:
        frame = ttk.Frame(self.notebook, style="Card.TFrame", padding=12)
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        for column, heading, width in zip(columns, headings, widths, strict=True):
            tree.heading(column, text=heading)
            tree.column(column, width=width, minwidth=56, anchor="w")
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.notebook.add(frame, text=title)
        return tree

    def _parse_range(self) -> AnalyticsDateRange | None:
        try:
            start = date.fromisoformat(self.start_var.get())
            end = date.fromisoformat(self.end_var.get())
        except ValueError:
            self.set_error(DATE_FORMAT_HINT)
            return None
        try:
            return AnalyticsDateRange(start, end)
        except InvalidAnalyticsDateRangeError as exc:
            self.set_error(str(exc))
            return None

    def _render_overdue(self, rows: tuple[OverdueRow, ...]) -> None:
        tree = self._clear("overdue")
        for row in rows:
            tree.insert(
                "",
                "end",
                values=(
                    row.service_number,
                    row.received_date.isoformat(),
                    f"{row.age_days}일",
                    row.model,
                    row.failure_cause,
                ),
            )
        select_first_row(tree)

    def _render_repeat(self, rows: tuple[RepeatFailure, ...]) -> None:
        tree = self._clear("repeat")
        for row in rows:
            tree.insert("", "end", values=(row.model, row.failure_cause, str(row.count)))
        select_first_row(tree)

    def _render_model_counts(self, rows: tuple[ModelServiceCount, ...]) -> None:
        tree = self._clear("model")
        for row in rows:
            tree.insert("", "end", values=(row.model, str(row.count)))
        select_first_row(tree)

    def _render_monthly(self, rows: tuple[MonthlyFailureCause, ...]) -> None:
        tree = self._clear("monthly")
        for row in rows:
            tree.insert("", "end", values=(row.month, row.failure_cause, str(row.count)))
        select_first_row(tree)

    def _clear(self, key: TableKey) -> ttk.Treeview:
        tree = self._trees[key]
        tree.delete(*tree.get_children())
        return tree
