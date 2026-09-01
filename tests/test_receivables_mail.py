from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from receivables_reconciliation.mail_parser import AlertPatternSet, NotDeposit, parse_message
from receivables_reconciliation.models import DepositNotice, UnparsedDepositNotice


@dataclass(frozen=True, slots=True)
class MailFixture:
    EntryID: str
    Subject: str
    Body: str
    ReceivedTime: datetime


def test_parse_message_returns_notice_when_korean_labels_are_complete() -> None:
    # Given
    message = MailFixture(
        EntryID="msg-1",
        Subject="입금 알림",
        Body="입금일시: 2026-08-14 09:31\n입금자: 김민수\n입금액: 1,234,500원",
        ReceivedTime=datetime(2026, 8, 14, 9, 32),
    )

    # When
    result = parse_message(message)

    # Then
    assert result == DepositNotice(
        message_id="msg-1",
        deposit_date=datetime(2026, 8, 14, 9, 31).date(),
        depositor_name="김민수",
        amount=1234500,
        subject="입금 알림",
        received_at=datetime(2026, 8, 14, 9, 32),
    )


def test_parse_message_returns_notice_when_english_keyword_and_custom_labels_match() -> None:
    # Given
    message = MailFixture(
        EntryID="msg-2",
        Subject="Payment received",
        Body="Paid on: 2026/08/13\nSender: ACME Korea\nTotal: KRW 88,000",
        ReceivedTime=datetime(2026, 8, 13, 18, 2),
    )
    patterns = AlertPatternSet(
        deposit_keywords=("payment received",),
        date_labels=("Paid on",),
        name_labels=("Sender",),
        amount_labels=("Total",),
    )

    # When
    result = parse_message(message, patterns)

    # Then
    assert result == DepositNotice(
        message_id="msg-2",
        deposit_date=datetime(2026, 8, 13).date(),
        depositor_name="ACME Korea",
        amount=88000,
        subject="Payment received",
        received_at=datetime(2026, 8, 13, 18, 2),
    )


def test_parse_message_returns_every_deposit_row_from_outlook_plain_text_table() -> None:
    # Given
    message = MailFixture(
        EntryID="msg-table",
        Subject="8/21 국내입금",
        Body=(
            "안녕하세요.\n국내 입금 송부드립니다.\n"
            "일자\n거래처\n금액\n금융기관\n　\n"
            "2026-08-21\n장경진(세종씨엠에스)\n44,000\n기업018(원화)\n　\n"
            "2026-08-21\n강동미사노블요양병원\n165,000\n국민648(원화)"
        ),
        ReceivedTime=datetime(2026, 8, 21, 10, 0),
    )

    # When
    result = parse_message(message)

    # Then
    assert isinstance(result, tuple)
    assert [(notice.depositor_name, notice.amount, notice.bank_name) for notice in result] == [
        ("장경진(세종씨엠에스)", 44_000, "기업018(원화)"),
        ("강동미사노블요양병원", 165_000, "국민648(원화)"),
    ]
    assert [notice.message_id for notice in result] == ["msg-table", "msg-table#2"]


def test_parse_message_preserves_deposit_candidate_when_required_labels_are_missing() -> None:
    # Given
    message = MailFixture(
        EntryID="msg-3",
        Subject="송금 완료",
        Body="금액: 10,000원\n확인 후 처리해주세요",
        ReceivedTime=datetime(2026, 8, 14, 10, 0),
    )

    # When
    result = parse_message(message)

    # Then
    assert result == UnparsedDepositNotice(
        message_id="msg-3",
        received_at=datetime(2026, 8, 14, 10, 0),
        subject="송금 완료",
        reason="입금 후보 메일에서 입금일자 또는 입금자를 찾을 수 없습니다.",
    )


def test_parse_message_returns_unparsed_for_malformed_date_and_amount_is_data_only() -> None:
    # Given
    message = MailFixture(
        EntryID="msg-4",
        Subject="credited alert",
        Body="거래일자: 내일 삭제\n송금인: <script>홍길동</script>\n거래금액: DROP TABLE 1,000",
        ReceivedTime=datetime(2026, 8, 14, 10, 5),
    )

    # When
    result = parse_message(message)

    # Then
    assert result == UnparsedDepositNotice(
        message_id="msg-4",
        received_at=datetime(2026, 8, 14, 10, 5),
        subject="credited alert",
        reason="입금 후보 메일의 입금일자를 해석할 수 없습니다.",
    )


def test_parse_message_ignores_irrelevant_mail() -> None:
    # Given
    message = MailFixture(
        EntryID="msg-5",
        Subject="주간 회의",
        Body="안건을 공유합니다.",
        ReceivedTime=datetime(2026, 8, 14, 11, 0),
    )

    # When
    result = parse_message(message)

    # Then
    assert result == NotDeposit(reason="입금 알림 키워드가 없습니다.")
