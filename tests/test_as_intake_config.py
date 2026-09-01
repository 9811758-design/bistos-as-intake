from __future__ import annotations

from pathlib import Path

from as_intake.config import AppConfig, load_config, save_config


def test_config_round_trip_keeps_external_oauth_client_path(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    expected = AppConfig(
        spreadsheet_id="sheet-id",
        oauth_client_file=str(tmp_path / "oauth-client.json"),
        default_receiver="장진영",
    )

    save_config(path, expected)

    assert load_config(path) == expected
