from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Final

BRAND_BLUE: Final = "#1D709B"
BRAND_BLUE_DARK: Final = "#11506F"
BRAND_GREEN: Final = "#009B58"
BACKGROUND: Final = "#F3F7F9"
SURFACE: Final = "#FFFFFF"
SURFACE_SUBTLE: Final = "#EAF2F5"
TEXT: Final = "#202428"
MUTED: Final = "#66737C"
BORDER: Final = "#D7E2E7"
ERROR: Final = "#B42318"
ISSUED_BACKGROUND: Final = "#E5F6ED"

NAVY: Final = BRAND_BLUE_DARK
BLUE: Final = BRAND_BLUE
PALE_BLUE: Final = SURFACE_SUBTLE
SUCCESS: Final = BRAND_GREEN


def asset_path(filename: str) -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(str(bundle_root)) / "service_validation" / "assets" / filename
    return Path(__file__).with_name("assets") / filename


def configure_styles(root: tk.Tk) -> None:
    root.configure(background=BACKGROUND)
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    style.configure("TFrame", background=BACKGROUND)
    style.configure("App.TFrame", background=BACKGROUND)
    style.configure("Card.TFrame", background=SURFACE, relief="solid", borderwidth=1)
    style.configure(
        "Header.TLabel",
        background=NAVY,
        foreground=SURFACE,
        font=("맑은 고딕", 20, "bold"),
    )
    style.configure(
        "Subtitle.TLabel",
        background=NAVY,
        foreground="#DDECF3",
        font=("맑은 고딕", 10),
    )
    style.configure(
        "Section.TLabel",
        background=SURFACE,
        foreground=TEXT,
        font=("맑은 고딕", 12, "bold"),
    )
    style.configure(
        "Muted.TLabel", background=SURFACE, foreground=MUTED, font=("맑은 고딕", 9)
    )
    style.configure(
        "Count.TLabel", background=SURFACE, foreground=BLUE, font=("맑은 고딕", 10, "bold")
    )
    style.configure(
        "TEntry", fieldbackground=SURFACE, foreground=TEXT, bordercolor=BORDER, padding=6
    )
    style.configure(
        "TLabelframe", background=SURFACE, bordercolor=BORDER, relief="solid"
    )
    style.configure(
        "TLabelframe.Label",
        background=SURFACE,
        foreground=TEXT,
        font=("맑은 고딕", 11, "bold"),
    )
    style.configure("TLabel", background=BACKGROUND, foreground=TEXT, font=("맑은 고딕", 10))
    style.configure(
        "TButton",
        background=SURFACE,
        foreground=TEXT,
        bordercolor=BORDER,
        padding=(12, 7),
        font=("맑은 고딕", 9),
    )
    style.map("TButton", background=[("active", SURFACE_SUBTLE), ("pressed", BORDER)])
    style.configure(
        "Tool.TButton",
        background=SURFACE,
        foreground=TEXT,
        bordercolor=BORDER,
        padding=(12, 7),
        font=("맑은 고딕", 9),
    )
    style.configure(
        "Primary.TButton",
        background=BLUE,
        foreground=SURFACE,
        bordercolor=BLUE,
        padding=(18, 9),
        font=("맑은 고딕", 10, "bold"),
    )
    style.map(
        "Primary.TButton",
        background=[("active", NAVY), ("pressed", NAVY), ("disabled", BORDER)],
        foreground=[("disabled", MUTED)],
    )
    for name in ("Success.TButton", "Header.TButton"):
        style.configure(
            name,
            background=SUCCESS,
            foreground=SURFACE,
            bordercolor=SUCCESS,
            padding=(18, 9),
            font=("맑은 고딕", 10, "bold"),
        )
        style.map(name, background=[("active", "#007A46"), ("pressed", "#007A46")])
    style.configure(
        "Treeview",
        font=("맑은 고딕", 9),
        rowheight=32,
        background=SURFACE,
        fieldbackground=SURFACE,
        foreground=TEXT,
        bordercolor=BORDER,
    )
    style.configure(
        "Treeview.Heading",
        background=SURFACE_SUBTLE,
        foreground=TEXT,
        font=("맑은 고딕", 9, "bold"),
        padding=(8, 9),
        relief="flat",
    )
    style.map("Treeview", background=[("selected", PALE_BLUE)], foreground=[("selected", TEXT)])


def set_window_icon(window: tk.Tk | tk.Toplevel) -> tk.PhotoImage:
    icon = tk.PhotoImage(file=asset_path("bistos_icon.png"))
    window.iconphoto(True, icon)
    return icon


def load_header_logo() -> tk.PhotoImage:
    return tk.PhotoImage(file=asset_path("bistos_logo.png"))
