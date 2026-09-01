from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict

DEFAULT_SPREADSHEET_ID: Final = "1dvPujmHsVENRia_E17TIZjASHBtAnk0uqVAkhyka2Gc"


class AppConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    spreadsheet_id: str = DEFAULT_SPREADSHEET_ID
    oauth_client_file: str = ""
    default_receiver: str = ""


def default_config_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "Bistos" / "ASIntake" / "config.json"


def default_oauth_token_path() -> Path:
    return default_config_path().with_name("google-oauth-token.json")


def load_config(path: Path | None = None) -> AppConfig:
    target = path or default_config_path()
    if not target.is_file():
        return AppConfig()
    return AppConfig.model_validate_json(target.read_text(encoding="utf-8"))


def save_config(path: Path, config: AppConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(config.model_dump_json(indent=2), encoding="utf-8")
