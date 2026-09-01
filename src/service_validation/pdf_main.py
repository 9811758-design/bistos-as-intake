from __future__ import annotations

import tkinter as tk

from .pdf_app import PdfMergeApp


def main() -> None:
    root = tk.Tk()
    PdfMergeApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
