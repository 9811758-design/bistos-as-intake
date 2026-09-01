from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Protocol, assert_never

from pythoncom import CoInitialize, CoUninitialize
from pywintypes import com_error

from receivables_reconciliation.mail_parser import (
    DEFAULT_ALERT_PATTERNS,
    AlertPatternSet,
    NotDeposit,
    parse_message,
)
from receivables_reconciliation.models import DepositNotice, UnparsedDepositNotice


class OutlookComError(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class OutlookActivationDeniedError(Exception):
    detail: str

    def __str__(self) -> str:
        return f"Outlook 실행 권한이 맞지 않아 접근할 수 없습니다: {self.detail}"


@dataclass(frozen=True, slots=True)
class MissingOutlookProfileError(Exception):
    detail: str

    def __str__(self) -> str:
        return f"Outlook 프로필을 찾을 수 없습니다: {self.detail}"


@dataclass(frozen=True, slots=True)
class OutlookComUnavailableError(Exception):
    detail: str

    def __str__(self) -> str:
        return f"클래식 Outlook COM을 사용할 수 없습니다: {self.detail}"


@dataclass(frozen=True, slots=True)
class OutlookProbeResult:
    success: bool
    count: int
    hashed_message_ids: tuple[str, ...]
    detail: str


class OutlookMessage(Protocol):
    @property
    def EntryID(self) -> str: ...

    @property
    def Subject(self) -> str: ...

    @property
    def Body(self) -> str: ...

    @property
    def ReceivedTime(self) -> datetime: ...


class OutlookItems(Protocol):
    def Sort(self, field_name: str, descending: bool) -> None: ...

    def __iter__(self) -> Iterator[OutlookMessage]: ...


class OutlookFolders(Protocol):
    def __iter__(self) -> Iterator[OutlookFolder]: ...


class OutlookFolder(Protocol):
    @property
    def Name(self) -> str: ...

    @property
    def Items(self) -> OutlookItems: ...

    @property
    def Folders(self) -> OutlookFolders: ...


class OutlookStore(Protocol):
    def GetDefaultFolder(self, folder_id: int) -> OutlookFolder: ...


class OutlookStores(Protocol):
    def __iter__(self) -> Iterator[OutlookStore]: ...


class OutlookNamespace(Protocol):
    @property
    def Stores(self) -> OutlookStores: ...

    def GetDefaultFolder(self, folder_id: int) -> OutlookFolder: ...


class OutlookApplication(Protocol):
    def GetNamespace(self, namespace_name: str) -> OutlookNamespace: ...


MAPI_INBOX_FOLDER_ID = 6
_SKIPPED_FOLDER_NAMES = frozenset(
    (
        "archive",
        "junk email",
        "junk",
        "deleted items",
        "보관",
        "정크 메일",
        "지운 편지함",
        "삭제된 항목",
    )
)


class ClassicOutlookReader:
    def __init__(
        self,
        dispatch: Callable[[], OutlookApplication] | None = None,
        patterns: AlertPatternSet | None = None,
    ) -> None:
        self._dispatch = _dispatch_outlook if dispatch is None else dispatch
        self._patterns = DEFAULT_ALERT_PATTERNS if patterns is None else patterns

    def read(
        self,
        start_date: date,
        end_date: date,
    ) -> tuple[DepositNotice | UnparsedDepositNotice, ...]:
        CoInitialize()
        try:
            try:
                outlook = self._dispatch()
                namespace = outlook.GetNamespace("MAPI")
                inbox = _active_inbox(namespace)
                start_at = datetime.combine(start_date, time.min)
                end_before = datetime.combine(end_date, time.min) + _one_day()
                return tuple(
                    _scan_folder_tree(
                        inbox,
                        start_at,
                        end_before,
                        self._patterns,
                    )
                )
            except OutlookComError as exc:
                raise OutlookComUnavailableError(str(exc)) from exc
            except com_error as exc:
                raise _typed_outlook_error(exc) from exc
        finally:
            CoUninitialize()


def live_read_only_probe(
    reader: ClassicOutlookReader,
    start_date: date,
    end_date: date,
) -> OutlookProbeResult:
    try:
        notices = reader.read(start_date, end_date)
    except (
        OutlookActivationDeniedError,
        MissingOutlookProfileError,
        OutlookComUnavailableError,
    ) as exc:
        return OutlookProbeResult(False, 0, (), str(exc))
    return OutlookProbeResult(
        success=True,
        count=len(notices),
        hashed_message_ids=tuple(
            hashlib.sha256(notice.message_id.encode("utf-8")).hexdigest()[:16]
            for notice in notices
        ),
        detail="read-only probe completed",
    )


def _scan_folder_tree(
    folder: OutlookFolder,
    start_at: datetime,
    end_before: datetime,
    patterns: AlertPatternSet,
) -> Iterator[DepositNotice | UnparsedDepositNotice]:
    items = folder.Items
    items.Sort("[ReceivedTime]", True)
    for message in items:
        received_at = _as_local_wall_time(message.ReceivedTime)
        if received_at < start_at:
            break
        if received_at >= end_before:
            continue
        parsed = parse_message(message, patterns)
        match parsed:
            case DepositNotice() | UnparsedDepositNotice():
                yield replace(parsed, received_at=received_at)
            case tuple() as notices:
                for notice in notices:
                    yield replace(notice, received_at=received_at)
            case NotDeposit():
                continue
            case unreachable:
                assert_never(unreachable)
    for child in folder.Folders:
        if _is_skipped_folder(child):
            continue
        yield from _scan_folder_tree(child, start_at, end_before, patterns)


def _active_inbox(namespace: OutlookNamespace) -> OutlookFolder:
    candidates: list[tuple[datetime, OutlookFolder]] = []
    for store in namespace.Stores:
        inbox = store.GetDefaultFolder(MAPI_INBOX_FOLDER_ID)
        items = inbox.Items
        items.Sort("[ReceivedTime]", True)
        latest_message = next(iter(items), None)
        latest_at = (
            _as_local_wall_time(latest_message.ReceivedTime)
            if latest_message is not None
            else datetime.min
        )
        candidates.append((latest_at, inbox))
    if candidates:
        return max(candidates, key=lambda candidate: candidate[0])[1]
    inbox = namespace.GetDefaultFolder(MAPI_INBOX_FOLDER_ID)
    inbox.Items.Sort("[ReceivedTime]", True)
    return inbox


def _is_skipped_folder(folder: OutlookFolder) -> bool:
    return folder.Name.strip().casefold() in _SKIPPED_FOLDER_NAMES


def _dispatch_outlook() -> OutlookApplication:
    if TYPE_CHECKING:
        raise OutlookComError("pywin32 또는 클래식 Outlook COM 등록을 확인하세요.")
    try:
        from win32com.client import Dispatch
    except ModuleNotFoundError as exc:
        raise OutlookComError("pywin32 또는 클래식 Outlook COM 등록을 확인하세요.") from exc
    return Dispatch("Outlook.Application")


def _typed_outlook_error(exc: BaseException) -> Exception:
    detail = str(exc)
    detail_lower = detail.casefold()
    hresult = _hresult(exc)
    if hresult == -2147024156 or "800702e4" in detail_lower:
        return OutlookActivationDeniedError(detail)
    if hresult in {-2147221231, -2147221219} or "profile" in detail_lower:
        return MissingOutlookProfileError(detail)
    return OutlookComUnavailableError(detail)


def _hresult(exc: BaseException) -> int | None:
    first_arg = exc.args[0] if exc.args else None
    if isinstance(first_arg, int):
        return first_arg
    hresult = getattr(exc, "hresult", None)
    if isinstance(hresult, int):
        return hresult
    return None


def _one_day() -> timedelta:
    return timedelta(days=1)


def _as_local_wall_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value
    return value.astimezone().replace(tzinfo=None)
