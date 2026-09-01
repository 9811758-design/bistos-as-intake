from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest


def _bootstrap_tcl_library() -> None:
    if os.environ.get("TCL_LIBRARY") and os.environ.get("TK_LIBRARY"):
        return
    for root in _candidate_tcl_roots():
        tcl = root / "tcl8.6"
        tk = root / "tk8.6"
        if (tcl / "init.tcl").is_file() and (tk / "icons.tcl").is_file():
            os.environ["TCL_LIBRARY"] = str(tcl)
            os.environ["TK_LIBRARY"] = str(tk)
            return


def _candidate_tcl_roots() -> tuple[Path, ...]:
    roots = [Path(sys.base_prefix) / "tcl", Path(sys.prefix) / "tcl"]
    appdata = os.environ.get("APPDATA")
    if appdata:
        roots.extend(Path(appdata).glob("uv/python/*/tcl"))
    return tuple(roots)


_bootstrap_tcl_library()

import tkinter as tk  # noqa: E402

from as_intake.analytics import (  # noqa: E402
    AnalyticsDateRange,
    AnalyticsReport,
    ModelServiceCount,
    MonthlyFailureCause,
    OverdueRow,
    RepeatFailure,
    WarrantyCount,
)
from as_intake.dashboard_dialog import DashboardDialog  # noqa: E402


@pytest.fixture(scope="module")
def root() -> Iterator[tk.Tk]:
    # Given
    window = tk.Tk()
    window.withdraw()
    yield window
    window.destroy()


def _report(
    *,
    included: int = 3,
    excluded: int = 1,
    overdue: tuple[OverdueRow, ...] = (
        OverdueRow("DS26081601", date(2026, 8, 16), 9, "BT350L", "Battery"),
    ),
    warranties: tuple[WarrantyCount, ...] = (
        WarrantyCount("내", 2),
        WarrantyCount("외", 1),
    ),
    repeats: tuple[RepeatFailure, ...] = (
        RepeatFailure("BT350L", "Battery", 2),
    ),
    monthly: tuple[MonthlyFailureCause, ...] = (
        MonthlyFailureCause("2026-08", "Battery", 2),
        MonthlyFailureCause("2026-08", "Cable", 1),
    ),
    models: tuple[ModelServiceCount, ...] = (
        ModelServiceCount("BT350L", 3),
        ModelServiceCount("BCM350", 2),
    ),
) -> AnalyticsReport:
    return AnalyticsReport(
        date_range=AnalyticsDateRange(date(2026, 8, 1), date(2026, 8, 31)),
        included_row_count=included,
        date_unparseable_excluded_count=excluded,
        overdue_rows=overdue,
        warranty_counts=warranties,
        repeat_failures=repeats,
        monthly_failure_causes=monthly,
        model_service_counts=models,
    )


def test_dialog_defaults_to_current_year_through_today(root: tk.Tk) -> None:
    # Given / When
    dialog = DashboardDialog(
        root, refresh_command=lambda _date_range: None, today=date(2026, 8, 25)
    )

    # Then
    assert dialog.start_var.get() == "2026-01-01"
    assert dialog.end_var.get() == "2026-08-25"
    assert dialog.status_var.get() == "조회할 날짜 구간을 입력하세요."
    dialog.destroy()


def test_dialog_calls_refresh_with_inclusive_date_range(root: tk.Tk) -> None:
    # Given
    calls: list[AnalyticsDateRange] = []
    dialog = DashboardDialog(root, refresh_command=calls.append, today=date(2026, 8, 25))
    dialog.start_var.set("2026-08-01")
    dialog.end_var.set("2026-08-31")

    # When
    dialog.refresh()

    # Then
    assert calls == [AnalyticsDateRange(date(2026, 8, 1), date(2026, 8, 31))]
    assert dialog.status_var.get() == "2026-08-01 ~ 2026-08-31 조회 중"
    dialog.destroy()


def test_dialog_rejects_invalid_date_format_before_callback(root: tk.Tk) -> None:
    # Given
    calls: list[AnalyticsDateRange] = []
    dialog = DashboardDialog(root, refresh_command=calls.append, today=date(2026, 8, 25))
    dialog.start_var.set("2026-99-01")
    dialog.end_var.set("2026-08-31")

    # When
    dialog.refresh()

    # Then
    assert calls == []
    assert "YYYY-MM-DD" in dialog.status_var.get()
    dialog.destroy()


def test_dialog_rejects_reversed_range_before_callback(root: tk.Tk) -> None:
    # Given
    calls: list[AnalyticsDateRange] = []
    dialog = DashboardDialog(root, refresh_command=calls.append, today=date(2026, 8, 25))
    dialog.start_var.set("2026-08-31")
    dialog.end_var.set("2026-08-01")

    # When
    dialog.refresh()

    # Then
    assert calls == []
    assert "시작일" in dialog.status_var.get()
    dialog.destroy()


def test_dialog_renders_summary_tabs_excluded_count_and_columns(root: tk.Tk) -> None:
    # Given
    dialog = DashboardDialog(
        root, refresh_command=lambda _date_range: None, today=date(2026, 8, 25)
    )

    # When
    dialog.render(_report())

    # Then
    assert "총 접수 3건" in dialog.summary_var.get()
    assert "미처리 1건" in dialog.summary_var.get()
    assert "보증 내 2건" in dialog.summary_var.get()
    assert "보증 외 1건" in dialog.summary_var.get()
    assert "날짜 판독 제외 1건" in dialog.excluded_var.get()
    assert dialog.tab_labels() == (
        "미처리",
        "모델별 A/S 발생건수",
        "모델별 반복 고장",
        "월별 불량원인",
    )
    assert dialog.table_headings("overdue") == ("접수번호", "접수일", "경과일", "모델", "불량원인")
    assert dialog.table_headings("repeat") == ("모델", "불량원인", "건수")
    assert dialog.table_headings("monthly") == ("월", "불량원인", "건수")
    assert dialog.table_headings("model") == ("모델", "완료 A/S 건수")
    assert dialog.table_values("overdue") == (
        ("DS26081601", "2026-08-16", "9일", "BT350L", "Battery"),
    )
    assert dialog._trees["overdue"].selection()
    assert dialog.table_values("monthly") == (
        ("2026-08", "Battery", "2"),
        ("2026-08", "Cable", "1"),
    )
    assert dialog.table_values("model") == (("BT350L", "3"), ("BCM350", "2"))
    dialog.destroy()


def test_dialog_shows_empty_result_text(root: tk.Tk) -> None:
    # Given
    dialog = DashboardDialog(
        root, refresh_command=lambda _date_range: None, today=date(2026, 8, 25)
    )

    # When
    dialog.render(
        _report(
            included=0,
            excluded=0,
            overdue=(),
            warranties=(),
            repeats=(),
            monthly=(),
            models=(),
        )
    )

    # Then
    assert dialog.status_var.get() == "조회 결과 없음"
    assert dialog.table_values("overdue") == ()
    dialog.destroy()
