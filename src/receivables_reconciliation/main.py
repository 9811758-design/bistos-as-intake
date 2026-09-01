from __future__ import annotations

import time
import tkinter as tk
from typing import Final

from receivables_reconciliation.outlook_reader import ClassicOutlookReader
from receivables_reconciliation.tracker_app import ReceivablesTrackerApp
from receivables_reconciliation.tracker_service import ReceivablesTrackerService
from receivables_reconciliation.tracker_store import SqliteTaskStore, default_store_path

TRANSIENT_TCL_ERRORS: Final = (
    "couldn't read file",
    "can't find a usable tk.tcl",
    'invalid command name "tcl_findlibrary"',
)


def create_root(*, attempts: int = 3, retry_delay: float = 0.05) -> tk.Tk:
    for attempt in range(attempts):
        try:
            return tk.Tk()
        except tk.TclError as exc:
            detail = str(exc).casefold()
            transient_resource_error = any(marker in detail for marker in TRANSIENT_TCL_ERRORS)
            if not transient_resource_error or attempt == attempts - 1:
                raise
            time.sleep(retry_delay)
    raise AssertionError("unreachable")


def main() -> None:
    root = create_root()
    service = ReceivablesTrackerService(
        ClassicOutlookReader(),
        SqliteTaskStore(default_store_path()),
    )
    ReceivablesTrackerApp(root, service)
    root.mainloop()


if __name__ == "__main__":
    main()
