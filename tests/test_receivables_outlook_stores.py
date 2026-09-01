from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime

from receivables_reconciliation.models import DepositNotice
from receivables_reconciliation.outlook_reader import ClassicOutlookReader


@dataclass(frozen=True, slots=True)
class MessageFixture:
    EntryID: str
    Subject: str
    Body: str
    ReceivedTime: datetime


class ItemCollectionFixture:
    def __init__(self, messages: tuple[MessageFixture, ...]) -> None:
        self.messages = messages
        self.sort_calls: list[tuple[str, bool]] = []

    def Sort(self, field_name: str, descending: bool) -> None:
        self.sort_calls.append((field_name, descending))
        self.messages = tuple(
            sorted(self.messages, key=lambda message: message.ReceivedTime, reverse=descending)
        )

    def __iter__(self) -> Iterator[MessageFixture]:
        return iter(self.messages)


@dataclass(frozen=True, slots=True)
class FolderCollectionFixture:
    def __iter__(self) -> Iterator[FolderFixture]:
        return iter(())


@dataclass(frozen=True, slots=True)
class FolderFixture:
    Name: str
    Items: ItemCollectionFixture
    Folders: FolderCollectionFixture


@dataclass(frozen=True, slots=True)
class StoreFixture:
    inbox: FolderFixture

    def GetDefaultFolder(self, folder_id: int) -> FolderFixture:
        assert folder_id == 6
        return self.inbox


@dataclass(frozen=True, slots=True)
class StoreCollectionFixture:
    stores: tuple[StoreFixture, ...]

    def __iter__(self) -> Iterator[StoreFixture]:
        return iter(self.stores)


@dataclass(frozen=True, slots=True)
class NamespaceFixture:
    Stores: StoreCollectionFixture
    fallback_inbox: FolderFixture

    def GetDefaultFolder(self, folder_id: int) -> FolderFixture:
        assert folder_id == 6
        return self.fallback_inbox


@dataclass(frozen=True, slots=True)
class OutlookFixture:
    namespace: NamespaceFixture

    def GetNamespace(self, namespace_name: str) -> NamespaceFixture:
        assert namespace_name == "MAPI"
        return self.namespace


def _message(entry_id: str, received_at: datetime, depositor: str) -> MessageFixture:
    return MessageFixture(
        EntryID=entry_id,
        Subject="입금 알림",
        Body=f"입금일자: {received_at:%Y-%m-%d}\n입금자: {depositor}\n금액: 10,000원",
        ReceivedTime=received_at,
    )


def test_reader_selects_store_with_most_recent_inbox_message() -> None:
    # Given
    stale_items = ItemCollectionFixture(
        (_message("stale", datetime(2026, 6, 29, 17, 4), "과거입금자"),)
    )
    active_items = ItemCollectionFixture(
        (_message("active", datetime(2026, 8, 21, 10, 0), "최신입금자"),)
    )
    empty_folders = FolderCollectionFixture()
    stale_inbox = FolderFixture("Inbox", stale_items, empty_folders)
    active_inbox = FolderFixture("Inbox", active_items, empty_folders)
    stores = StoreCollectionFixture((StoreFixture(stale_inbox), StoreFixture(active_inbox)))
    namespace = NamespaceFixture(stores, stale_inbox)
    reader = ClassicOutlookReader(lambda: OutlookFixture(namespace))

    # When
    result = reader.read(date(2026, 8, 21), date(2026, 8, 21))

    # Then
    assert len(result) == 1
    only = result[0]
    assert isinstance(only, DepositNotice)
    assert only.message_id == "active"
    assert only.depositor_name == "최신입금자"
    assert stale_items.sort_calls == [("[ReceivedTime]", True)]
    assert active_items.sort_calls == [
        ("[ReceivedTime]", True),
        ("[ReceivedTime]", True),
    ]
