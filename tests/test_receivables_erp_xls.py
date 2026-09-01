from __future__ import annotations

from datetime import date
from hashlib import sha256
from pathlib import Path

import pytest

from receivables_reconciliation.erp_xls import (
    ErpXlsCellError,
    ErpXlsFileError,
    ErpXlsHeaderError,
    read_erp_registrations,
)

FIXTURE_PATH = Path("tests/fixtures/receivables_sample.xls")
FIXTURE_SHA256 = "975f8e1998961c57c75c399abf53a3210c1871bf59b3a38c8acced8c17025da1"


def test_fixture_hash_when_sanitized_sample_changes() -> None:
    # Given: the checked-in sanitized BIFF fixture
    data = FIXTURE_PATH.read_bytes()

    # When: its content hash is computed
    digest = sha256(data).hexdigest()

    # Then: unexpected fixture replacement is visible in test output
    assert digest == FIXTURE_SHA256


def test_read_erp_registrations_when_valid_legacy_xls() -> None:
    # Given: a sanitized legacy ERP BIFF .xls export with shifted headers
    path = FIXTURE_PATH

    # When: the reader parses the workbook
    registrations = read_erp_registrations(path)

    # Then: blank rows are ignored and required semantic fields are parsed
    assert len(registrations) == 5
    assert registrations[0].receipt_date == date(2026, 8, 1)
    assert registrations[0].customer_name == "Alpha Clinic"
    assert registrations[0].depositor_name == "Alpha Clinic"
    assert registrations[0].row_number == 4
    assert registrations[0].is_personal is False


def test_read_erp_registrations_when_personal_markers_use_note_name() -> None:
    # Given: personal ERP rows using both supported markers
    path = FIXTURE_PATH

    # When: the reader parses personal registrations
    registrations = read_erp_registrations(path)

    # Then: the final slash-delimited note segment is the review match name
    assert registrations[1].customer_name == "개인매출"
    assert registrations[1].depositor_name == "홍길동"
    assert registrations[1].is_personal is True
    assert registrations[2].customer_name == "개인고객"
    assert registrations[2].depositor_name is None
    assert registrations[2].is_personal is True


def test_read_erp_registrations_when_duplicate_required_headers() -> None:
    # Given: a sheet with two semantic note headers
    path = FIXTURE_PATH

    # When / Then: the reader rejects the duplicate required header in Korean
    with pytest.raises(ErpXlsHeaderError, match="중복"):
        read_erp_registrations(path, sheet_name="duplicate headers")


def test_read_erp_registrations_when_missing_required_header() -> None:
    # Given: a sheet missing the required note header
    path = FIXTURE_PATH

    # When / Then: the reader rejects the missing required header in Korean
    with pytest.raises(ErpXlsHeaderError, match="필수.*비고"):
        read_erp_registrations(path, sheet_name="missing headers")


def test_read_erp_registrations_when_workbook_is_corrupt(tmp_path: Path) -> None:
    # Given: a corrupt OLE/BIFF file path
    path = tmp_path / "corrupt.xls"
    path.write_bytes(b"not an ole workbook")

    # When / Then: the reader reports an unreadable ERP file in Korean
    with pytest.raises(ErpXlsFileError, match="읽을 수 없습니다"):
        read_erp_registrations(path)


def test_read_erp_registrations_when_date_is_invalid() -> None:
    # Given: a row with a syntactically date-like but invalid date
    path = FIXTURE_PATH

    # When / Then: the reader reports the invalid receipt date
    with pytest.raises(ErpXlsCellError, match="수금일자"):
        read_erp_registrations(path, sheet_name="invalid date")
