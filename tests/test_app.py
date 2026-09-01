import json
import tkinter as tk
from pathlib import Path

import pytest

from service_validation.app import GeneratorApp


def test_saved_source_reload_is_scheduled_after_window_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.xlsx"
    source.touch()
    (tmp_path / "settings.json").write_text(
        json.dumps({"source": str(source), "template": "", "output": ""}),
        encoding="utf-8",
    )
    reload_calls: list[bool] = []
    monkeypatch.setattr(GeneratorApp, "_config_dir", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(GeneratorApp, "_reload_rows", lambda _self: reload_calls.append(True))
    root = tk.Tk()
    root.withdraw()
    try:
        GeneratorApp(root)

        assert reload_calls == []
        assert root.tk.call("after", "info")
    finally:
        root.destroy()
