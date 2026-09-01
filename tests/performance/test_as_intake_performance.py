from __future__ import annotations

import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from time import perf_counter

import pytest
from pydantic import JsonValue

from as_intake.google_gateway import GoogleSheetsGateway
from as_intake.google_transport import GoogleAuthTransport
from as_intake.records import SheetRow
from as_intake.service import ASIntakeService, SearchQuery


class CountingTransport:
    def __init__(self) -> None:
        self.metadata_reads = 0

    def request(
        self,
        method: str,
        url: str,
        payload: Mapping[str, JsonValue] | None = None,
    ) -> JsonValue:
        del payload
        if method == "GET" and "fields=sheets.properties" in url:
            self.metadata_reads += 1
            return {
                "sheets": [
                    {
                        "properties": {
                            "sheetId": 779531332,
                            "title": "2026 국내 서비스 접수/처리 내역",
                        }
                    }
                ]
            }
        return {"replies": []}


class StaticRowsGateway:
    def __init__(self, rows: tuple[SheetRow, ...]) -> None:
        self._rows = rows

    def read_rows(self, year: int) -> tuple[SheetRow, ...]:
        del year
        return self._rows

    def insert_row(self, year: int, row: SheetRow) -> SheetRow:
        raise AssertionError((year, row))

    def overwrite_row(self, year: int, row_number: int, row: SheetRow) -> SheetRow:
        raise AssertionError((year, row_number, row))


def _row() -> SheetRow:
    return SheetRow(("",) * 36)


def test_main_module_import_completes_within_startup_budget() -> None:
    # Given
    command = (
        "import time; "
        "started = time.perf_counter(); "
        "import as_intake.main; "
        "print(time.perf_counter() - started)"
    )

    # When
    completed = subprocess.run(
        (sys.executable, "-c", command),
        check=True,
        capture_output=True,
        text=True,
    )

    # Then
    assert float(completed.stdout.strip()) < 0.65


def test_google_transport_defers_credentials_until_first_request(tmp_path: Path) -> None:
    # Given
    missing_client = tmp_path / "missing-client.json"
    token_file = tmp_path / "token.json"

    # When
    transport = GoogleAuthTransport(missing_client, token_file)

    # Then
    with pytest.raises(FileNotFoundError, match="OAuth 클라이언트"):
        transport.request("GET", "https://example.invalid")


def test_repeated_writes_reuse_sheet_metadata() -> None:
    # Given
    transport = CountingTransport()
    gateway = GoogleSheetsGateway("spreadsheet-id", transport)

    # When
    gateway.overwrite_row(2026, 5, _row())
    gateway.overwrite_row(2026, 6, _row())

    # Then
    assert transport.metadata_reads == 1


def test_default_text_search_completes_within_cpu_budget() -> None:
    # Given
    row = SheetRow(("DS26082401",) + ("",) * 35)
    service = ASIntakeService(StaticRowsGateway((row,) * 200_000))

    # When
    started = perf_counter()
    result = service.search(SearchQuery(2026, "DS"))
    elapsed = perf_counter() - started

    # Then
    assert len(result) == 200_000
    assert elapsed < 0.18
