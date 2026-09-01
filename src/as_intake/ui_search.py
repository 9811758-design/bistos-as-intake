from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from datetime import date
from tkinter import ttk

from .columns import SheetField
from .records import SheetRow
from .ui_tokens import SURFACE


class SearchPane(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        search_command: Callable[[], None],
        select_command: Callable[[], None],
    ) -> None:
        super().__init__(master, style="Card.TFrame", padding=16)
        self.year = tk.StringVar(value=str(date.today().year))
        self.query = tk.StringVar()
        self.close_status = tk.StringVar()
        self._rows: dict[str, SheetRow] = {}
        ttk.Label(self, text="접수 내역 검색", style="Section.TLabel").pack(anchor="w")
        ttk.Label(
            self,
            text="서비스번호, 의뢰자, 병원, 모델, 시리얼, 증상으로 찾습니다.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(2, 12))
        self._filters = ttk.Frame(self, style="Form.TFrame")
        self._filters.pack(fill="x")
        ttk.Label(self._filters, text="연도", background=SURFACE).grid(row=0, column=0, sticky="w")
        ttk.Label(self._filters, text="검색어", background=SURFACE).grid(
            row=0, column=1, sticky="w"
        )
        ttk.Label(self._filters, text="종료상태", background=SURFACE).grid(
            row=0, column=2, sticky="w"
        )
        ttk.Combobox(
            self._filters,
            textvariable=self.year,
            width=7,
            values=("2025", "2026", "2027"),
        ).grid(
            row=1, column=0, sticky="ew", padx=(0, 8)
        )
        query_entry = ttk.Entry(self._filters, textvariable=self.query)
        query_entry.grid(row=1, column=1, sticky="ew", padx=(0, 8))
        ttk.Combobox(
            self._filters,
            textvariable=self.close_status,
            values=("", "종료"),
            width=9,
            state="readonly",
        ).grid(row=1, column=2, sticky="ew", padx=(0, 8))
        ttk.Button(
            self._filters, text="검색", style="Primary.TButton", command=search_command
        ).grid(
            row=1, column=3, sticky="ew"
        )
        self._filters.columnconfigure(1, weight=1)
        query_entry.bind("<Return>", lambda _event: search_command())
        self._build_tree(select_command)

    def _build_tree(self, select_command: Callable[[], None]) -> None:
        wrapper = ttk.Frame(self, style="Card.TFrame")
        wrapper.pack(fill="both", expand=True, pady=(12, 0))
        columns = ("number", "requester", "hospital", "model", "symptom", "status")
        self.tree = ttk.Treeview(wrapper, columns=columns, show="headings", selectmode="browse")
        headings = ("접수번호", "의뢰자", "병원", "모델", "증상", "상태")
        widths = (112, 82, 100, 74, 150, 54)
        for column, heading, width in zip(columns, headings, widths, strict=True):
            self.tree.heading(column, text=heading)
            self.tree.column(column, width=width, minwidth=48, anchor="w")
        yscroll = ttk.Scrollbar(wrapper, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(wrapper, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        wrapper.rowconfigure(0, weight=1)
        wrapper.columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", lambda _event: select_command())

    def render(self, rows: tuple[SheetRow, ...]) -> None:
        self.tree.delete(*self.tree.get_children())
        self._rows.clear()
        for index, row in enumerate(rows):
            item = self.tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    row.value(SheetField.SERVICE_NUMBER),
                    row.value(SheetField.REQUESTER),
                    row.value(SheetField.HOSPITAL),
                    row.value(SheetField.MODEL),
                    row.value(SheetField.SYMPTOM),
                    row.value(SheetField.CLOSE_STATUS) or "진행",
                ),
            )
            self._rows[item] = row

    def selected_row(self) -> SheetRow | None:
        selected = self.tree.selection()
        return self._rows.get(selected[0]) if selected else None
