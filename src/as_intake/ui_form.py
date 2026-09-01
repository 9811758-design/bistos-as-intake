from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import ttk

from .columns import FORM_SPECS, FieldSpec, FormSection, SheetField
from .numbering import service_number_date
from .policy import (
    FIXED_PROCESSOR,
    NO_PRODUCTION_MONTH_STATUS,
    is_bcm_model,
    warranty_status,
)
from .records import RecordDraft, SheetRow
from .ui_tokens import SURFACE


class BoundText(tk.Text):
    def __init__(self, master: tk.Misc, variable: tk.StringVar) -> None:
        super().__init__(
            master,
            height=3,
            wrap="word",
            font=("맑은 고딕", 10),
            background=SURFACE,
            relief="solid",
            borderwidth=1,
            padx=6,
            pady=5,
        )
        self._variable = variable
        self._updating = False
        variable.trace_add("write", self._from_variable)
        self.bind("<<Modified>>", self._from_widget)

    def _from_variable(self, *_args: str) -> None:
        if self._updating:
            return
        value = self._variable.get()
        if self.get("1.0", "end-1c") == value:
            return
        self._updating = True
        self.delete("1.0", "end")
        self.insert("1.0", value)
        self.edit_modified(False)
        self._updating = False

    def _from_widget(self, _event: tk.Event[tk.Misc]) -> None:
        if self._updating or not self.edit_modified():
            return
        self._updating = True
        self._variable.set(self.get("1.0", "end-1c"))
        self.edit_modified(False)
        self._updating = False


class RecordForm(ttk.Frame):
    def __init__(self, master: tk.Misc, default_receiver: str = "") -> None:
        super().__init__(master, style="Card.TFrame", padding=16)
        self.default_receiver = default_receiver
        self.service_number = tk.StringVar()
        self.receipt_date = tk.StringVar()
        self.mode_text = tk.StringVar()
        self.fields = {spec.field: tk.StringVar() for spec in FORM_SPECS}
        self._loading = False
        self._loaded_row_number: int | None = None
        self._mode_label = ttk.Label(self, textvariable=self.mode_text, style="Mode.TLabel")
        self._mode_label.pack(fill="x", pady=(0, 12))
        self._build_identity()
        self._build_tabs()
        self._bind_warranty_policy()
        self.clear()

    def _build_identity(self) -> None:
        self._identity = ttk.Frame(self, style="Form.TFrame")
        self._identity.pack(fill="x", pady=(0, 12))
        ttk.Label(self._identity, text="서비스 접수번호", background=SURFACE).grid(
            row=0, column=0, sticky="w"
        )
        service_number = ttk.Entry(
            self._identity,
            textvariable=self.service_number,
            state="readonly",
            width=22,
        )
        service_number.grid(
            row=1, column=0, sticky="ew", padx=(0, 12)
        )
        ttk.Label(self._identity, text="접수일 (YYYY-MM-DD)", background=SURFACE).grid(
            row=0, column=1, sticky="w"
        )
        ttk.Entry(self._identity, textvariable=self.receipt_date, width=20).grid(
            row=1, column=1, sticky="ew"
        )
        self._identity.columnconfigure(0, weight=1)
        self._identity.columnconfigure(1, weight=1)

    def _build_tabs(self) -> None:
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)
        for section in FormSection:
            tab, content = self._scrollable_tab(notebook)
            notebook.add(tab, text=section.value)
            specs = [spec for spec in FORM_SPECS if spec.section is section]
            for index, spec in enumerate(specs):
                row, block = divmod(index, 2)
                field_frame = ttk.Frame(content, style="Form.TFrame")
                field_frame.grid(row=row, column=block, sticky="nsew", padx=(0, 12), pady=(7, 5))
                ttk.Label(field_frame, text=spec.label, background=SURFACE).pack(
                    anchor="w", pady=(0, 2)
                )
                widget = self._field_widget(field_frame, spec)
                widget.pack(fill="x")
            content.columnconfigure(0, weight=1, uniform="field")
            content.columnconfigure(1, weight=1, uniform="field")

    def _scrollable_tab(self, notebook: ttk.Notebook) -> tuple[ttk.Frame, ttk.Frame]:
        tab = ttk.Frame(notebook, style="Card.TFrame")
        canvas = tk.Canvas(tab, background=SURFACE, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas, style="Card.TFrame", padding=12)
        window = canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        content.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(window, width=event.width),
        )
        return tab, content

    def _field_widget(
        self,
        master: tk.Misc,
        spec: FieldSpec,
    ) -> ttk.Entry | ttk.Combobox | BoundText:
        variable = self.fields[spec.field]
        if spec.multiline:
            return BoundText(master, variable)
        if spec.field is SheetField.PROCESSOR:
            return ttk.Entry(master, textvariable=variable, state="readonly")
        if spec.options:
            return ttk.Combobox(
                master,
                textvariable=variable,
                values=spec.options,
                state="normal",
            )
        return ttk.Entry(master, textvariable=variable)

    def _bind_warranty_policy(self) -> None:
        self.fields[SheetField.MODEL].trace_add("write", self._update_bcm_defaults)
        for variable in (
            self.receipt_date,
            self.fields[SheetField.MODEL],
            self.fields[SheetField.PRODUCTION_MONTH],
        ):
            variable.trace_add("write", self._update_warranty_from_policy)

    def _update_bcm_defaults(self, *_args: str) -> None:
        if self._loading or not is_bcm_model(self.fields[SheetField.MODEL].get()):
            return
        self.fields[SheetField.SERIAL_NUMBER].set(NO_PRODUCTION_MONTH_STATUS)
        self.fields[SheetField.PRODUCTION_MONTH].set(NO_PRODUCTION_MONTH_STATUS)

    def _update_warranty_from_policy(self, *_args: str) -> None:
        if self._loading:
            return
        try:
            received_on = date.fromisoformat(self.receipt_date.get().strip())
        except ValueError:
            return
        status = warranty_status(
            self.fields[SheetField.MODEL].get(),
            self.fields[SheetField.PRODUCTION_MONTH].get(),
            received_on,
        )
        if status is not None:
            self.fields[SheetField.WARRANTY].set(status)

    def clear(self) -> None:
        self._loading = True
        self._loaded_row_number = None
        self.service_number.set("")
        self.receipt_date.set(date.today().isoformat())
        for variable in self.fields.values():
            variable.set("")
        self.fields[SheetField.RECEIVER].set(self.default_receiver)
        self.fields[SheetField.PROCESSOR].set(FIXED_PROCESSOR)
        self._loading = False
        self._update_warranty_from_policy()
        self.mode_text.set("신규 접수 · 저장 시 접수번호가 자동 생성됩니다")
        self._mode_label.configure(style="Mode.TLabel")

    def set_value(self, field: SheetField, value: str) -> None:
        self.fields[field].set(FIXED_PROCESSOR if field is SheetField.PROCESSOR else value)

    def draft(self) -> RecordDraft:
        parsed_date = date.fromisoformat(self.receipt_date.get().strip())
        values = {field: variable.get() for field, variable in self.fields.items()}
        values[SheetField.PROCESSOR] = FIXED_PROCESSOR
        return RecordDraft.create(parsed_date, values)

    def sheet_row(self) -> SheetRow:
        service_number = self.service_number.get().strip()
        row = self.draft().to_sheet_row(service_number)
        return SheetRow(row.values, self._loaded_row_number)

    def load(self, row: SheetRow) -> None:
        number = row.value(SheetField.SERVICE_NUMBER)
        self._loading = True
        self._loaded_row_number = row.row_number
        self.service_number.set(number)
        parsed_date = service_number_date(number)
        self.receipt_date.set(parsed_date.isoformat() if parsed_date else date.today().isoformat())
        for field, variable in self.fields.items():
            variable.set(row.value(field))
        self.fields[SheetField.PROCESSOR].set(FIXED_PROCESSOR)
        self._loading = False
        self.mode_text.set(f"기존 행 덮어쓰기 · {number} · 마지막 저장 내용으로 반영")
        self._mode_label.configure(style="Overwrite.TLabel")
