from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from .columns import SheetField
from .recommendation import CaseRecommendation, RecommendationReport
from .ui_tokens import MUTED, SURFACE, TEXT


class RecommendationDialog(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        report: RecommendationReport,
        apply_command: Callable[[CaseRecommendation, bool], None],
    ) -> None:
        super().__init__(master)
        self._apply_command = apply_command
        self._recommendations: dict[str, CaseRecommendation] = {}
        self._details: dict[SheetField, tk.Text] = {}
        self.title("과거 A/S 유사 사례 추천")
        self.geometry("980x640")
        self.minsize(780, 520)
        self.transient(master.winfo_toplevel())
        self._build_header(report)
        self._build_results(report)
        self._build_details()
        self._build_actions()
        self.bind("<Escape>", lambda _event: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._select_first()
        self.grab_set()

    def _build_header(self, report: RecommendationReport) -> None:
        header = ttk.Frame(self, style="Card.TFrame", padding=16)
        header.pack(fill="x")
        ttk.Label(header, text="유사 사례 기반 해결 추천", style="Section.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text=(
                f"Google 시트 과거 {report.analyzed_rows:,}건을 PC 안에서 비교했습니다. "
                "유사도는 참고값이며 최종 조치는 담당자가 확인하세요."
            ),
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(4, 0))

    def _build_results(self, report: RecommendationReport) -> None:
        wrapper = ttk.Frame(self, style="Card.TFrame", padding=(16, 0, 16, 12))
        wrapper.pack(fill="both", expand=True)
        columns = ("score", "number", "model", "symptom", "cause", "action")
        self.tree = ttk.Treeview(
            wrapper,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=8,
        )
        headings = ("유사도", "접수번호", "모델", "증상", "불량원인", "대응조치")
        widths = (64, 112, 86, 210, 210, 230)
        for column, heading, width in zip(columns, headings, widths, strict=True):
            self.tree.heading(column, text=heading)
            self.tree.column(column, width=width, minwidth=56, anchor="w")
        for index, recommendation in enumerate(report.recommendations):
            row = recommendation.source
            item = self.tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    f"{recommendation.score_percent}%",
                    row.value(SheetField.SERVICE_NUMBER),
                    row.value(SheetField.MODEL),
                    row.value(SheetField.SYMPTOM),
                    row.value(SheetField.FAILURE_CAUSE),
                    row.value(SheetField.ACTION),
                ),
            )
            self._recommendations[item] = recommendation
        yscroll = ttk.Scrollbar(wrapper, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(wrapper, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        wrapper.rowconfigure(0, weight=1)
        wrapper.columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self._show_selected)
        self.tree.bind("<Double-1>", lambda _event: self._apply(include_cause=True))

    def _build_details(self) -> None:
        details = ttk.Frame(self, style="Card.TFrame", padding=(16, 0, 16, 12))
        details.pack(fill="x")
        labels = (
            (SheetField.SYMPTOM, "과거 증상"),
            (SheetField.FAILURE_CAUSE, "과거 불량원인"),
            (SheetField.ACTION, "과거 대응조치"),
        )
        for column, (field, label) in enumerate(labels):
            frame = ttk.Frame(details, style="Form.TFrame")
            frame.grid(row=0, column=column, sticky="nsew", padx=(0, 12))
            ttk.Label(frame, text=label, background=SURFACE, foreground=TEXT).pack(anchor="w")
            widget = tk.Text(
                frame,
                height=4,
                wrap="word",
                font=("맑은 고딕", 10),
                background=SURFACE,
                foreground=MUTED,
                relief="solid",
                borderwidth=1,
                padx=8,
                pady=6,
                state="disabled",
            )
            widget.pack(fill="both", expand=True, pady=(4, 0))
            self._details[field] = widget
            details.columnconfigure(column, weight=1, uniform="detail")

    def _build_actions(self) -> None:
        actions = ttk.Frame(self, style="App.TFrame", padding=(16, 0, 16, 16))
        actions.pack(fill="x")
        ttk.Button(actions, text="닫기  Esc", command=self.destroy).pack(side="left")
        ttk.Button(
            actions,
            text="원인·조치 적용",
            style="Primary.TButton",
            command=lambda: self._apply(include_cause=True),
        ).pack(side="right", padx=(8, 0))
        ttk.Button(
            actions,
            text="대응조치만 적용",
            command=lambda: self._apply(include_cause=False),
        ).pack(side="right")

    def _select_first(self) -> None:
        items = self.tree.get_children()
        if items:
            self.tree.selection_set(items[0])
            self.tree.focus(items[0])
            self._show_selected()

    def _selected(self) -> CaseRecommendation | None:
        selected = self.tree.selection()
        return self._recommendations.get(selected[0]) if selected else None

    def _show_selected(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        recommendation = self._selected()
        if recommendation is None:
            return
        for field, widget in self._details.items():
            widget.configure(state="normal")
            widget.delete("1.0", "end")
            widget.insert("1.0", recommendation.source.value(field))
            widget.configure(state="disabled")

    def _apply(self, *, include_cause: bool) -> None:
        recommendation = self._selected()
        if recommendation is None:
            return
        self._apply_command(recommendation, include_cause)
        self.destroy()
