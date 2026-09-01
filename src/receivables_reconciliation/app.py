from __future__ import annotations

import json
import os
import queue
import threading
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import TypeAlias, assert_never

from receivables_reconciliation.models import MatchStatus
from receivables_reconciliation.service import (
    ReconciliationPipelineError,
    ReconciliationReport,
    ReconciliationRequest,
)
from receivables_reconciliation.ui_layout import LayoutBindings, build_layout
from service_validation.brand import (
    BACKGROUND,
    configure_styles,
    set_window_icon,
)

ReconciliationRunner = Callable[[ReconciliationRequest], ReconciliationReport]


@dataclass(frozen=True, slots=True)
class SuccessEvent:
    report: ReconciliationReport


@dataclass(frozen=True, slots=True)
class FailureEvent:
    detail: str


UiEvent: TypeAlias = SuccessEvent | FailureEvent


class ReceivablesReconciliationApp:
    def __init__(self, root: tk.Tk, runner: ReconciliationRunner) -> None:
        self.root = root
        self._runner = runner
        self._events: queue.Queue[UiEvent] = queue.Queue()
        self._icon: tk.PhotoImage | None = None
        self.root.title("Outlook-ERP 수금 대조")
        self.root.geometry("1120x720")
        self.root.minsize(940, 620)
        self.root.configure(background=BACKGROUND)
        configure_styles(root)
        self.start_date = tk.StringVar(value=date.today().isoformat())
        self.end_date = tk.StringVar(value=date.today().isoformat())
        self.erp_path = tk.StringVar()
        self.status = tk.StringVar(value="조회 기간과 ERP 수금 파일을 선택하세요.")
        self.summary_values = {
            "outlook": tk.StringVar(value="0"),
            "erp": tk.StringVar(value="0"),
            "registered": tk.StringVar(value="0"),
            "unregistered": tk.StringVar(value="0"),
            "review": tk.StringVar(value="0"),
        }
        self._build_ui()
        self._load_settings()
        self._set_icon()
        for variable in (self.start_date, self.end_date, self.erp_path):
            variable.trace_add("write", self._on_input_change)
        self._refresh_ready_state()
        self.root.after(100, self._poll_events)

    def _build_ui(self) -> None:
        widgets = build_layout(
            self.root,
            LayoutBindings(
                start_date=self.start_date,
                end_date=self.end_date,
                erp_path=self.erp_path,
                status=self.status,
                summary_values=self.summary_values,
                choose_erp_file=self._choose_erp_file,
                start_comparison=self._start,
            ),
        )
        self.start_entry = widgets.start_entry
        self.end_entry = widgets.end_entry
        self.erp_entry = widgets.erp_entry
        self.compare_button = widgets.compare_button
        self.tree = widgets.tree

    def _set_icon(self) -> None:
        try:
            self._icon = set_window_icon(self.root)
        except (tk.TclError, OSError):
            self._icon = None

    def _on_input_change(self, *_args: str) -> None:
        self._refresh_ready_state()

    def _refresh_ready_state(self) -> None:
        ready = self._input_error() is None
        self.compare_button.configure(state="normal" if ready else "disabled")

    def _input_error(self) -> str | None:
        try:
            start = date.fromisoformat(self.start_date.get().strip())
            end = date.fromisoformat(self.end_date.get().strip())
        except ValueError:
            return "조회일은 YYYY-MM-DD 형식으로 입력하세요."
        if start > end:
            return "시작일은 종료일보다 늦을 수 없습니다."
        path_text = self.erp_path.get().strip()
        if not path_text:
            return "ERP 수금 파일을 선택하세요."
        path = Path(path_text)
        if path.suffix.casefold() != ".xls":
            return "ERP 수금 파일은 .xls 형식이어야 합니다."
        if not path.is_file():
            return "선택한 ERP 수금 파일을 찾을 수 없습니다."
        return None

    def _choose_erp_file(self) -> None:
        selected = filedialog.askopenfilename(
            title="ERP 수금 등록 파일 선택",
            filetypes=(("ERP Excel 97-2003", "*.xls"),),
        )
        if selected:
            self.erp_path.set(selected)
            self._save_settings()

    def _start(self) -> None:
        error = self._input_error()
        if error is not None:
            self.status.set(error)
            messagebox.showerror("입력 확인", error)
            return
        request = ReconciliationRequest(
            date.fromisoformat(self.start_date.get().strip()),
            date.fromisoformat(self.end_date.get().strip()),
            Path(self.erp_path.get().strip()),
        )
        self.compare_button.configure(state="disabled")
        self.status.set("Outlook과 ERP 수금 내역을 읽고 있습니다...")
        self._clear_results()
        self._save_settings()
        threading.Thread(target=self._run, args=(request,), daemon=True).start()

    def _run(self, request: ReconciliationRequest) -> None:
        try:
            report = self._runner(request)
        except (
            ModuleNotFoundError,
            ReconciliationPipelineError,
            OSError,
            TypeError,
            ValueError,
        ) as exc:
            self._events.put(FailureEvent(str(exc)))
            return
        self._events.put(SuccessEvent(report))

    def _poll_events(self) -> None:
        while True:
            try:
                self._handle_event(self._events.get_nowait())
            except queue.Empty:
                break
        self.root.after(100, self._poll_events)

    def _handle_event(self, event: UiEvent) -> None:
        match event:
            case SuccessEvent(report=report):
                self._render_report(report)
                self.compare_button.configure(state="normal")
            case FailureEvent(detail=detail):
                self.status.set(f"대조에 실패했습니다: {detail}")
                self.compare_button.configure(state="normal")
                messagebox.showerror("수금 대조 실패", detail)
            case unreachable:
                assert_never(unreachable)

    def _render_report(self, report: ReconciliationReport) -> None:
        summary = report.summary
        self.summary_values["outlook"].set(f"{summary.total_candidates:,}")
        self.summary_values["erp"].set(f"{summary.erp_registration_count:,}")
        self.summary_values["registered"].set(f"{summary.registered_count:,}")
        self.summary_values["unregistered"].set(f"{summary.unregistered_count:,}")
        self.summary_values["review"].set(f"{summary.review_needed_count:,}")
        self.tree.delete(*self.tree.get_children())
        for row in report.actionable_rows:
            self.tree.insert(
                "",
                "end",
                values=(
                    _status_label(row.status),
                    row.deposit_date.isoformat() if row.deposit_date else "-",
                    f"{row.amount:,}원" if row.amount is not None else "-",
                    row.depositor_name or "-",
                    row.subject,
                    row.received_at.strftime("%Y-%m-%d %H:%M"),
                    _reason_label(row.reason),
                ),
            )
        if report.actionable_rows:
            self.status.set(f"대조 완료: 확인할 항목 {len(report.actionable_rows):,}건")
        else:
            self.status.set("대조 완료: 미등록 또는 확인 필요 항목이 없습니다.")

    def _clear_results(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for value in self.summary_values.values():
            value.set("0")

    @staticmethod
    def _config_dir() -> Path:
        base = os.getenv("LOCALAPPDATA")
        return Path(base) / "ReceivablesReconciliation" if base else Path.home() / ".receivables"

    def _load_settings(self) -> None:
        path = self._config_dir() / "settings.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return
        last_path = data.get("erp_path")
        if isinstance(last_path, str):
            self.erp_path.set(last_path)

    def _save_settings(self) -> None:
        directory = self._config_dir()
        try:
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "settings.json").write_text(
                json.dumps({"erp_path": self.erp_path.get().strip()}, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            return


def _status_label(status: MatchStatus) -> str:
    match status:
        case MatchStatus.UNREGISTERED:
            return "미등록"
        case MatchStatus.REVIEW_NEEDED:
            return "확인 필요"
        case MatchStatus.REGISTERED:
            return "등록 확인"
        case unreachable:
            assert_never(unreachable)


def _reason_label(reason: str) -> str:
    labels = {
        "exact_match": "입금일과 입금자명이 일치합니다.",
        "no_erp_registration": "같은 입금일과 입금자명의 ERP 등록이 없습니다.",
        "ambiguous_match": "같은 조건의 내역이 여러 건이거나 개인고객 비고를 확인해야 합니다.",
    }
    return labels.get(reason, reason)
