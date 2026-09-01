from __future__ import annotations

import tkinter as tk
from typing import cast

import pytest


@pytest.mark.parametrize(
    "detail",
    ("couldn't read file tk.tcl", 'invalid command name "tcl_findLibrary"'),
)
def test_create_root_retries_transient_tcl_resource_read(
    monkeypatch: pytest.MonkeyPatch,
    detail: str,
) -> None:
    from receivables_reconciliation import main

    expected = cast(tk.Tk, object())
    attempts = iter((tk.TclError(detail), expected))

    def create() -> tk.Tk:
        result = next(attempts)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(main.tk, "Tk", create)
    monkeypatch.setattr(main.time, "sleep", lambda _delay: None)

    assert main.create_root() is expected


def test_create_root_does_not_retry_unrelated_tcl_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from receivables_reconciliation import main

    calls = 0

    def create() -> tk.Tk:
        nonlocal calls
        calls += 1
        raise tk.TclError("no display name")

    monkeypatch.setattr(main.tk, "Tk", create)

    with pytest.raises(tk.TclError, match="no display name"):
        main.create_root()

    assert calls == 1
