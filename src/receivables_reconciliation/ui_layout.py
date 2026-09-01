from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from tkinter import ttk

from service_validation.brand import BORDER, MUTED, NAVY, SURFACE


@dataclass(frozen=True, slots=True)
class LayoutBindings:
    start_date: tk.StringVar
    end_date: tk.StringVar
    erp_path: tk.StringVar
    status: tk.StringVar
    summary_values: Mapping[str, tk.StringVar]
    choose_erp_file: Callable[[], None]
    start_comparison: Callable[[], None]


@dataclass(frozen=True, slots=True)
class LayoutWidgets:
    start_entry: ttk.Entry
    end_entry: ttk.Entry
    erp_entry: ttk.Entry
    compare_button: ttk.Button
    tree: ttk.Treeview


def build_layout(root: tk.Tk, bindings: LayoutBindings) -> LayoutWidgets:
    header = tk.Frame(root, bg=NAVY, height=112)
    header.pack(fill="x")
    header.pack_propagate(False)
    ttk.Label(header, text="Outlook-ERP 수금 대조", style="Header.TLabel").pack(
        anchor="w", padx=30, pady=(22, 2)
    )
    ttk.Label(
        header,
        text="Outlook 입금 알림과 ERP 수금 등록을 입금일·입금자명으로 비교합니다.",
        style="Subtitle.TLabel",
    ).pack(anchor="w", padx=31)

    body = ttk.Frame(root, style="App.TFrame", padding=(22, 18, 22, 12))
    body.pack(fill="both", expand=True)
    body.columnconfigure(0, weight=1)
    body.rowconfigure(2, weight=1)

    settings = ttk.Frame(body, style="Card.TFrame", padding=18)
    settings.grid(row=0, column=0, sticky="ew")
    settings.columnconfigure(4, weight=1)
    ttk.Label(settings, text="조회 설정", style="Section.TLabel").grid(
        row=0, column=0, columnspan=6, sticky="w", pady=(0, 10)
    )
    ttk.Label(settings, text="시작일", background=SURFACE).grid(row=1, column=0, sticky="w")
    start_entry = ttk.Entry(settings, textvariable=bindings.start_date, width=13)
    start_entry.grid(row=1, column=1, padx=(8, 16), sticky="w")
    ttk.Label(settings, text="종료일", background=SURFACE).grid(row=1, column=2, sticky="w")
    end_entry = ttk.Entry(settings, textvariable=bindings.end_date, width=13)
    end_entry.grid(row=1, column=3, padx=(8, 18), sticky="w")
    ttk.Label(settings, text="ERP 수금 파일", background=SURFACE).grid(
        row=2, column=0, sticky="w", pady=(12, 0)
    )
    erp_entry = ttk.Entry(settings, textvariable=bindings.erp_path)
    erp_entry.grid(row=2, column=1, columnspan=4, padx=(8, 10), pady=(12, 0), sticky="ew")
    ttk.Button(settings, text="파일 선택", command=bindings.choose_erp_file).grid(
        row=2, column=5, pady=(12, 0)
    )
    compare_button = ttk.Button(
        settings,
        text="대조 실행",
        style="Primary.TButton",
        command=bindings.start_comparison,
        state="disabled",
    )
    compare_button.grid(row=1, column=5, sticky="e")
    ttk.Label(
        settings,
        text="날짜 형식: YYYY-MM-DD · 원본 Outlook과 ERP 파일은 변경하지 않습니다.",
        style="Muted.TLabel",
    ).grid(row=3, column=0, columnspan=6, sticky="w", pady=(10, 0))

    summary = ttk.Frame(body, style="Card.TFrame", padding=(18, 12))
    summary.grid(row=1, column=0, sticky="ew", pady=(12, 12))
    for index, (key, label) in enumerate(
        (
            ("outlook", "Outlook 대상"),
            ("erp", "ERP 대상"),
            ("registered", "등록 확인"),
            ("unregistered", "미등록"),
            ("review", "확인 필요"),
        )
    ):
        summary.columnconfigure(index, weight=1)
        item = ttk.Frame(summary, style="Card.TFrame")
        item.grid(row=0, column=index, sticky="ew", padx=8)
        ttk.Label(item, text=label, style="Muted.TLabel").pack()
        ttk.Label(item, textvariable=bindings.summary_values[key], style="Count.TLabel").pack()

    table_card = ttk.Frame(body, style="Card.TFrame", padding=(16, 14))
    table_card.grid(row=2, column=0, sticky="nsew")
    table_card.columnconfigure(0, weight=1)
    table_card.rowconfigure(1, weight=1)
    ttk.Label(table_card, text="미등록 / 확인 필요 목록", style="Section.TLabel").grid(
        row=0, column=0, sticky="w", pady=(0, 10)
    )
    columns = ("status", "date", "amount", "name", "subject", "received", "reason")
    tree = ttk.Treeview(table_card, columns=columns, show="headings")
    headings = {
        "status": "상태",
        "date": "입금일",
        "amount": "입금액",
        "name": "입금자명",
        "subject": "메일 제목",
        "received": "수신 시각",
        "reason": "판정 사유",
    }
    widths = {
        "status": 90,
        "date": 95,
        "amount": 110,
        "name": 130,
        "subject": 240,
        "received": 145,
        "reason": 220,
    }
    for column in columns:
        tree.heading(column, text=headings[column])
        tree.column(
            column,
            width=widths[column],
            minwidth=70,
            anchor="center" if column in {"status", "date", "amount", "received"} else "w",
            stretch=column in {"subject", "reason"},
        )
    y_scroll = ttk.Scrollbar(table_card, orient="vertical", command=tree.yview)
    x_scroll = ttk.Scrollbar(table_card, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
    tree.grid(row=1, column=0, sticky="nsew")
    y_scroll.grid(row=1, column=1, sticky="ns")
    x_scroll.grid(row=2, column=0, sticky="ew")

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
    return LayoutWidgets(start_entry, end_entry, erp_entry, compare_button, tree)
