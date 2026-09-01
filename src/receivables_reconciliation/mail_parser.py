from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final, Protocol

from receivables_reconciliation.models import DepositNotice, UnparsedDepositNotice


@dataclass(frozen=True, slots=True)
class AlertPatternSet:
    deposit_keywords: tuple[str, ...] = (
        "입금",
        "송금",
        "이체",
        "deposit",
        "credited",
        "payment received",
    )
    date_labels: tuple[str, ...] = ("입금일시", "입금일자", "거래일시", "거래일자", "처리일시")
    name_labels: tuple[str, ...] = ("입금자", "입금인", "송금인", "보낸분", "의뢰인")
    amount_labels: tuple[str, ...] = ("입금액", "거래금액", "금액")


@dataclass(frozen=True, slots=True)
class NotDeposit:
    reason: str


class MailMessage(Protocol):
    @property
    def EntryID(self) -> str: ...

    @property
    def Subject(self) -> str: ...

    @property
    def Body(self) -> str: ...

    @property
    def ReceivedTime(self) -> datetime: ...


ParseResult = DepositNotice | tuple[DepositNotice, ...] | UnparsedDepositNotice | NotDeposit

DEFAULT_ALERT_PATTERNS: Final = AlertPatternSet()
_MISSING_REQUIRED_REASON: Final = "입금 후보 메일에서 입금일자 또는 입금자를 찾을 수 없습니다."
_BAD_DATE_REASON: Final = "입금 후보 메일의 입금일자를 해석할 수 없습니다."
_NO_KEYWORD_REASON: Final = "입금 알림 키워드가 없습니다."
_DATE_PATTERNS: Final = (
    re.compile(r"(?P<year>\d{4})[-/.](?P<month>\d{1,2})[-/.](?P<day>\d{1,2})"),
    re.compile(r"(?P<year>\d{4})년\s*(?P<month>\d{1,2})월\s*(?P<day>\d{1,2})일"),
)
_AMOUNT_DIGITS: Final = re.compile(r"\d[\d,]*")
_TABLE_HEADERS: Final = ("일자", "거래처", "금액", "금융기관")


def parse_message(
    message: MailMessage,
    patterns: AlertPatternSet = DEFAULT_ALERT_PATTERNS,
) -> ParseResult:
    text = f"{message.Subject}\n{message.Body}"
    if not _contains_keyword(text, patterns.deposit_keywords):
        return NotDeposit(_NO_KEYWORD_REASON)

    table_notices = _parse_table_notices(message)
    if table_notices:
        return table_notices

    date_text = _find_labeled_value(message.Body, patterns.date_labels)
    depositor_name = _find_labeled_value(message.Body, patterns.name_labels)
    amount_text = _find_labeled_value(message.Body, patterns.amount_labels)
    if date_text is None or depositor_name is None:
        return UnparsedDepositNotice(
            message_id=message.EntryID,
            received_at=message.ReceivedTime,
            subject=message.Subject,
            reason=_MISSING_REQUIRED_REASON,
        )

    deposit_date = _parse_date(date_text)
    if deposit_date is None:
        return UnparsedDepositNotice(
            message_id=message.EntryID,
            received_at=message.ReceivedTime,
            subject=message.Subject,
            reason=_BAD_DATE_REASON,
        )

    return DepositNotice(
        message_id=message.EntryID,
        deposit_date=deposit_date,
        depositor_name=depositor_name,
        amount=_parse_amount(amount_text),
        subject=message.Subject,
        received_at=message.ReceivedTime,
    )


def _parse_table_notices(message: MailMessage) -> tuple[DepositNotice, ...]:
    values = _table_values(message.Body)
    if not values or len(values) % len(_TABLE_HEADERS) != 0:
        return ()
    notices: list[DepositNotice] = []
    for offset in range(0, len(values), len(_TABLE_HEADERS)):
        date_text, depositor_name, amount_text, bank_name = values[offset : offset + 4]
        deposit_date = _parse_date(date_text)
        amount = _parse_amount(amount_text)
        if deposit_date is None or amount is None:
            return ()
        row_number = offset // len(_TABLE_HEADERS) + 1
        message_id = message.EntryID if row_number == 1 else f"{message.EntryID}#{row_number}"
        notices.append(
            DepositNotice(
                message_id=message_id,
                deposit_date=deposit_date,
                depositor_name=depositor_name,
                amount=amount,
                subject=message.Subject,
                received_at=message.ReceivedTime,
                bank_name=bank_name,
            )
        )
    return tuple(notices)


def _table_values(text: str) -> tuple[str, ...]:
    lines = tuple(line.strip() for line in text.splitlines() if line.strip())
    header_count = len(_TABLE_HEADERS)
    for index in range(len(lines) - header_count + 1):
        if lines[index : index + header_count] == _TABLE_HEADERS:
            return lines[index + header_count :]
    return ()


def _contains_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    normalized = text.casefold()
    return any(keyword.casefold() in normalized for keyword in keywords)


def _find_labeled_value(text: str, labels: tuple[str, ...]) -> str | None:
    for label in labels:
        pattern = re.compile(rf"(^|\n)\s*{re.escape(label)}\s*[:：]\s*(?P<value>[^\r\n]+)")
        match = pattern.search(text)
        if match is not None:
            value = match.group("value").strip()
            if value:
                return value
    return None


def _parse_date(raw: str) -> date | None:
    for pattern in _DATE_PATTERNS:
        match = pattern.search(raw)
        if match is None:
            continue
        try:
            return date(
                int(match.group("year")),
                int(match.group("month")),
                int(match.group("day")),
            )
        except ValueError:
            return None
    return None


def _parse_amount(raw: str | None) -> int | None:
    if raw is None:
        return None
    match = _AMOUNT_DIGITS.search(raw)
    if match is None:
        return None
    return int(match.group(0).replace(",", ""))
