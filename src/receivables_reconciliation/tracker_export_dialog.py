from __future__ import annotations

import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox

from receivables_reconciliation.tracker_export import export_tasks
from receivables_reconciliation.tracker_models import TaskFilter
from receivables_reconciliation.tracker_service import TrackerService
from receivables_reconciliation.tracker_store import TaskStoreError


def export_all_tasks(
    root: tk.Tk,
    service: TrackerService,
    status: tk.StringVar,
) -> None:
    selected = filedialog.asksaveasfilename(
        parent=root,
        title="입금메일 목록 Excel 저장",
        defaultextension=".xlsx",
        initialfile=f"입금메일_정리_{date.today():%Y%m%d}.xlsx",
        filetypes=(("Excel 통합 문서", "*.xlsx"),),
    )
    if not selected:
        return
    try:
        snapshot = service.load(TaskFilter.ALL)
        export_tasks(Path(selected), snapshot.tasks)
    except (OSError, TaskStoreError) as exc:
        messagebox.showerror("Excel 저장 실패", str(exc), parent=root)
        return
    status.set(f"전체 목록을 Excel로 저장했습니다: {selected}")
