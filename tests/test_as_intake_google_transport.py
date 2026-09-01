from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from google.oauth2.credentials import Credentials

from as_intake.google_transport import SHEETS_SCOPE, InstalledAppCredentialProvider


def _credentials() -> Credentials:
    return Credentials(
        token="access-token",
        refresh_token="refresh-token",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="client-id",
        client_secret="client-secret",
        scopes=(SHEETS_SCOPE,),
        expiry=datetime.now(UTC) + timedelta(hours=1),
    )


def test_oauth_provider_rejects_missing_client_file(tmp_path: Path) -> None:
    provider = InstalledAppCredentialProvider()

    with pytest.raises(FileNotFoundError, match="OAuth 클라이언트"):
        provider.load(tmp_path / "missing.json", tmp_path / "token.json")


def test_oauth_provider_reuses_valid_cached_credentials(tmp_path: Path) -> None:
    client_file = tmp_path / "oauth-client.json"
    token_file = tmp_path / "token.json"
    client_file.write_text("{}", encoding="utf-8")
    token_file.write_text(_credentials().to_json(), encoding="utf-8")

    loaded = InstalledAppCredentialProvider().load(client_file, token_file)

    assert loaded.token == "access-token"
    assert loaded.refresh_token == "refresh-token"


def test_oauth_provider_opens_browser_and_saves_first_login_token(tmp_path: Path) -> None:
    client_file = tmp_path / "oauth-client.json"
    token_file = tmp_path / "token.json"
    client_file.write_text("{}", encoding="utf-8")
    requested_clients: list[Path] = []

    def login(selected_client: Path) -> Credentials:
        requested_clients.append(selected_client)
        return _credentials()

    provider = InstalledAppCredentialProvider(login)
    loaded = provider.load(client_file, token_file)

    assert requested_clients == [client_file]
    assert loaded.token == "access-token"
    assert Credentials.from_authorized_user_file(token_file).refresh_token == "refresh-token"
