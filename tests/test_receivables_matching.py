from datetime import UTC, date, datetime

from receivables_reconciliation import (
    DepositNotice,
    ErpRegistration,
    MatchStatus,
    reconcile,
)
from receivables_reconciliation.matching import normalize_name


def test_reconcile_marks_registered_and_unregistered_when_exact_key_counts_are_singletons() -> None:
    # Given
    received_at = datetime(2026, 8, 14, 9, 30, tzinfo=UTC)
    notices = (
        DepositNotice("msg-1", date(2026, 8, 14), " Acme Corp ", 100_000, "deposit", received_at),
        DepositNotice("msg-2", date(2026, 8, 14), "Beta LLC", None, "deposit", received_at),
        DepositNotice("msg-3", date(2026, 8, 15), "Gamma", 1, "deposit", received_at),
    )
    registrations = (
        ErpRegistration(10, date(2026, 8, 14), "Ignored Customer", "acmecorp", False),
        ErpRegistration(11, date(2026, 8, 15), "Gamma", None, False),
    )

    # When
    results = reconcile(notices, registrations)

    # Then
    assert tuple(result.status for result in results) == (
        MatchStatus.REGISTERED,
        MatchStatus.UNREGISTERED,
        MatchStatus.REGISTERED,
    )
    assert tuple(result.notice.message_id for result in results) == ("msg-1", "msg-2", "msg-3")
    assert results[0].reason == "exact_match"
    assert results[1].reason == "no_erp_registration"


def test_reconcile_ignores_amount_when_exact_key_matches() -> None:
    # Given
    received_at = datetime(2026, 8, 14, 9, 30, tzinfo=UTC)
    notice = DepositNotice("msg-1", date(2026, 8, 14), "Acme", 999_999, "deposit", received_at)
    registration = ErpRegistration(10, date(2026, 8, 14), "Acme", None, False)

    # When
    results = reconcile((notice,), (registration,))

    # Then
    assert tuple(result.status for result in results) == (MatchStatus.REGISTERED,)


def test_reconcile_marks_every_duplicate_outlook_notice_for_review() -> None:
    # Given
    received_at = datetime(2026, 8, 14, 9, 30, tzinfo=UTC)
    notices = (
        DepositNotice("msg-1", date(2026, 8, 14), "Acme", 1, "deposit", received_at),
        DepositNotice("msg-2", date(2026, 8, 14), " A c m e ", 2, "deposit", received_at),
    )
    registrations = (ErpRegistration(10, date(2026, 8, 14), "Acme", None, False),)

    # When
    results = reconcile(notices, registrations)

    # Then
    assert tuple(result.status for result in results) == (
        MatchStatus.REVIEW_NEEDED,
        MatchStatus.REVIEW_NEEDED,
    )
    assert tuple(result.reason for result in results) == ("ambiguous_match", "ambiguous_match")


def test_reconcile_marks_duplicate_erp_group_for_review() -> None:
    # Given
    received_at = datetime(2026, 8, 14, 9, 30, tzinfo=UTC)
    notices = (DepositNotice("msg-1", date(2026, 8, 14), "Acme", 1, "deposit", received_at),)
    registrations = (
        ErpRegistration(10, date(2026, 8, 14), "Acme", None, False),
        ErpRegistration(11, date(2026, 8, 14), "Other", " A c m e ", True),
    )

    # When
    results = reconcile(notices, registrations)

    # Then
    assert tuple(result.status for result in results) == (MatchStatus.REVIEW_NEEDED,)
    assert tuple(result.reason for result in results) == ("ambiguous_match",)


def test_reconcile_marks_same_date_personal_erp_row_without_depositor_for_review() -> None:
    # Given
    received_at = datetime(2026, 8, 14, 9, 30, tzinfo=UTC)
    notices = (
        DepositNotice("msg-1", date(2026, 8, 14), "Alice", 1, "deposit", received_at),
        DepositNotice("msg-2", date(2026, 8, 15), "Bob", 1, "deposit", received_at),
    )
    registrations = (
        ErpRegistration(10, date(2026, 8, 14), "Personal Customer", None, True),
        ErpRegistration(11, date(2026, 8, 15), "Personal Customer", " \t", True),
    )

    # When
    results = reconcile(notices, registrations)

    # Then
    assert tuple(result.status for result in results) == (
        MatchStatus.REVIEW_NEEDED,
        MatchStatus.REVIEW_NEEDED,
    )
    assert tuple(result.reason for result in results) == ("ambiguous_match", "ambiguous_match")


def test_normalize_name_handles_unicode_whitespace_casefolding_and_punctuation() -> None:
    # Given
    raw = " \uff21cme-\u2003Corp\u321c\n"

    # When
    normalized = normalize_name(raw)

    # Then
    assert normalized == "acme-corp(\uc8fc)"


def test_reconcile_has_defined_empty_name_outcome() -> None:
    # Given
    received_at = datetime(2026, 8, 14, 9, 30, tzinfo=UTC)
    notices = (
        DepositNotice("msg-1", date(2026, 8, 14), "\t \u2003", 1, "deposit", received_at),
        DepositNotice("msg-2", date(2026, 8, 15), "", 1, "deposit", received_at),
    )
    registrations = (ErpRegistration(10, date(2026, 8, 14), "", " \n", True),)

    # When
    results = reconcile(notices, registrations)

    # Then
    assert normalize_name("\t \u2003") == ""
    assert tuple(result.status for result in results) == (
        MatchStatus.REVIEW_NEEDED,
        MatchStatus.UNREGISTERED,
    )
