from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from service_validation.brand import (
    BACKGROUND,
    BORDER,
    BRAND_BLUE,
    BRAND_BLUE_DARK,
    BRAND_GREEN,
    ERROR,
    MUTED,
    SURFACE,
    SURFACE_SUBTLE,
    TEXT,
    configure_styles,
    load_header_logo,
    set_window_icon,
)

WARNING = "#B54708"


def configure_as_styles(root: tk.Tk) -> None:
    configure_styles(root)
    style = ttk.Style(root)
    style.configure(
        "Mode.TLabel",
        background=SURFACE_SUBTLE,
        foreground=BRAND_BLUE_DARK,
        padding=(12, 8),
        font=("맑은 고딕", 10, "bold"),
    )
    style.configure("Form.TFrame", background=SURFACE)
    style.configure(
        "Overwrite.TLabel",
        background="#FFF4E5",
        foreground=WARNING,
        padding=(12, 8),
        font=("맑은 고딕", 10, "bold"),
    )
    style.configure(
        "Status.TLabel",
        background=SURFACE,
        foreground=MUTED,
        padding=(12, 7),
        font=("맑은 고딕", 9),
    )
    style.configure(
        "SuccessStatus.TLabel",
        background=SURFACE,
        foreground=BRAND_GREEN,
        padding=(12, 7),
        font=("맑은 고딕", 9, "bold"),
    )
    style.configure(
        "ErrorStatus.TLabel",
        background=SURFACE,
        foreground=ERROR,
        padding=(12, 7),
        font=("맑은 고딕", 9, "bold"),
    )
    style.configure(
        "Warning.TButton",
        background=WARNING,
        foreground=SURFACE,
        bordercolor=WARNING,
        padding=(18, 9),
        font=("맑은 고딕", 10, "bold"),
    )
    style.map(
        "Warning.TButton",
        background=[("active", "#8A3505"), ("pressed", "#8A3505")],
    )
    style.configure("TNotebook", background=BACKGROUND, borderwidth=0)
    style.configure("TNotebook.Tab", padding=(16, 9), font=("맑은 고딕", 10, "bold"))
    style.map(
        "TNotebook.Tab",
        background=[("selected", SURFACE), ("!selected", SURFACE_SUBTLE)],
        foreground=[("selected", BRAND_BLUE_DARK), ("!selected", MUTED)],
    )


__all__ = [
    "BACKGROUND",
    "BORDER",
    "BRAND_BLUE",
    "BRAND_BLUE_DARK",
    "BRAND_GREEN",
    "MUTED",
    "SURFACE",
    "SURFACE_SUBTLE",
    "TEXT",
    "WARNING",
    "configure_as_styles",
    "load_header_logo",
    "set_window_icon",
]
