from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pytest
from pywintypes import com_error

import receivables_reconciliation.outlook_reader as outlook_reader_module
from receivables_reconciliation.mail_parser import AlertPatternSet
from receivables_reconciliation.models import DepositNotice
from receivables_reconciliation.outlook_reader import (
    ClassicOutlookReader,
    MissingOutlookProfileError,
    OutlookActivationDeniedError,
    OutlookComError,
    OutlookComUnavailableError,
    OutlookMessage,
    live_read_only_probe,
)


@dataclass(frozen=True, slots=True)
class MessageFixture:
    EntryID: str
    Subject: str
    Body: str
    ReceivedTime: datetime


class ItemCollectionFixture:
    def __init__(self, messages: tuple[OutlookMessage, ...]) -> None:
        self.messages = messages
        self.sort_calls: list[tuple[str, bool]] = []

    def Sort(self, field_name: str, descending: bool) -> None:
        self.sort_calls.append((field_name, descending))
        self.messages = tuple(
            sorted(self.messages, key=lambda message: message.ReceivedTime, reverse=descending)
        )

    def __iter__(self) -> Iterator[OutlookMessage]:
        return iter(self.messages)


@dataclass(frozen=True, slots=True)
class FolderCollectionFixture:
    folders: tuple[FolderFixture, ...]

    def __iter__(self) -> Iterator[FolderFixture]:
        return iter(self.folders)


@dataclass(frozen=True, slots=True)
class FolderFixture:
    Name: str
    Items: ItemCollectionFixture
    Folders: FolderCollectionFixture


@dataclass(frozen=True, slots=True)
class NamespaceFixture:
    inbox: FolderFixture

    @property
    def Stores(self) -> tuple[NamespaceFixture, ...]: return (self,)

    def GetDefaultFolder(self, folder_id: int) -> FolderFixture:
        return self.inbox


@dataclass(frozen=True, slots=True)
class OutlookFixture:
    namespace: NamespaceFixture

    def GetNamespace(self, namespace_name: str) -> NamespaceFixture:
        assert namespace_name == "MAPI"
        return self.namespace


def _message(entry_id: str, received_at: datetime, depositor: str = "김민수") -> MessageFixture:
    return MessageFixture(
        EntryID=entry_id,
        Subject="입금 알림",
        Body=f"입금일자: {received_at:%Y-%m-%d}\n입금자: {depositor}\n금액: 10,000원",
        ReceivedTime=received_at,
    )


def test_reader_scans_default_inbox_tree_descending_and_stops_after_start_boundary() -> None:
    # Given
    old_message = _message("old", datetime(2026, 8, 13, 23, 59))
    in_range = _message("in-range", datetime(2026, 8, 14, 15, 0))
    end_excluded = _message("end-excluded", datetime(2026, 8, 15, 0, 0))
    child_message = _message("child", datetime(2026, 8, 14, 9, 0), "이영희")
    child_items = ItemCollectionFixture((child_message,))
    child = FolderFixture("입금", child_items, FolderCollectionFixture(()))
    inbox_items = ItemCollectionFixture((old_message, in_range, end_excluded))
    inbox = FolderFixture("Inbox", inbox_items, FolderCollectionFixture((child,)))
    reader = ClassicOutlookReader(lambda: OutlookFixture(NamespaceFixture(inbox)))

    # When
    result = reader.read(date(2026, 8, 14), date(2026, 8, 14))

    # Then
    assert result == (
        DepositNotice(
            message_id="in-range",
            deposit_date=date(2026, 8, 14),
            depositor_name="김민수",
            amount=10000,
            subject="입금 알림",
            received_at=datetime(2026, 8, 14, 15, 0),
        ),
        DepositNotice(
            message_id="child",
            deposit_date=date(2026, 8, 14),
            depositor_name="이영희",
            amount=10000,
            subject="입금 알림",
            received_at=datetime(2026, 8, 14, 9, 0),
        ),
    )
    assert inbox_items.sort_calls == [
        ("[ReceivedTime]", True),
        ("[ReceivedTime]", True),
    ]
    assert child_items.sort_calls == [("[ReceivedTime]", True)]


def test_reader_converts_timezone_aware_received_time_to_local_wall_time() -> None:
    # Given
    received_at = datetime(2026, 8, 14, 15, 0, tzinfo=UTC)
    local_received_at = received_at.astimezone().replace(tzinfo=None)
    message = _message("aware-time", received_at)
    items = ItemCollectionFixture((message,))
    inbox = FolderFixture("Inbox", items, FolderCollectionFixture(()))
    reader = ClassicOutlookReader(lambda: OutlookFixture(NamespaceFixture(inbox)))

    # When
    result = reader.read(local_received_at.date(), local_received_at.date())

    # Then
    assert len(result) == 1
    assert result[0].received_at == local_received_at
    assert result[0].received_at.tzinfo is None


def test_reader_flattens_multiple_rows_from_outlook_deposit_table() -> None:
    # Given
    message = MessageFixture(
        EntryID="table-mail",
        Subject="8/21 국내입금",
        Body=(
            "일자\n거래처\n금액\n금융기관\n"
            "2026-08-21\n장경진(세종씨엠에스)\n44,000\n기업018(원화)\n"
            "2026-08-21\n강동미사노블요양병원\n165,000\n국민648(원화)"
        ),
        ReceivedTime=datetime(2026, 8, 21, 10, 0),
    )
    inbox = FolderFixture(
        "Inbox",
        ItemCollectionFixture((message,)),
        FolderCollectionFixture(()),
    )
    reader = ClassicOutlookReader(lambda: OutlookFixture(NamespaceFixture(inbox)))

    # When
    result = reader.read(date(2026, 8, 21), date(2026, 8, 21))

    # Then
    assert len(result) == 2
    first, second = result
    assert isinstance(first, DepositNotice)
    assert isinstance(second, DepositNotice)
    actual = [
        (notice.message_id, notice.depositor_name, notice.bank_name)
        for notice in (first, second)
    ]
    assert actual == [
        ("table-mail", "장경진(세종씨엠에스)", "기업018(원화)"),
        ("table-mail#2", "강동미사노블요양병원", "국민648(원화)"),
    ]


def test_reader_initializes_com_in_calling_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    calls: list[str] = []
    monkeypatch.setattr(
        outlook_reader_module,
        "CoInitialize",
        lambda: calls.append("initialize"),
        raising=False,
    )
    monkeypatch.setattr(
        outlook_reader_module,
        "CoUninitialize",
        lambda: calls.append("uninitialize"),
        raising=False,
    )
    inbox = FolderFixture("Inbox", ItemCollectionFixture(()), FolderCollectionFixture(()))
    reader = ClassicOutlookReader(lambda: OutlookFixture(NamespaceFixture(inbox)))

    # When
    reader.read(date(2026, 8, 14), date(2026, 8, 14))

    # Then
    assert calls == ["initialize", "uninitialize"]


def test_reader_never_calls_outlook_mutation_methods() -> None:
    # Given
    class MutatingMessage:
        EntryID = "mutating"
        Subject = "입금 알림"
        Body = "입금일자: 2026-08-14\n입금자: 김민수"
        ReceivedTime = datetime(2026, 8, 14, 12, 0)

        def Save(self) -> None:
            raise AssertionError("Save must not be called")

        def Move(self, destination: str) -> None:
            raise AssertionError(destination)

        def Delete(self) -> None:
            raise AssertionError("Delete must not be called")

    items = ItemCollectionFixture((MutatingMessage(),))
    inbox = FolderFixture("Inbox", items, FolderCollectionFixture(()))
    reader = ClassicOutlookReader(lambda: OutlookFixture(NamespaceFixture(inbox)))

    # When
    result = reader.read(date(2026, 8, 14), date(2026, 8, 14))

    # Then
    assert len(result) == 1


def test_reader_uses_injected_alert_patterns() -> None:
    # Given
    message = MessageFixture(
        EntryID="custom-pattern",
        Subject="Wire matched",
        Body="When: 2026-08-14\nWho: Delta Labs\nValue: KRW 50,000",
        ReceivedTime=datetime(2026, 8, 14, 12, 0),
    )
    items = ItemCollectionFixture((message,))
    inbox = FolderFixture("Inbox", items, FolderCollectionFixture(()))
    patterns = AlertPatternSet(
        deposit_keywords=("wire matched",),
        date_labels=("When",),
        name_labels=("Who",),
        amount_labels=("Value",),
    )
    reader = ClassicOutlookReader(lambda: OutlookFixture(NamespaceFixture(inbox)), patterns)

    # When
    result = reader.read(date(2026, 8, 14), date(2026, 8, 14))

    # Then
    assert result == (
        DepositNotice(
            message_id="custom-pattern",
            deposit_date=date(2026, 8, 14),
            depositor_name="Delta Labs",
            amount=50000,
            subject="Wire matched",
            received_at=datetime(2026, 8, 14, 12, 0),
        ),
    )


def test_reader_skips_archive_junk_and_deleted_subfolders() -> None:
    # Given
    kept_message = _message("kept", datetime(2026, 8, 14, 13, 0))
    skipped_message = _message("skipped", datetime(2026, 8, 14, 13, 1), "Excluded")
    archive_items = ItemCollectionFixture((skipped_message,))
    junk_items = ItemCollectionFixture((skipped_message,))
    deleted_items = ItemCollectionFixture((skipped_message,))
    folders = FolderCollectionFixture(
        (
            FolderFixture("Archive", archive_items, FolderCollectionFixture(())),
            FolderFixture("Junk Email", junk_items, FolderCollectionFixture(())),
            FolderFixture("Deleted Items", deleted_items, FolderCollectionFixture(())),
        )
    )
    inbox_items = ItemCollectionFixture((kept_message,))
    inbox = FolderFixture("Inbox", inbox_items, folders)
    reader = ClassicOutlookReader(lambda: OutlookFixture(NamespaceFixture(inbox)))

    # When
    result = reader.read(date(2026, 8, 14), date(2026, 8, 14))

    # Then
    assert tuple(notice.message_id for notice in result) == ("kept",)
    assert archive_items.sort_calls == []
    assert junk_items.sort_calls == []
    assert deleted_items.sort_calls == []


def test_reader_raises_activation_denied_error_for_elevation_mismatch() -> None:
    # Given
    def denied_dispatch() -> OutlookFixture:
        raise com_error(-2147024156, "800702E4", None, None)

    reader = ClassicOutlookReader(denied_dispatch)

    # When
    with pytest.raises(OutlookActivationDeniedError, match="Outlook 실행 권한"):
        reader.read(date(2026, 8, 14), date(2026, 8, 14))


def test_reader_raises_missing_profile_error_for_profile_failures() -> None:
    # Given
    def missing_profile_dispatch() -> OutlookFixture:
        raise com_error(-2147221231, "MAPI profile is unavailable", None, None)

    reader = ClassicOutlookReader(missing_profile_dispatch)

    # When
    with pytest.raises(MissingOutlookProfileError, match="Outlook 프로필"):
        reader.read(date(2026, 8, 14), date(2026, 8, 14))


def test_reader_raises_no_com_error_for_new_outlook_or_missing_classic_com() -> None:
    # Given
    def no_com_dispatch() -> OutlookFixture:
        raise OutlookComError("클래식 Outlook COM을 사용할 수 없습니다.")

    reader = ClassicOutlookReader(no_com_dispatch)

    # When
    with pytest.raises(OutlookComUnavailableError, match="클래식 Outlook"):
        reader.read(date(2026, 8, 14), date(2026, 8, 14))


def test_live_probe_reports_typed_error_instead_of_empty_success() -> None:
    # Given
    def denied_dispatch() -> OutlookFixture:
        raise com_error(-2147024156, "800702E4", None, None)

    reader = ClassicOutlookReader(denied_dispatch)

    # When
    result = live_read_only_probe(reader, date(2026, 8, 14), date(2026, 8, 14))

    # Then
    assert result.success is False
    assert result.count == 0
    assert result.hashed_message_ids == ()
    assert "Outlook 실행 권한" in result.detail
