from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from datetime import date
from tkinter import ttk

from service_validation.brand import asset_path

from .background import ASIntakeBackgroundCoordinator, TkBackgroundRunner
from .columns import SheetField
from .recommendation import CaseRecommendation, RecommendationQuery
from .recommendation_dialog import RecommendationDialog
from .service import ASIntakeService, SearchQuery
from .ui_form import RecordForm
from .ui_search import SearchPane
from .ui_tokens import BRAND_BLUE_DARK, BRAND_GREEN, configure_as_styles


class ASIntakeApp:
    def __init__(
        self,
        root: tk.Tk,
        service: ASIntakeService,
        default_receiver: str = "",
        settings_command: Callable[[], None] | None = None,
        runner: TkBackgroundRunner | None = None,
        today_provider: Callable[[], date] = date.today,
    ) -> None:
        self.root = root
        self.service = service
        self.status = tk.StringVar(value="준비됨")
        self._settings_command = settings_command
        configure_as_styles(root)
        root.title("Bistos A/S 접수 관리")
        root.geometry("1360x820")
        root.minsize(1080, 680)
        try:
            self._icon = tk.PhotoImage(master=root, file=asset_path("bistos_icon.png"))
            root.iconphoto(True, self._icon)
        except tk.TclError:
            self._icon = None
        self._build_header()
        self._build_body(default_receiver, runner, today_provider)
        self._build_status()
        root.bind("<Control-n>", lambda _event: self._new())
        root.bind("<Control-s>", lambda _event: self._save_current())
        root.bind("<Control-r>", lambda _event: self._recommend())
        root.bind("<Destroy>", self._on_destroy, add="+")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(0, self.background.refresh_overdue)

    def replace_service(self, service: ASIntakeService, default_receiver: str) -> None:
        self.service = service
        self.background.replace_service(service)
        self.form.default_receiver = default_receiver
        self._new()
        self._set_status("Google Sheets 연결 설정을 적용했습니다.", "SuccessStatus.TLabel")

    def _build_header(self) -> None:
        self._header = tk.Frame(self.root, background=BRAND_BLUE_DARK, height=104)
        self._header.pack(fill="x")
        self._header.pack_propagate(False)
        title = tk.Frame(self._header, background=BRAND_BLUE_DARK)
        title.pack(side="left", fill="y", padx=20, pady=(12, 16))
        ttk.Label(title, text="Bistos A/S 접수 관리", style="Header.TLabel").pack(anchor="w")
        self._header_subtitle = ttk.Label(
            title,
            text="신규 접수부터 검색·수정까지 Google 시트와 같은 데이터로 관리합니다.",
            style="Subtitle.TLabel",
            wraplength=520,
        )
        self._header_subtitle.pack(anchor="w", pady=(4, 0))
        self._logo_image = tk.PhotoImage(master=self.root, file=asset_path("bistos_logo.png"))
        self._header_logo = tk.Label(
            self._header,
            image=self._logo_image,
            background=BRAND_BLUE_DARK,
            borderwidth=0,
        )
        self._header_logo.pack(side="right", padx=(0, 20), pady=16)
        actions = tk.Frame(self._header, background=BRAND_BLUE_DARK)
        actions.pack(side="right", padx=(0, 12))
        ttk.Button(actions, text="새 접수  Ctrl+N", command=self._new).pack(side="left", padx=4)
        if self._settings_command is not None:
            settings_command = self._settings_command
            button = ttk.Button(actions, text="Google 설정", command=settings_command)
            button.pack(side="left", padx=4)
        accent = tk.Frame(self.root, background=BRAND_GREEN, height=4)
        accent.pack(fill="x")

    def _build_body(
        self,
        default_receiver: str,
        runner: TkBackgroundRunner | None,
        today_provider: Callable[[], date],
    ) -> None:
        body = ttk.Frame(self.root, style="App.TFrame", padding=16)
        body.pack(fill="both", expand=True)
        self.background = ASIntakeBackgroundCoordinator(
            body,
            self.root,
            self.service,
            runner,
            today_provider,
            self._set_status,
        )
        self.overdue_banner = self.background.banner
        paned = ttk.Panedwindow(body, orient="horizontal")
        paned.pack(fill="both", expand=True)
        self.search = SearchPane(paned, self._search, self._select_result)
        editor = ttk.Frame(paned, style="App.TFrame")
        buttons = ttk.Frame(editor, style="App.TFrame")
        buttons.pack(fill="x", pady=(0, 12))
        load_button = ttk.Button(buttons, text="검색 결과 불러오기", command=self._select_result)
        load_button.pack(side="left")
        self.recommend_button = ttk.Button(
            buttons,
            text="해결 추천  Ctrl+R",
            command=self._recommend,
        )
        self.recommend_button.pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="신규 저장", style="Primary.TButton", command=self._register).pack(
            side="right",
            padx=(8, 0),
        )
        ttk.Button(
            buttons,
            text="기존 행 덮어쓰기",
            style="Warning.TButton",
            command=self._overwrite,
        ).pack(side="right")
        self.form = RecordForm(editor, default_receiver)
        self.form.pack(fill="both", expand=True)
        paned.add(self.search, weight=5)
        paned.add(editor, weight=7)

    def _build_status(self) -> None:
        bar = ttk.Frame(self.root, style="Card.TFrame")
        bar.pack(fill="x")
        self._status_label = ttk.Label(bar, textvariable=self.status, style="Status.TLabel")
        self._status_label.pack(fill="x")

    def _set_status(self, message: str, style: str = "Status.TLabel") -> None:
        self.status.set(message)
        self._status_label.configure(style=style)

    def _new(self) -> None:
        self.form.clear()
        self._set_status("새 접수 입력을 시작합니다.")

    def _save_current(self) -> None:
        if self.form.service_number.get().strip():
            self._overwrite()
        else:
            self._register()

    def _register(self) -> None:
        try:
            saved = self.service.register(self.form.draft())
            self.form.load(saved)
            number = saved.value(SheetField.SERVICE_NUMBER)
            self._set_status(
                f"저장 완료 · {number} · Google 시트 최상단에 추가했습니다.",
                "SuccessStatus.TLabel",
            )
            self.background.refresh_overdue()
        except (ValueError, LookupError, OSError, RuntimeError) as error:
            self._set_status(f"저장 실패 · {error}", "ErrorStatus.TLabel")

    def _search(self) -> None:
        try:
            year = int(self.search.year.get())
            rows = self.service.search(
                SearchQuery(year, self.search.query.get(), self.search.close_status.get())
            )
            self.search.render(rows)
            self._set_status(f"검색 완료 · {len(rows)}건")
        except (ValueError, LookupError, OSError, RuntimeError) as error:
            self._set_status(f"검색 실패 · {error}", "ErrorStatus.TLabel")

    def _select_result(self) -> None:
        row = self.search.selected_row()
        if row is None:
            self._set_status("검색 결과에서 수정할 행을 먼저 선택하세요.", "ErrorStatus.TLabel")
            return
        self.form.load(row)
        number = row.value(SheetField.SERVICE_NUMBER)
        self._set_status(f"{number} 행을 불러왔습니다. 저장하면 기존 행을 덮어씁니다.")

    def _recommend(self) -> None:
        symptom = self.form.fields[SheetField.SYMPTOM].get().strip()
        cause = self.form.fields[SheetField.FAILURE_CAUSE].get().strip()
        if not symptom and not cause:
            self._set_status(
                "증상 또는 불량원인을 먼저 입력하세요.",
                "ErrorStatus.TLabel",
            )
            return
        try:
            year = int(self.form.receipt_date.get().strip()[:4])
            report = self.service.recommend(
                RecommendationQuery(
                    year,
                    symptom,
                    cause,
                    self.form.fields[SheetField.MODEL].get(),
                )
            )
            if not report.recommendations:
                self._set_status(
                    f"추천 결과 없음 · 과거 {report.analyzed_rows:,}건에서 "
                    "충분히 유사한 사례가 없습니다.",
                    "ErrorStatus.TLabel",
                )
                return
            RecommendationDialog(self.root, report, self._apply_recommendation)
            self._set_status(
                f"추천 완료 · 과거 {report.analyzed_rows:,}건에서 상위 "
                f"{len(report.recommendations)}건을 찾았습니다."
            )
        except (ValueError, LookupError, OSError, RuntimeError) as error:
            self._set_status(f"추천 실패 · {error}", "ErrorStatus.TLabel")

    def _apply_recommendation(
        self,
        recommendation: CaseRecommendation,
        include_cause: bool,
    ) -> None:
        source = recommendation.source
        learning_note = ""
        try:
            if self.service.learn_from_recommendation(recommendation):
                learning_note = " · 선택 이력을 다음 추천에 학습했습니다."
        except (OSError, ValueError) as error:
            learning_note = f" · 적용 완료, 학습 저장 실패: {error}"
        if include_cause:
            self.form.set_value(SheetField.FAILURE_CAUSE, source.value(SheetField.FAILURE_CAUSE))
        self.form.set_value(SheetField.ACTION, source.value(SheetField.ACTION))
        number = source.value(SheetField.SERVICE_NUMBER)
        applied = "원인·대응조치" if include_cause else "대응조치"
        self._set_status(
            f"추천 적용 · {number} 사례의 {applied}를 입력했습니다.{learning_note}",
            "SuccessStatus.TLabel",
        )

    def _overwrite(self) -> None:
        original_number = self.form.service_number.get().strip()
        if not original_number:
            self._set_status("먼저 검색 결과를 불러오세요.", "ErrorStatus.TLabel")
            return
        try:
            saved = self.service.update(original_number, self.form.sheet_row())
            self.form.load(saved)
            self._search()
            self._set_status(
                f"덮어쓰기 완료 · {original_number} · 마지막 저장 내용이 반영됐습니다.",
                "SuccessStatus.TLabel",
            )
            self.background.refresh_overdue()
        except (ValueError, LookupError, OSError, RuntimeError) as error:
            self._set_status(f"덮어쓰기 실패 · {error}", "ErrorStatus.TLabel")

    def _on_destroy(self, event: tk.Event[tk.Misc]) -> None:
        if event.widget is self.root:
            self.background.close()

    def close(self) -> None:
        self.background.close()
        self.root.destroy()
