from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from tkinter import ttk
from typing import assert_never

from receivables_reconciliation.tracker_models import EntryStatus
from service_validation.brand import (
    BORDER,
    BRAND_GREEN,
    MUTED,
    NAVY,
    SURFACE,
    SURFACE_SUBTLE,
    TEXT,
)


@dataclass(frozen=True, slots=True)
class TrackerLayoutBindings:
    status: tk.StringVar
    filter_value: tk.StringVar
    start_date: tk.StringVar
    end_date: tk.StringVar
    depositor_name: tk.StringVar
    summary_values: Mapping[str, tk.StringVar]
    refresh: Callable[[], None]
    apply_filter: Callable[[], None]
    clear_date_filter: Callable[[], None]
    clear_name_filter: Callable[[], None]
    select_all_visible: Callable[[], None]
    clear_selection: Callable[[], None]
    mark_completed: Callable[[], None]
    mark_pending: Callable[[], None]
    export_excel: Callable[[], None]
    selection_changed: Callable[[], None]


@dataclass(frozen=True, slots=True)
class TrackerLayoutWidgets:
    refresh_button: ttk.Button
    complete_button: ttk.Button
    pending_button: ttk.Button
    export_button: ttk.Button
    tree: ttk.Treeview


def build_tracker_layout(
    root: tk.Tk,
    bindings: TrackerLayoutBindings,
) -> TrackerLayoutWidgets:
    header = tk.Frame(root, bg=NAVY, height=104)
    header.pack(fill="x")
    header.pack_propagate(False)
    ttk.Label(header, text="Outlook 입금메일 정리", style="Header.TLabel").pack(
        anchor="w", padx=30, pady=(18, 2)
    )
    ttk.Label(
        header,
        text="입금 알림을 자동으로 모으고 ERP 입력 완료 여부를 관리합니다.",
        style="Subtitle.TLabel",
    ).pack(anchor="w", padx=31)
    tk.Frame(header, bg=BRAND_GREEN, height=4).pack(fill="x", side="bottom")

    body = ttk.Frame(root, style="App.TFrame", padding=(22, 16, 22, 12))
    body.pack(fill="both", expand=True)
    body.columnconfigure(0, weight=1)
    body.rowconfigure(2, weight=1)

    toolbar = ttk.Frame(body, style="Card.TFrame", padding=(16, 12))
    toolbar.grid(row=0, column=0, sticky="ew")
    toolbar.columnconfigure(2, weight=1)
    refresh_button = ttk.Button(
        toolbar,
        text="Outlook 새로고침",
        style="Primary.TButton",
        command=bindings.refresh,
    )
    refresh_button.grid(row=0, column=0, sticky="w")
    ttk.Label(
        toolbar,
        text="프로그램 실행 중 10분마다 자동으로 확인합니다.",
        style="Muted.TLabel",
    ).grid(row=0, column=1, padx=(12, 0), sticky="w")
    export_button = ttk.Button(
        toolbar,
        text="전체 목록 Excel 저장",
        command=bindings.export_excel,
    )
    export_button.grid(row=0, column=3, sticky="e")

    summary = ttk.Frame(body, style="Card.TFrame", padding=(18, 12))
    summary.grid(row=1, column=0, sticky="ew", pady=(12, 12))
    for index, (key, label) in enumerate(
        (
            ("total", "전체 입금메일"),
            ("pending", "미입력"),
            ("completed", "입력 완료"),
            ("review", "내용 확인 필요"),
        )
    ):
        summary.columnconfigure(index, weight=1)
        item = tk.Frame(summary, bg=SURFACE, padx=8, pady=4)
        item.grid(row=0, column=index, sticky="ew", padx=8)
        ttk.Label(item, text=label, style="Muted.TLabel").pack()
        ttk.Label(item, textvariable=bindings.summary_values[key], style="Count.TLabel").pack()

    table_card = ttk.Frame(body, style="Card.TFrame", padding=(16, 14))
    table_card.grid(row=2, column=0, sticky="nsew")
    table_card.columnconfigure(0, weight=1)
    table_card.rowconfigure(2, weight=1)
    heading_row = ttk.Frame(table_card, style="Card.TFrame")
    heading_row.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
    heading_row.columnconfigure(1, weight=1)
    ttk.Label(heading_row, text="입금메일 업무 목록", style="Section.TLabel").grid(
        row=0, column=0, sticky="w"
    )
    name_filter = ttk.Frame(heading_row, style="Card.TFrame")
    name_filter.grid(row=0, column=1, padx=12, sticky="e")
    ttk.Label(name_filter, text="입금자명", style="Muted.TLabel").pack(side="left")
    name_entry = ttk.Entry(name_filter, textvariable=bindings.depositor_name, width=14)
    name_entry.pack(side="left", padx=(8, 4))
    name_entry.bind("<Return>", lambda _event: bindings.apply_filter())
    ttk.Button(name_filter, text="검색", command=bindings.apply_filter).pack(
        side="left", padx=(6, 4)
    )
    ttk.Button(name_filter, text="초기화", command=bindings.clear_name_filter).pack(side="left")
    filters = tk.Frame(heading_row, bg=SURFACE)
    filters.grid(row=0, column=2, sticky="e")
    for label, value in (("전체", "all"), ("미입력", "pending"), ("입력 완료", "completed")):
        tk.Radiobutton(
            filters,
            text=label,
            variable=bindings.filter_value,
            value=value,
            command=bindings.apply_filter,
            bg=SURFACE,
            fg=TEXT,
            activebackground=SURFACE_SUBTLE,
            selectcolor=SURFACE,
            font=("맑은 고딕", 9),
        ).pack(side="left", padx=(8, 0))

    actions = ttk.Frame(table_card, style="Card.TFrame")
    actions.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8))
    complete_button = ttk.Button(
        actions,
        text="선택 건 입력 완료",
        style="Success.TButton",
        command=bindings.mark_completed,
        state="disabled",
    )
    complete_button.pack(side="left")
    pending_button = ttk.Button(
        actions,
        text="선택 건 미입력",
        command=bindings.mark_pending,
        state="disabled",
    )
    pending_button.pack(side="left", padx=(8, 0))
    ttk.Button(
        actions,
        text="현재 목록 전체 선택",
        command=bindings.select_all_visible,
    ).pack(side="left", padx=(8, 0))
    ttk.Button(actions, text="선택 해제", command=bindings.clear_selection).pack(
        side="left", padx=(8, 0)
    )
    date_filters = ttk.Frame(actions, style="Card.TFrame")
    date_filters.pack(side="right")
    ttk.Label(date_filters, text="입금일", style="Muted.TLabel").pack(side="left")
    ttk.Entry(date_filters, textvariable=bindings.start_date, width=11).pack(
        side="left", padx=(8, 4)
    )
    ttk.Label(date_filters, text="~", style="Muted.TLabel").pack(side="left")
    ttk.Entry(date_filters, textvariable=bindings.end_date, width=11).pack(side="left", padx=4)
    ttk.Button(date_filters, text="기간 적용", command=bindings.apply_filter).pack(
        side="left", padx=(6, 4)
    )
    ttk.Button(date_filters, text="기간 초기화", command=bindings.clear_date_filter).pack(
        side="left"
    )

    columns = ("status", "date", "amount", "name", "bank", "subject", "received", "note")
    tree = ttk.Treeview(table_card, columns=columns, show="headings", selectmode="extended")
    headings = {
        "status": "입력 상태",
        "date": "입금일",
        "amount": "입금액",
        "name": "입금자명",
        "bank": "금융기관",
        "subject": "메일 제목",
        "received": "수신 시각",
        "note": "확인 메모",
    }
    widths = {
        "status": 100,
        "date": 100,
        "amount": 120,
        "name": 140,
        "bank": 130,
        "subject": 260,
        "received": 150,
        "note": 260,
    }
    for column in columns:
        tree.heading(column, text=headings[column])
        tree.column(
            column,
            width=widths[column],
            minwidth=75,
            anchor="center" if column in {"status", "date", "amount", "received"} else "w",
            stretch=column in {"subject", "note"},
        )
    tree.tag_configure("completed", foreground=BRAND_GREEN)
    tree.bind("<<TreeviewSelect>>", lambda _event: bindings.selection_changed())
    y_scroll = ttk.Scrollbar(table_card, orient="vertical", command=tree.yview)
    x_scroll = ttk.Scrollbar(table_card, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
    tree.grid(row=2, column=0, sticky="nsew")
    y_scroll.grid(row=2, column=1, sticky="ns")
    x_scroll.grid(row=3, column=0, sticky="ew")

    status_bar = tk.Frame(root, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
    status_bar.pack(fill="x", side="bottom", before=body)
    tk.Label(
        status_bar,
        textvariable=bindings.status,
        bg=SURFACE,
        fg=MUTED,
        font=("맑은 고딕", 9),
        anchor="w",
    ).pack(fill="x", padx=22, pady=7)
    return TrackerLayoutWidgets(
        refresh_button,
        complete_button,
        pending_button,
        export_button,
        tree,
    )


def status_label(status: EntryStatus) -> str:
    match status:
        case EntryStatus.PENDING:
            return "미입력"
        case EntryStatus.COMPLETED:
            return "입력 완료"
        case unreachable:
            assert_never(unreachable)
