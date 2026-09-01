from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .app import GeneratorApp
from .brand import NAVY, configure_styles, load_header_logo, set_window_icon
from .quick_entry import QuickEntryWindow


class EnhancedGeneratorApp(GeneratorApp):
    def _configure_style(self) -> None:
        configure_styles(self.root)

    def __init__(self, root: tk.Tk) -> None:
        super().__init__(root)
        root.title("Bistos 서비스 검증결과서 생성기")
        header = root.winfo_children()[0]
        self.header_banner = header.winfo_children()[0]
        self.header_banner.configure({"background": NAVY})
        self.icon_image = set_window_icon(root)
        self.logo_image = load_header_logo()
        self.logo_label = tk.Label(
            self.header_banner,
            image=self.logo_image,
            background=NAVY,
            borderwidth=0,
        )
        self.logo_label.place(relx=1, rely=0.5, x=-4, anchor="e")
        self.quick_entry: QuickEntryWindow | None = None
        self.quick_button = ttk.Button(
            root,
            text="1건 빠른 발행",
            command=self._open_quick_entry,
            style="Header.TButton",
        )
        self.quick_button.place(relx=1, x=-278, y=26, anchor="ne")

    def _open_quick_entry(self) -> None:
        if self.quick_entry is not None and self.quick_entry.exists:
            self.quick_entry.focus()
            return
        self.quick_entry = QuickEntryWindow(
            self.root,
            self.template,
            self.output,
            self._config_dir(),
            self._refresh_after_quick_issue,
        )

    def _refresh_after_quick_issue(self) -> None:
        self._refresh_issued()
        self._render_page()
        self._save_settings()
