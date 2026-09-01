from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from threading import Lock
from typing import Final, Protocol

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from pydantic import JsonValue, TypeAdapter

from .errors import GoogleRequestError

SHEETS_SCOPE: Final = "https://www.googleapis.com/auth/spreadsheets"


class JsonTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        payload: Mapping[str, JsonValue] | None = None,
    ) -> JsonValue: ...


OAuthLogin = Callable[[Path], Credentials]


class OAuthCredentialTypeError(TypeError):
    pass


def _installed_app_login(client_file: Path) -> Credentials:
    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_file),
        scopes=(SHEETS_SCOPE,),
    )
    credentials = flow.run_local_server(
        host="127.0.0.1",
        port=0,
        open_browser=True,
    )
    if not isinstance(credentials, Credentials):
        raise OAuthCredentialTypeError("데스크톱 OAuth 사용자 인증 정보를 받지 못했습니다.")
    return credentials


class InstalledAppCredentialProvider:
    def __init__(self, login: OAuthLogin = _installed_app_login) -> None:
        self._login = login

    def load(self, client_file: Path, token_file: Path) -> Credentials:
        if not client_file.is_file():
            raise FileNotFoundError(
                f"Google OAuth 클라이언트 JSON을 찾을 수 없습니다: {client_file}"
            )

        credentials = self._load_cached(token_file)
        if credentials is not None and credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
            except RefreshError:
                credentials = None
            else:
                self._save(token_file, credentials)
        if credentials is not None and credentials.valid:
            return credentials

        credentials = self._login(client_file)
        self._save(token_file, credentials)
        return credentials

    @staticmethod
    def _load_cached(token_file: Path) -> Credentials | None:
        if not token_file.is_file():
            return None
        try:
            return Credentials.from_authorized_user_file(
                str(token_file),
                scopes=(SHEETS_SCOPE,),
            )
        except (OSError, ValueError):
            return None

    @staticmethod
    def _save(token_file: Path, credentials: Credentials) -> None:
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(credentials.to_json(), encoding="utf-8")


class GoogleAuthTransport:
    def __init__(self, client_file: Path, token_file: Path) -> None:
        self._client_file = client_file
        self._token_file = token_file
        self._session: AuthorizedSession | None = None
        self._session_lock = Lock()

    def request(
        self,
        method: str,
        url: str,
        payload: Mapping[str, JsonValue] | None = None,
    ) -> JsonValue:
        response = self._authorized_session().request(method, url, json=payload, timeout=30)
        if response.status_code >= 400:
            raise GoogleRequestError(
                f"Google Sheets API 오류 {response.status_code}: {response.text[:400]}"
            )
        if not response.text:
            return {}
        return TypeAdapter(JsonValue).validate_json(response.text)

    def _authorized_session(self) -> AuthorizedSession:
        session = self._session
        if session is not None:
            return session
        with self._session_lock:
            session = self._session
            if session is None:
                credentials = InstalledAppCredentialProvider().load(
                    self._client_file,
                    self._token_file,
                )
                session = AuthorizedSession(credentials)
                self._session = session
            return session
