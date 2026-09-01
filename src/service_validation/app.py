from __future__ import annotations

import json
import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .domain import ServiceRecord, ValidationError
from .issuance import (
    append_issuance_log,
    load_issued_counts,
    record_key,
    write_status_report,
)
from .selection import MAX_BATCH_SIZE, BatchSelection
from .service import create_reports
from .validation_rules import build_validation_plan
from .workbook import SourceRows, load_overrides, read_source

NAVY = "#172554"
BLUE = "#2563eb"
PALE_BLUE = "#dbeafe"
BACKGROUND = "#f4f7fb"
TEXT = "#172033"
MUTED = "#64748b"


class GeneratorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("서비스 검증결과서 생성기")
        self.root.geometry("1180x760")
        self.root.minsize(940, 620)
        self.records: tuple[ServiceRecord, ...] = ()
        self.source_rows: SourceRows | None = None
        self.issued_indices: set[int] = set()
        self.selection = BatchSelection()
        self.source = tk.StringVar()
        self.template = tk.StringVar()
        self.output = tk.StringVar()
        self.status = tk.StringVar(value="원본 엑셀을 선택하면 발행 가능한 항목을 불러옵니다.")
        self.selection_status = tk.StringVar(value="선택 0개 / 최대 500개")
        self.page_status = tk.StringVar(value="1 / 1 묶음")
        self._configure_style()
        self._build()
        self._load_settings()

    def _configure_style(self) -> None:
        self.root.configure(background=BACKGROUND)
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("App.TFrame", background=BACKGROUND)
        style.configure("Card.TFrame", background="white")
        style.configure(
            "Header.TLabel", background=NAVY, foreground="white", font=("맑은 고딕", 19, "bold")
        )
        style.configure(
            "Subtitle.TLabel", background=NAVY, foreground="#cbd5e1", font=("맑은 고딕", 10)
        )
        style.configure(
            "Section.TLabel", background="white", foreground=TEXT, font=("맑은 고딕", 11, "bold")
        )
        style.configure("Muted.TLabel", background="white", foreground=MUTED, font=("맑은 고딕", 9))
        style.configure(
            "Count.TLabel", background="white", foreground=BLUE, font=("맑은 고딕", 10, "bold")
        )
        style.configure("Primary.TButton", font=("맑은 고딕", 10, "bold"), padding=(18, 9))
        style.configure("Tool.TButton", font=("맑은 고딕", 9), padding=(11, 6))
        style.configure(
            "Treeview",
            font=("맑은 고딕", 9),
            rowheight=30,
            background="white",
            fieldbackground="white",
            foreground=TEXT,
        )
        style.configure("Treeview.Heading", font=("맑은 고딕", 9, "bold"), padding=(7, 8))
        style.map("Treeview", background=[("selected", PALE_BLUE)], foreground=[("selected", TEXT)])

    def _build(self) -> None:
        header = ttk.Frame(self.root, style="Card.TFrame")
        header.pack(fill="x")
        banner = tk.Frame(header, bg=NAVY, padx=26, pady=18)
        banner.pack(fill="x")
        ttk.Label(banner, text="서비스 검증결과서 생성기", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            banner,
            text="엑셀 데이터를 선택해 최대 500건의 검증결과서를 한 번에 발행합니다.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(3, 0))

        body = ttk.Frame(self.root, style="App.TFrame", padding=(24, 18, 24, 20))
        body.pack(fill="both", expand=True)
        file_card = ttk.Frame(body, style="Card.TFrame", padding=16)
        file_card.pack(fill="x")
        ttk.Label(file_card, text="파일 설정", style="Section.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 9)
        )
        file_card.columnconfigure(1, weight=1)
        for row, (label, variable, command) in enumerate(
            (
                ("원본 엑셀", self.source, self._choose_source),
                ("검증결과서 양식", self.template, self._choose_template),
                ("저장 폴더", self.output, self._choose_output),
            ),
            start=1,
        ):
            ttk.Label(file_card, text=label, width=17, style="Muted.TLabel").grid(
                row=row, column=0, sticky="w", pady=4
            )
            ttk.Entry(file_card, textvariable=variable).grid(
                row=row, column=1, sticky="ew", padx=(0, 8), pady=4, ipady=4
            )
            ttk.Button(file_card, text="찾아보기", command=command, style="Tool.TButton").grid(
                row=row, column=2, pady=4
            )

        list_card = ttk.Frame(body, style="Card.TFrame", padding=16)
        list_card.pack(fill="both", expand=True, pady=(14, 0))
        toolbar = ttk.Frame(list_card, style="Card.TFrame")
        toolbar.pack(fill="x", pady=(0, 10))
        ttk.Label(toolbar, text="발행 항목", style="Section.TLabel").pack(side="left")
        ttk.Label(toolbar, textvariable=self.selection_status, style="Count.TLabel").pack(
            side="left", padx=(12, 18)
        )
        ttk.Button(
            toolbar,
            text="선택한 검증결과서 생성",
            command=self._generate,
            style="Primary.TButton",
        ).pack(side="right")

        controls = ttk.Frame(list_card, style="Card.TFrame")
        controls.pack(fill="x", pady=(0, 10))
        ttk.Button(
            controls,
            text="현재 묶음 전체 선택",
            command=self._select_page,
            style="Tool.TButton",
        ).pack(side="left")
        ttk.Button(
            controls, text="선택 해제", command=self._clear_selection, style="Tool.TButton"
        ).pack(side="left", padx=6)
        ttk.Button(
            controls, text="이전 500건", command=lambda: self._move_page(-1), style="Tool.TButton"
        ).pack(side="left", padx=(12, 0))
        ttk.Label(controls, textvariable=self.page_status, style="Muted.TLabel").pack(
            side="left", padx=10
        )
        ttk.Button(
            controls, text="다음 500건", command=lambda: self._move_page(1), style="Tool.TButton"
        ).pack(side="left")
        ttk.Button(
            controls,
            text="발행 현황 엑셀 저장",
            command=self._export_status,
            style="Tool.TButton",
        ).pack(side="left", padx=(12, 0))
        ttk.Label(
            controls,
            text="행을 클릭하면 체크/해제됩니다. Ctrl 키는 필요 없습니다.",
            style="Muted.TLabel",
        ).pack(side="right")

        table_frame = ttk.Frame(list_card, style="Card.TFrame")
        table_frame.pack(fill="both", expand=True)
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        columns = (
            "check",
            "status",
            "service",
            "requester",
            "hospital",
            "model",
            "rule",
            "symptom",
            "date",
        )
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="none")
        headings = (
            "선택",
            "발행상태",
            "서비스번호",
            "의뢰자",
            "병원명",
            "모델",
            "검증판정",
            "증상/요청사항",
            "완료일",
        )
        widths = (58, 90, 120, 145, 170, 90, 560, 360, 105)
        for key, title, width in zip(columns, headings, widths, strict=True):
            self.table.heading(key, text=title)
            self.table.column(
                key,
                width=width,
                minwidth=50,
                anchor="center" if key in {"check", "status", "service", "model", "date"} else "w",
            )
        self.table.tag_configure("checked", background=PALE_BLUE)
        self.table.tag_configure("issued", background="#dcfce7")
        self.table.bind("<Button-1>", self._toggle_row)
        vertical = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        horizontal = ttk.Scrollbar(table_frame, orient="horizontal", command=self.table.xview)
        self.table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")

        status_bar = ttk.Frame(body, style="App.TFrame")
        status_bar.pack(fill="x", pady=(10, 0))
        ttk.Label(
            status_bar,
            textvariable=self.status,
            background=BACKGROUND,
            foreground=MUTED,
            font=("맑은 고딕", 9),
        ).pack(side="left")

    def _choose_source(self) -> None:
        selected = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx")])
        if selected:
            self.source.set(selected)
            self._reload_rows()

    def _choose_template(self) -> None:
        selected = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx")])
        if selected:
            self.template.set(selected)

    def _choose_output(self) -> None:
        selected = filedialog.askdirectory()
        if selected:
            self.output.set(selected)
            self._refresh_issued()
            self._render_page()

    def _reload_rows(self) -> None:
        self.status.set("원본 엑셀을 불러오는 중입니다. 잠시 기다려 주세요.")
        self.root.update_idletasks()
        try:
            source = read_source(
                Path(self.source.get()),
                load_overrides(self._config_dir() / "customer_overrides.json"),
            )
        except (OSError, ValidationError) as exc:
            messagebox.showerror("오류", str(exc))
            return
        self.records = source.records
        self.source_rows = source
        self.selection.reset(len(self.records))
        self._refresh_issued()
        self.status.set(
            f"발행 가능 {len(self.records):,}건 · 미완료/오류 제외 {source.skipped_rows:,}건"
        )
        self._render_page()

    def _render_page(self) -> None:
        self.table.delete(*self.table.get_children())
        for index in self.selection.page_indices:
            record = self.records[index]
            checked = index in self.selection.selected
            issued = index in self.issued_indices
            self.table.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    "☑" if checked else "☐",
                    "발행완료" if issued else "미발행",
                    record.service_number,
                    record.requester,
                    record.hospital,
                    record.model,
                    build_validation_plan(record).summary,
                    record.service_details,
                    record.completion_date.isoformat(),
                ),
                tags=self._row_tags(index),
            )
        self.page_status.set(f"{self.selection.page + 1} / {self.selection.page_count} 묶음")
        self._update_selection_status()

    def _toggle_row(self, event: tk.Event[tk.Misc]) -> str | None:
        row = self.table.identify_row(event.y)
        if not row:
            return None
        if not self.selection.toggle(int(row)):
            messagebox.showwarning(
                "선택 제한", f"한 번에 최대 {MAX_BATCH_SIZE}개까지 선택할 수 있습니다."
            )
            return "break"
        checked = int(row) in self.selection.selected
        self.table.set(row, "check", "☑" if checked else "☐")
        self.table.item(row, tags=self._row_tags(int(row)))
        self._update_selection_status()
        return "break"

    def _select_page(self) -> None:
        self.selection.select_page()
        self._render_page()

    def _clear_selection(self) -> None:
        self.selection.clear()
        self._render_page()

    def _move_page(self, offset: int) -> None:
        self.selection.move(offset)
        self._render_page()

    def _update_selection_status(self) -> None:
        self.selection_status.set(
            f"선택 {len(self.selection.selected):,}개 / 최대 {MAX_BATCH_SIZE}개"
        )

    def _row_tags(self, index: int) -> tuple[str, ...]:
        if index in self.selection.selected:
            return ("checked",)
        if index in self.issued_indices:
            return ("issued",)
        return ()

    def _refresh_issued(self) -> None:
        self.issued_indices.clear()
        if not self.output.get() or not Path(self.output.get()).exists():
            return
        try:
            remaining = load_issued_counts(Path(self.output.get()))
        except ValidationError as exc:
            messagebox.showerror("발행이력 오류", str(exc))
            return
        for index, record in enumerate(self.records):
            key = record_key(record)
            if remaining[key] > 0:
                self.issued_indices.add(index)
                remaining[key] -= 1

    def _export_status(self) -> None:
        if self.source_rows is None:
            messagebox.showerror("오류", "먼저 원본 엑셀을 선택하세요.")
            return
        if not self.output.get():
            messagebox.showerror("오류", "저장 폴더를 선택하세요.")
            return
        try:
            counts = load_issued_counts(Path(self.output.get()))
            report = write_status_report(Path(self.output.get()), self.source_rows, counts)
        except (OSError, ValidationError) as exc:
            messagebox.showerror("오류", str(exc))
            return
        messagebox.showinfo("발행 현황 저장 완료", f"발행 현황을 저장했습니다.\n{report}")

    def _generate(self) -> None:
        if not self.selection.selected:
            messagebox.showerror("오류", "생성할 행을 하나 이상 선택하세요.")
            return
        try:
            selected_records = tuple(
                self.records[index] for index in sorted(self.selection.selected)
            )
            result = create_reports(
                Path(self.template.get()),
                Path(self.output.get()),
                selected_records,
            )
            history = None
            if result.outputs:
                history = append_issuance_log(
                    Path(self.output.get()),
                    result.successful_records,
                    result.outputs,
                )
            self._refresh_issued()
            self._render_page()
            self._save_settings()
        except (OSError, ValidationError) as exc:
            messagebox.showerror("오류", str(exc))
            return
        if result.failures:
            failure_lines = "\n".join(
                f"{failure.record.service_number}: {failure.detail}"
                for failure in result.failures[:5]
            )
            more = len(result.failures) - 5
            if more > 0:
                failure_lines += f"\n외 {more:,}건"
            messagebox.showwarning(
                "부분 완료",
                f"검증결과서 {len(result.outputs):,}개 저장, "
                f"{len(result.failures):,}개 실패했습니다.\n"
                "성공한 파일과 발행이력은 보존되었습니다.\n\n"
                f"{failure_lines}",
            )
            return
        messagebox.showinfo(
            "완료",
            f"검증결과서 {len(result.outputs):,}개를 저장했습니다.\n발행이력: {history}",
        )

    @staticmethod
    def _config_dir() -> Path:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ServiceValidationGenerator"
        base.mkdir(parents=True, exist_ok=True)
        return base

    def _load_settings(self) -> None:
        path = self._config_dir() / "settings.json"
        if not path.exists():
            return
        try:
            values = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(values, dict):
            self.source.set(str(values.get("source", "")))
            self.template.set(str(values.get("template", "")))
            self.output.set(str(values.get("output", "")))
            if self.source.get() and Path(self.source.get()).exists():
                self.root.after(250, self._reload_rows)

    def _save_settings(self) -> None:
        values = {
            "source": self.source.get(),
            "template": self.template.get(),
            "output": self.output.get(),
        }
        (self._config_dir() / "settings.json").write_text(
            json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8"
        )
