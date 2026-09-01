from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox, ttk

from .brand import (
    BACKGROUND,
    BLUE,
    ERROR,
    MUTED,
    NAVY,
    SUCCESS,
    load_header_logo,
    set_window_icon,
)
from .domain import ServiceRecord, ValidationError
from .issuance import append_issuance_log
from .pasted_row import parse_pasted_row
from .service import create_reports
from .validation_rules import build_validation_plan
from .workbook import load_overrides


class QuickEntryWindow:
    def __init__(
        self,
        parent: tk.Tk,
        template: tk.StringVar,
        output: tk.StringVar,
        config_dir: Path,
        on_created: Callable[[], None],
    ) -> None:
        self.template = template
        self.output = output
        self.config_dir = config_dir
        self.on_created = on_created
        self.record: ServiceRecord | None = None
        self.status = tk.StringVar(value="구글시트에서 행 전체를 복사해 아래 칸에 붙여넣으세요.")
        self.preview = tuple(tk.StringVar(value="-") for _ in range(7))
        self.window = tk.Toplevel(parent)
        self.window.title("Bistos | 1건 빠른 발행")
        self.window.geometry("980x700")
        self.window.minsize(820, 620)
        self.window.configure(background=BACKGROUND)
        self.window.transient(parent)
        self.icon_image = set_window_icon(self.window)
        self._build()
        self.window.after(100, self.input.focus_set)

    @property
    def exists(self) -> bool:
        return bool(self.window.winfo_exists())

    def focus(self) -> None:
        self.window.deiconify()
        self.window.lift()
        self.input.focus_set()

    def _build(self) -> None:
        banner = tk.Frame(self.window, bg=NAVY, padx=26, pady=18)
        banner.pack(fill="x")
        self.logo_image = load_header_logo()
        tk.Label(banner, image=self.logo_image, bg=NAVY, borderwidth=0).place(
            relx=1,
            rely=0.5,
            anchor="e",
        )
        tk.Label(
            banner,
            text="1건 빠른 발행",
            bg=NAVY,
            fg="#FFFFFF",
            font=("맑은 고딕", 18, "bold"),
        ).pack(anchor="w")
        tk.Label(
            banner,
            text="구글시트 행 복사 → 붙여넣기 → 검증결과서 1건 생성",
            bg=NAVY,
            fg="#DDECF3",
            font=("맑은 고딕", 10),
        ).pack(anchor="w", pady=(3, 0))

        body = ttk.Frame(self.window, padding=18)
        body.pack(fill="both", expand=True)
        input_card = ttk.LabelFrame(body, text=" 구글시트 행 붙여넣기 ", padding=12)
        input_card.pack(fill="x")
        input_card.columnconfigure(0, weight=1)
        input_card.rowconfigure(0, weight=1)
        self.input = tk.Text(
            input_card,
            height=5,
            wrap="none",
            font=("맑은 고딕", 10),
            relief="solid",
            borderwidth=1,
            undo=True,
        )
        horizontal = ttk.Scrollbar(input_card, orient="horizontal", command=self.input.xview)
        self.input.configure(xscrollcommand=horizontal.set)
        self.input.grid(row=0, column=0, sticky="ew")
        horizontal.grid(row=1, column=0, sticky="ew")
        self.input.bind("<<Paste>>", self._on_paste)
        self.input.bind("<Control-Return>", self._on_generate_shortcut)

        actions = ttk.Frame(input_card)
        actions.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(actions, text="클립보드 붙여넣기", command=self._paste_clipboard).pack(
            side="left"
        )
        ttk.Button(actions, text="내용 분석", command=self._analyze).pack(side="left", padx=7)
        ttk.Button(actions, text="입력 지우기", command=self._clear).pack(side="left")
        ttk.Label(actions, text="단축키: Ctrl+Enter로 생성", foreground=MUTED).pack(side="right")

        preview_card = ttk.LabelFrame(body, text=" 발행 내용 미리보기 ", padding=12)
        preview_card.pack(fill="both", expand=True, pady=(12, 0))
        preview_card.columnconfigure(1, weight=1)
        labels = (
            "서비스번호 / 접수일",
            "고객구분 / 고객명",
            "모델",
            "증상/요청사항",
            "대응조치",
            "처리완료일 / 처리자",
            "PASS / N/A 판정",
        )
        for row, (label, variable) in enumerate(zip(labels, self.preview, strict=True)):
            ttk.Label(preview_card, text=label, width=22, foreground=MUTED).grid(
                row=row, column=0, sticky="nw", pady=5
            )
            ttk.Label(
                preview_card,
                textvariable=variable,
                font=("맑은 고딕", 10, "bold" if row < 3 else "normal"),
                wraplength=660,
                justify="left",
            ).grid(row=row, column=1, sticky="w", pady=5)

        footer = ttk.Frame(body)
        footer.pack(fill="x", pady=(10, 0))
        self.status_label = ttk.Label(footer, textvariable=self.status, foreground=MUTED)
        self.status_label.pack(side="left", fill="x", expand=True)
        self.generate_button = ttk.Button(
            footer,
            text="검증결과서 1건 생성",
            command=self._generate,
            state="disabled",
            style="Success.TButton",
        )
        self.generate_button.pack(side="right")

    def _on_paste(self, _event: tk.Event[tk.Misc]) -> None:
        self.window.after_idle(self._analyze)

    def _on_generate_shortcut(self, _event: tk.Event[tk.Misc]) -> str:
        self._generate()
        return "break"

    def _paste_clipboard(self) -> None:
        try:
            text = self.window.clipboard_get()
        except tk.TclError:
            messagebox.showerror(
                "붙여넣기 오류",
                "클립보드에 텍스트가 없습니다.",
                parent=self.window,
            )
            return
        self.input.delete("1.0", "end")
        self.input.insert("1.0", text)
        self._analyze()

    def _analyze(self) -> None:
        try:
            record = parse_pasted_row(
                self.input.get("1.0", "end-1c"),
                load_overrides(self.config_dir / "customer_overrides.json"),
            )
        except ValidationError as exc:
            self.record = None
            self.generate_button.configure(state="disabled")
            self.status.set(str(exc))
            self.status_label.configure(foreground=ERROR)
            return
        self.record = record
        plan = build_validation_plan(record)
        values = (
            f"{record.service_number} / {record.receipt_date.isoformat()}",
            f"{record.customer.category.value} / {record.customer.display_name}",
            record.model,
            record.service_details,
            record.processing_details,
            f"{record.completion_date.isoformat()} / {record.processor}",
            plan.summary,
        )
        for variable, value in zip(self.preview, values, strict=True):
            variable.set(value)
        self.generate_button.configure(state="normal")
        self.status.set("내용을 확인한 뒤 생성 버튼을 누르세요.")
        self.status_label.configure(foreground=BLUE)

    def _generate(self) -> None:
        if self.record is None:
            self._analyze()
        if self.record is None:
            return
        template = Path(self.template.get())
        output = Path(self.output.get())
        if not template.is_file():
            messagebox.showerror(
                "설정 오류",
                "메인 화면에서 검증결과서 양식을 선택하세요.",
                parent=self.window,
            )
            return
        if not output.is_dir():
            messagebox.showerror(
                "설정 오류",
                "메인 화면에서 저장 폴더를 선택하세요.",
                parent=self.window,
            )
            return
        try:
            result = create_reports(template, output, (self.record,))
            if result.failures:
                raise ValidationError(result.failures[0].detail)
            append_issuance_log(output, result.successful_records, result.outputs)
        except (OSError, ValidationError) as exc:
            messagebox.showerror("생성 오류", str(exc), parent=self.window)
            return
        self.on_created()
        self.status.set(f"저장 완료: {result.outputs[0].name}")
        self.status_label.configure(foreground=SUCCESS)
        self.input.tag_add("sel", "1.0", "end-1c")
        self.input.focus_set()

    def _clear(self) -> None:
        self.record = None
        self.input.delete("1.0", "end")
        for variable in self.preview:
            variable.set("-")
        self.generate_button.configure(state="disabled")
        self.status.set("구글시트에서 행 전체를 복사해 아래 칸에 붙여넣으세요.")
        self.status_label.configure(foreground=MUTED)
        self.input.focus_set()
