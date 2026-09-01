from collections import Counter
from datetime import date
from typing import Final
from unicodedata import normalize

from receivables_reconciliation.models import (
    DepositNotice,
    ErpRegistration,
    MatchResult,
    MatchStatus,
)

MatchKey = tuple[date, str]

_EXACT_MATCH: Final = "exact_match"
_NO_ERP_REGISTRATION: Final = "no_erp_registration"
_AMBIGUOUS_MATCH: Final = "ambiguous_match"


def normalize_name(raw: str) -> str:
    normalized = normalize("NFKC", raw)
    compact = "".join(character for character in normalized if not character.isspace())
    return compact.casefold()


def reconcile(
    notices: tuple[DepositNotice, ...],
    registrations: tuple[ErpRegistration, ...],
) -> tuple[MatchResult, ...]:
    notice_counts = Counter(_notice_key(notice) for notice in notices)
    registration_counts = Counter(_registration_key(registration) for registration in registrations)
    ambiguous_personal_dates = frozenset(
        registration.receipt_date
        for registration in registrations
        if _is_ambiguous_personal_registration(registration)
    )

    return tuple(
        MatchResult(
            status=_status_for_key(
                _notice_key(notice),
                notice_counts,
                registration_counts,
                ambiguous_personal_dates,
            ),
            notice=notice,
            reason=_reason_for_key(
                _notice_key(notice),
                notice_counts,
                registration_counts,
                ambiguous_personal_dates,
            ),
        )
        for notice in notices
    )


def _notice_key(notice: DepositNotice) -> MatchKey:
    return (notice.deposit_date, normalize_name(notice.depositor_name))


def _registration_key(registration: ErpRegistration) -> MatchKey:
    depositor_name = registration.depositor_name
    return (
        registration.receipt_date,
        normalize_name(registration.customer_name if depositor_name is None else depositor_name),
    )


def _is_ambiguous_personal_registration(registration: ErpRegistration) -> bool:
    depositor_name = registration.depositor_name
    return registration.is_personal and (
        depositor_name is None or normalize_name(depositor_name) == ""
    )


def _status_for_key(
    key: MatchKey,
    notice_counts: Counter[MatchKey],
    registration_counts: Counter[MatchKey],
    ambiguous_personal_dates: frozenset[date],
) -> MatchStatus:
    deposit_date, _depositor_name = key
    if (
        deposit_date in ambiguous_personal_dates
        or notice_counts[key] > 1
        or registration_counts[key] > 1
    ):
        return MatchStatus.REVIEW_NEEDED
    if registration_counts[key] == 1:
        return MatchStatus.REGISTERED
    return MatchStatus.UNREGISTERED


def _reason_for_key(
    key: MatchKey,
    notice_counts: Counter[MatchKey],
    registration_counts: Counter[MatchKey],
    ambiguous_personal_dates: frozenset[date],
) -> str:
    deposit_date, _depositor_name = key
    if (
        deposit_date in ambiguous_personal_dates
        or notice_counts[key] > 1
        or registration_counts[key] > 1
    ):
        return _AMBIGUOUS_MATCH
    if registration_counts[key] == 1:
        return _EXACT_MATCH
    return _NO_ERP_REGISTRATION
