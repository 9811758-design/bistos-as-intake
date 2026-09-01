from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class DepositNotice:
    message_id: str
    deposit_date: date
    depositor_name: str
    amount: int | None
    subject: str
    received_at: datetime
    bank_name: str = ""


@dataclass(frozen=True, slots=True)
class UnparsedDepositNotice:
    message_id: str
    received_at: datetime
    subject: str
    reason: str


@dataclass(frozen=True, slots=True)
class ErpRegistration:
    row_number: int
    receipt_date: date
    customer_name: str
    depositor_name: str | None
    is_personal: bool


class MatchStatus(StrEnum):
    REGISTERED = "registered"
    UNREGISTERED = "unregistered"
    REVIEW_NEEDED = "review_needed"


@dataclass(frozen=True, slots=True)
class MatchResult:
    status: MatchStatus
    notice: DepositNotice
    reason: str
