from __future__ import annotations

import queue
import threading
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import TypeAlias, assert_never

import pywintypes
from pypdf.errors import PdfReadError

from .excel_export import ExcelUnavailableError, ExcelWorkbookExporter, WorkbookExportError
from .pdf_merge import (
    EmptyMergeError,
    PdfMergeJob,
    create_combined_pdf,
    default_output_path,
    discover_workbooks,
    service_number_from_filename,
)

NAVY = "#172554"
BLUE = "#2563eb"
BACKGROUND = "#f4f7fb"
TEXT = "#172033"
MUTED = "#64748b"


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    current: int
    total: int
    filename: str


@dataclass(frozen=True, slots=True)
class SuccessEvent:
    output: Path


@dataclass(frozen=True, slots=True)
class FailureEvent:
    detail: str


UiEvent: TypeAlias = ProgressEvent | SuccessEvent | FailureEvent


class PdfMergeApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("엑셀 통합 PDF 생성기")
        self.root.geometry("1040x720")
        self.root.minsize(860, 600)
        self.root.configure(bg=BACKGROUND)
        self.folder = tk.StringVar()
        self.output = tk.StringVar()
        self.count = tk.StringVar(value="선택된 결과서 0개")
        self.status = tk.StringVar(value="결과서가 있는 폴더를 선택하세요.")
        self.workbooks: tuple[Path, ...] = ()
        self.events: queue.Queue[UiEvent] = queue.Queue()
        self._configure_styles()
        self._build_ui()
        self.root.after(100, self._poll_events)

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Card.TFrame", background="white")
        style.configure("TLabel", background="white", foreground=TEXT, font=("맑은 고딕", 10))
        style.configure("Title.TLabel", font=("맑은 고딕", 12, "bold"))
        style.configure("Count.TLabel", foreground=BLUE, font=("맑은 고딕", 14, "bold"))
        style.configure("TButton", font=("맑은 고딕", 10), padding=(14, 8))
        style.configure("Primary.TButton", font=("맑은 고딕", 11, "bold"), padding=(20, 12))
        style.map(
            "Primary.TButton",
            background=[("!disabled", BLUE)],
            foreground=[("!disabled", "white")],
        )
        style.configure("Treeview", rowheight=30, font=("맑은 고딕", 10))
        style.configure("Treeview.Heading", font=("맑은 고딕", 10, "bold"))

    def _build_ui(self) -> None:
        header = tk.Frame(self.root, bg=NAVY, height=124)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header, text="엑셀 통합 PDF 생성기", bg=NAVY, fg="white",
            font=("맑은 고딕", 24, "bold"),
        ).pack(anchor="w", padx=34, pady=(24, 4))
        tk.Label(
            header,
            text="완성된 서비스 검증결과서를 서비스번호 순서로 하나의 PDF에 합칩니다.",
            bg=NAVY, fg="#cbd5e1", font=("맑은 고딕", 10),
        ).pack(anchor="w", padx=36)
        main = ttk.Frame(self.root, style="Card.TFrame", padding=24)
        main.pack(fill="both", expand=True, padx=24, pady=22)
        self._build_path_row(main, 0, "결과서 폴더", self.folder, self._choose_folder, "폴더 선택")
        self._build_path_row(main, 1, "저장할 PDF", self.output, self._choose_output, "저장 위치")
        summary = ttk.Frame(main, style="Card.TFrame")
        summary.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(14, 10))
        ttk.Label(summary, textvariable=self.count, style="Count.TLabel").pack(side="left")
        ttk.Label(
            summary, text="발행이력·발행현황·임시 파일은 자동 제외됩니다.", foreground=MUTED,
        ).pack(side="right")
        columns = ("order", "service", "filename")
        self.tree = ttk.Treeview(main, columns=columns, show="headings", height=12)
        self.tree.heading("order", text="순서")
        self.tree.heading("service", text="서비스번호")
        self.tree.heading("filename", text="결과서 파일명")
        self.tree.column("order", width=70, anchor="center", stretch=False)
        self.tree.column("service", width=150, anchor="center", stretch=False)
        self.tree.column("filename", width=650, anchor="w")
        scrollbar = ttk.Scrollbar(main, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=3, column=0, columnspan=2, sticky="nsew")
        scrollbar.grid(row=3, column=2, sticky="ns")
        footer = ttk.Frame(main, style="Card.TFrame")
        footer.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(18, 0))
        self.progress = ttk.Progressbar(footer, mode="determinate")
        self.progress.pack(fill="x", pady=(0, 8))
        ttk.Label(footer, textvariable=self.status, foreground=MUTED).pack(side="left")
        self.create_button = ttk.Button(
            footer, text="통합 PDF 만들기", style="Primary.TButton",
            command=self._start, state="disabled",
        )
        self.create_button.pack(side="right")
        main.columnconfigure(1, weight=1)
        main.rowconfigure(3, weight=1)

    def _build_path_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        command: Callable[[], None],
        button_text: str,
    ) -> None:
        ttk.Label(parent, text=label, style="Title.TLabel").grid(
            row=row, column=0, sticky="w", padx=(0, 16), pady=7
        )
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=7)
        ttk.Button(parent, text=button_text, command=command).grid(
            row=row, column=2, padx=(12, 0), pady=7
        )

    def _choose_folder(self) -> None:
        selected = filedialog.askdirectory(title="검증결과서 엑셀 폴더 선택")
        if not selected:
            return
        folder = Path(selected)
        self.folder.set(str(folder))
        self.output.set(str(default_output_path(folder, datetime.now())))
        self.workbooks = discover_workbooks(folder)
        self._render_workbooks()

    def _choose_output(self) -> None:
        initial = Path(self.output.get()) if self.output.get() else Path.home() / "통합.pdf"
        selected = filedialog.asksaveasfilename(
            title="통합 PDF 저장 위치", initialdir=initial.parent,
            initialfile=initial.name, defaultextension=".pdf",
            filetypes=(("PDF 파일", "*.pdf"),),
        )
        if selected:
            self.output.set(selected)

    def _render_workbooks(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for index, path in enumerate(self.workbooks, 1):
            values = (index, service_number_from_filename(path), path.name)
            self.tree.insert("", "end", values=values)
        self.count.set(f"선택된 결과서 {len(self.workbooks):,}개")
        if self.workbooks:
            self.status.set("목록을 확인한 뒤 통합 PDF 만들기를 누르세요.")
            self.create_button.configure(state="normal")
        else:
            self.status.set("선택한 폴더에 생성된 검증결과서가 없습니다.")
            self.create_button.configure(state="disabled")

    def _start(self) -> None:
        if not self.workbooks or not self.output.get():
            messagebox.showerror("오류", "결과서 폴더와 PDF 저장 위치를 확인하세요.")
            return
        self.create_button.configure(state="disabled")
        self.progress.configure(maximum=len(self.workbooks), value=0)
        self.status.set("Microsoft Excel을 실행하고 있습니다...")
        job = PdfMergeJob(self.workbooks, Path(self.output.get()))
        threading.Thread(target=self._run_job, args=(job,), daemon=True).start()

    def _run_job(self, job: PdfMergeJob) -> None:
        def progress(current: int, total: int, filename: str) -> None:
            self.events.put(ProgressEvent(current, total, filename))
        try:
            result = create_combined_pdf(job, ExcelWorkbookExporter(), progress)
        except (
            EmptyMergeError, ExcelUnavailableError, WorkbookExportError,
            PdfReadError, OSError, pywintypes.com_error,
        ) as exc:
            self.events.put(FailureEvent(str(exc)))
            return
        self.events.put(SuccessEvent(result))

    def _poll_events(self) -> None:
        try:
            while True:
                self._handle_event(self.events.get_nowait())
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _handle_event(self, event: UiEvent) -> None:
        match event:
            case ProgressEvent(current=current, total=total, filename=filename):
                self.progress.configure(value=current, maximum=total)
                self.status.set(f"{current:,}/{total:,} 변환 중: {filename}")
            case SuccessEvent(output=output):
                self.progress.configure(value=len(self.workbooks))
                self.status.set(f"완료: {output.name}")
                self.create_button.configure(state="normal")
                messagebox.showinfo(
                    "통합 PDF 생성 완료",
                    f"결과서 {len(self.workbooks):,}개를 하나의 PDF로 만들었습니다.\n{output}",
                )
            case FailureEvent(detail=detail):
                self.status.set("PDF 생성에 실패했습니다.")
                self.create_button.configure(state="normal")
                messagebox.showerror("PDF 생성 실패", detail)
            case unreachable:
                assert_never(unreachable)
