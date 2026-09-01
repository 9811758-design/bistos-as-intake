from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from threading import Event
from typing import TypeVar

from as_intake.app import ASIntakeApp
from as_intake.background import BackgroundTkRunner
from as_intake.columns import FORM_SPECS, SheetField
from as_intake.demo_gateway import DemoSheetGateway
from as_intake.feedback import LocalRecommendationFeedbackStore, case_feedback_key
from as_intake.recommendation import CaseRecommendation
from as_intake.service import ASIntakeService
from receivables_reconciliation.main import create_root

T = TypeVar("T")


class InlineRunner:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.closed = False
        self.submissions = 0

    def submit(
        self,
        work: Callable[[], T],
        on_success: Callable[[T], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        self.submissions += 1
        try:
            result = work()
        except Exception as exc:
            self.root.after(0, lambda saved_error=exc: on_error(saved_error))
            return
        self.root.after(0, lambda saved_result=result: on_success(saved_result))

    def close(self) -> None:
        self.closed = True


def _app() -> tuple[tk.Tk, ASIntakeApp, DemoSheetGateway]:
    root = create_root()
    root.withdraw()
    gateway = DemoSheetGateway()
    app = ASIntakeApp(
        root,
        ASIntakeService(gateway),
        default_receiver="장진영",
        runner=InlineRunner(root),
        today_provider=lambda: date(2026, 8, 25),
    )
    root.update()
    return root, app, gateway


def test_form_exposes_every_business_field_except_three_automatic_columns() -> None:
    root, app, _gateway = _app()

    try:
        assert len(FORM_SPECS) == 33
        assert set(app.form.fields) == {spec.field for spec in FORM_SPECS}
        assert SheetField.SPACER not in app.form.fields
    finally:
        root.destroy()


def test_new_save_generates_service_number_and_adds_searchable_row() -> None:
    root, app, gateway = _app()
    app.form.receipt_date.set("2026-08-25")
    app.form.set_value(SheetField.REQUESTER, "새 의뢰자")
    app.form.set_value(SheetField.MODEL, "BT710")
    app.form.set_value(SheetField.SYMPTOM, "화면이 켜지지 않음")

    app._register()

    try:
        assert gateway.rows[0].value(SheetField.SERVICE_NUMBER) == "DS26082501"
        assert app.form.service_number.get() == "DS26082501"
        assert "저장 완료" in app.status.get()
    finally:
        root.destroy()


def test_search_select_and_overwrite_existing_row() -> None:
    root, app, gateway = _app()
    app.search.query.set("국제메디칼")
    app._search()
    first = app.search.tree.get_children()[0]
    app.search.tree.selection_set(first)
    app._select_result()
    app.form.set_value(SheetField.SYMPTOM, "수정된 증상")

    app._overwrite()

    try:
        assert gateway.rows[0].value(SheetField.SYMPTOM) == "수정된 증상"
        assert "덮어쓰기 완료" in app.status.get()
    finally:
        root.destroy()


def test_invalid_receipt_date_is_rejected_without_inserting() -> None:
    root, app, gateway = _app()
    before = tuple(gateway.rows)
    app.form.receipt_date.set("2026-99-99")

    app._register()

    try:
        assert tuple(gateway.rows) == before
        assert "저장 실패" in app.status.get()
    finally:
        root.destroy()


def test_recommendation_action_is_discoverable_in_the_editor_toolbar() -> None:
    # Given
    root, app, _gateway = _app()

    # When
    label = app.recommend_button.cget("text")

    # Then
    try:
        assert "해결 추천" in label
    finally:
        root.destroy()


def test_header_logo_is_visible_and_subtitle_is_not_clipped_at_minimum_width() -> None:
    # Given
    root, app, _gateway = _app()
    root.deiconify()
    root.geometry("1080x680")
    root.update()

    # When
    header_bottom = app._header.winfo_rooty() + app._header.winfo_height()
    subtitle_bottom = app._header_subtitle.winfo_rooty() + app._header_subtitle.winfo_height()

    # Then
    try:
        assert app._header_logo.winfo_ismapped()
        assert subtitle_bottom <= header_bottom
    finally:
        root.destroy()


def test_nested_form_rows_do_not_draw_card_borders_through_labels() -> None:
    # Given
    root, app, _gateway = _app()

    # When / Then
    try:
        assert app.search._filters.cget("style") == "Form.TFrame"
        assert app.form._identity.cget("style") == "Form.TFrame"
    finally:
        root.destroy()


def test_apply_recommendation_fills_cause_and_action_without_changing_symptom() -> None:
    # Given
    root, app, gateway = _app()
    source = gateway.rows[0].with_value(SheetField.FAILURE_CAUSE, "전원부 접촉 불량")
    source = source.with_value(SheetField.ACTION, "전원 커넥터 재결합")
    app.form.set_value(SheetField.SYMPTOM, "사용자가 입력한 증상")

    # When
    app._apply_recommendation(CaseRecommendation(source, 91), include_cause=True)

    # Then
    try:
        assert app.form.fields[SheetField.SYMPTOM].get() == "사용자가 입력한 증상"
        assert app.form.fields[SheetField.FAILURE_CAUSE].get() == "전원부 접촉 불량"
        assert app.form.fields[SheetField.ACTION].get() == "전원 커넥터 재결합"
        assert "추천 적용" in app.status.get()
    finally:
        root.destroy()


def test_apply_recommendation_records_feedback_for_future_ranking(tmp_path: Path) -> None:
    # Given
    root = create_root()
    root.withdraw()
    gateway = DemoSheetGateway()
    feedback = LocalRecommendationFeedbackStore(tmp_path / "feedback.json")
    app = ASIntakeApp(root, ASIntakeService(gateway, feedback), default_receiver="장진영")
    source = gateway.rows[0].with_value(SheetField.ACTION, "전원 커넥터 재결합")

    # When
    app._apply_recommendation(CaseRecommendation(source, 91), include_cause=True)

    # Then
    try:
        assert feedback.counts()[case_feedback_key(source)] == 1
        assert "학습" in app.status.get()
    finally:
        root.destroy()


def test_recommend_requires_a_symptom_or_cause_before_reading_history() -> None:
    # Given
    root, app, _gateway = _app()

    # When
    app._recommend()

    # Then
    try:
        assert "증상 또는 불량원인" in app.status.get()
    finally:
        root.destroy()


def test_startup_overdue_banner_refreshes_without_modal() -> None:
    # Given / When
    root, app, _gateway = _app()

    # Then
    try:
        assert "미처리 2건" in app.overdue_banner.text.get()
        assert "미처리 보기" in app.overdue_banner.view_button.cget("text")
    finally:
        root.destroy()


def test_overdue_banner_shows_empty_state_for_six_day_or_completed_rows_only() -> None:
    # Given
    root = create_root()
    root.withdraw()
    gateway = DemoSheetGateway()
    gateway.rows = [
        gateway.rows[2],
        gateway.rows[3],
    ]

    # When
    app = ASIntakeApp(
        root,
        ASIntakeService(gateway),
        default_receiver="장진영",
        runner=InlineRunner(root),
        today_provider=lambda: date(2026, 8, 25),
    )
    root.update()

    # Then
    try:
        assert "미처리 0건" in app.overdue_banner.text.get()
        assert "지연 없음" in app.overdue_banner.text.get()
    finally:
        root.destroy()


def test_overdue_banner_shows_read_error_without_startup_modal() -> None:
    # Given
    class FailingGateway(DemoSheetGateway):
        def read_rows(self, year: int):
            raise LookupError(f"{year}년 탭 없음")

    root = create_root()
    root.withdraw()

    # When
    app = ASIntakeApp(
        root,
        ASIntakeService(FailingGateway()),
        default_receiver="장진영",
        runner=InlineRunner(root),
        today_provider=lambda: date(2026, 8, 25),
    )
    root.update()

    # Then
    try:
        assert "미처리 집계 실패" in app.overdue_banner.text.get()
        assert "미처리 경고 실패" in app.status.get()
    finally:
        root.destroy()


def test_dashboard_open_is_singleton_and_loads_date_range() -> None:
    # Given
    root, app, gateway = _app()

    # When
    app.background.open_dashboard()
    first_dialog = app.background.dashboard
    app.background.open_dashboard()
    root.update()

    # Then
    try:
        assert app.background.dashboard is first_dialog
        assert app.background.dashboard is not None
        assert "조회 완료" in app.background.dashboard.status_var.get()
        assert gateway.insert_calls == 0
        assert gateway.overwrite_calls == 0
    finally:
        root.destroy()


def test_dashboard_load_error_renders_inside_dialog() -> None:
    # Given
    class FailingDashboardService(ASIntakeService):
        def analytics_report(
            self,
            start_date: date,
            end_date: date,
            *,
            today: date,
        ):
            raise RuntimeError(f"{start_date.isoformat()} 실패")

    root = create_root()
    root.withdraw()
    app = ASIntakeApp(
        root,
        FailingDashboardService(DemoSheetGateway()),
        default_receiver="장진영",
        runner=InlineRunner(root),
        today_provider=lambda: date(2026, 8, 25),
    )
    root.update()

    # When
    app.background.open_dashboard()
    root.update()

    # Then
    try:
        assert app.background.dashboard is not None
        assert "대시보드 조회 실패" in app.background.dashboard.status_var.get()
    finally:
        root.destroy()


def test_callbacks_after_close_do_not_update_widgets() -> None:
    # Given
    root = create_root()
    root.withdraw()
    gateway = DemoSheetGateway()
    runner = InlineRunner(root)
    app = ASIntakeApp(
        root,
        ASIntakeService(gateway),
        default_receiver="장진영",
        runner=runner,
        today_provider=lambda: date(2026, 8, 25),
    )
    root.update()

    # When
    app.close()

    # Then
    assert runner.closed


def test_background_runner_marshals_completion_through_root_after() -> None:
    # Given
    class FakeRoot:
        def __init__(self) -> None:
            self.callbacks: list[Callable[[], None]] = []

        def after(self, delay: int, callback: Callable[[], None]) -> str:
            assert delay == 0
            self.callbacks.append(callback)
            scheduled.set()
            return "after#1"

    root = FakeRoot()
    seen: list[str] = []
    scheduled = Event()

    # When
    with ThreadPoolExecutor(max_workers=1) as executor:
        runner = BackgroundTkRunner(root, executor=executor)
        runner.submit(lambda: "done", seen.append, lambda _error: None)
        assert scheduled.wait(timeout=1)

        # Then
        assert seen == []
        root.callbacks.pop()()
        assert seen == ["done"]
        runner.close()


def test_background_runner_ignores_callbacks_after_close() -> None:
    # Given
    class FakeRoot:
        def __init__(self) -> None:
            self.callbacks: list[Callable[[], None]] = []

        def after(self, _delay: int, callback: Callable[[], None]) -> str:
            self.callbacks.append(callback)
            return "after#1"

    root = FakeRoot()
    seen: list[str] = []
    started = Event()
    release = Event()

    def work() -> str:
        started.set()
        release.wait(timeout=1)
        return "done"

    # When
    with ThreadPoolExecutor(max_workers=1) as executor:
        runner = BackgroundTkRunner(root, executor=executor)
        runner.submit(work, seen.append, lambda _error: None)
        assert started.wait(timeout=1)
        runner.close()
        release.set()

        # Then
        assert root.callbacks == []
        assert seen == []
