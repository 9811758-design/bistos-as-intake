from __future__ import annotations

from tkinter import ttk

from .analytics import AnalyticsReport


def summary_text(report: AnalyticsReport) -> str:
    warranty_counts = {item.warranty: item.count for item in report.warranty_counts}
    return (
        f"총 접수 {report.included_row_count:,}건 · "
        f"미처리 {len(report.overdue_rows):,}건 · "
        f"보증 내 {warranty_counts.get('내', 0):,}건 · "
        f"보증 외 {warranty_counts.get('외', 0):,}건"
    )


def is_empty(report: AnalyticsReport) -> bool:
    return (
        report.included_row_count == 0
        and len(report.overdue_rows) == 0
        and len(report.repeat_failures) == 0
        and len(report.monthly_failure_causes) == 0
        and len(report.model_service_counts) == 0
    )


def select_first_row(tree: ttk.Treeview) -> None:
    rows = tree.get_children()
    if rows:
        tree.selection_set(rows[0])
        tree.focus(rows[0])
