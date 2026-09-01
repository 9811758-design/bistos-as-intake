from __future__ import annotations

from collections.abc import Mapping

from pydantic import JsonValue

from as_intake.columns import SheetField
from as_intake.google_gateway import GoogleSheetsGateway
from as_intake.records import SheetRow


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Mapping[str, JsonValue] | None]] = []

    def request(
        self,
        method: str,
        url: str,
        payload: Mapping[str, JsonValue] | None = None,
    ) -> JsonValue:
        self.calls.append((method, url, payload))
        if method == "GET" and "fields=sheets.properties" in url:
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
        if method == "GET":
            return {"values": [["DS26082401", "8월", "장진영"]]}
        return {"replies": []}


def _mapping(value: JsonValue) -> Mapping[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _sequence(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, list)
    return value


def _request_named(
    requests: list[JsonValue],
    name: str,
) -> Mapping[str, JsonValue]:
    for request in requests:
        mapped = _mapping(request)
        if name in mapped:
            return _mapping(mapped[name])
    raise AssertionError(f"요청을 찾을 수 없습니다: {name}")


def _row() -> SheetRow:
    values = [""] * 36
    values[SheetField.SERVICE_NUMBER] = "DS26082402"
    values[SheetField.RECEIPT_MONTH] = "8월"
    values[SheetField.RECEIVER] = "장진영"
    return SheetRow(tuple(values))


def test_gateway_reads_a5_to_aj_and_preserves_sheet_row_number() -> None:
    gateway = GoogleSheetsGateway("spreadsheet-id", FakeTransport())

    rows = gateway.read_rows(2026)

    assert len(rows) == 1
    assert rows[0].row_number == 5
    assert rows[0].value(SheetField.SERVICE_NUMBER) == "DS26082401"


def test_gateway_inserts_row_five_and_updates_all_36_cells_atomically() -> None:
    transport = FakeTransport()
    gateway = GoogleSheetsGateway("spreadsheet-id", transport)

    stored = gateway.insert_row(2026, _row())

    method, url, payload = transport.calls[-1]
    assert method == "POST"
    assert url.endswith(":batchUpdate")
    assert payload is not None
    requests = _sequence(payload["requests"])
    insert_dimension = _request_named(requests, "insertDimension")
    assert _mapping(insert_dimension["range"])["startIndex"] == 4
    assert insert_dimension["inheritFromBefore"] is False
    update_cells = _request_named(requests, "updateCells")
    rows = _sequence(update_cells["rows"])
    assert len(_sequence(_mapping(rows[0])["values"])) == 36
    assert stored.row_number == 5


def test_gateway_overwrites_exact_row_across_a_to_aj() -> None:
    transport = FakeTransport()
    gateway = GoogleSheetsGateway("spreadsheet-id", transport)

    stored = gateway.overwrite_row(2026, 12, _row())

    payload = transport.calls[-1][2]
    assert payload is not None
    requests = _sequence(payload["requests"])
    request = _request_named(requests, "updateCells")
    assert _mapping(request["start"])["rowIndex"] == 11
    rows = _sequence(request["rows"])
    assert len(_sequence(_mapping(rows[0])["values"])) == 36
    assert stored.row_number == 12


def test_gateway_writes_formula_like_user_text_as_literal_string() -> None:
    transport = FakeTransport()
    gateway = GoogleSheetsGateway("spreadsheet-id", transport)
    hostile = _row().with_value(SheetField.NOTE, '=IMPORTXML("https://example.invalid")')

    gateway.insert_row(2026, hostile)

    payload = transport.calls[-1][2]
    assert payload is not None
    requests = _sequence(payload["requests"])
    update_cells = _request_named(requests, "updateCells")
    rows = _sequence(update_cells["rows"])
    cells = _sequence(_mapping(rows[0])["values"])
    assert cells[SheetField.NOTE] == {
        "userEnteredValue": {"stringValue": '=IMPORTXML("https://example.invalid")'}
    }


def test_gateway_inserts_with_sheet_row_format_and_yellow_service_number() -> None:
    # Given: a new open service row.
    transport = FakeTransport()
    gateway = GoogleSheetsGateway("spreadsheet-id", transport)

    # When: the row is inserted at the top of the live table.
    gateway.insert_row(2026, _row())

    # Then: the live row format is copied and A is yellow while B:AJ stays white.
    payload = transport.calls[-1][2]
    assert payload is not None
    requests = _sequence(payload["requests"])
    copy_format = _request_named(requests, "copyPaste")
    assert copy_format["pasteType"] == "PASTE_FORMAT"
    assert _mapping(copy_format["source"])["startRowIndex"] == 5
    assert _mapping(copy_format["destination"])["startRowIndex"] == 4
    repeat_cells = [
        _mapping(_mapping(request)["repeatCell"])
        for request in requests
        if "repeatCell" in _mapping(request)
    ]
    assert _mapping(repeat_cells[0]["range"])["startColumnIndex"] == 0
    assert _mapping(repeat_cells[0]["cell"])["userEnteredFormat"] == {
        "backgroundColorStyle": {
            "rgbColor": {"red": 1.0, "green": 0.9490196, "blue": 0.8}
        }
    }
    assert _mapping(repeat_cells[1]["range"])["startColumnIndex"] == 1
    assert _mapping(repeat_cells[1]["cell"])["userEnteredFormat"] == {
        "backgroundColorStyle": {
            "rgbColor": {"red": 1.0, "green": 1.0, "blue": 1.0}
        }
    }


def test_gateway_overwrite_marks_closed_row_gray_except_service_number() -> None:
    # Given: an existing service row whose close status is 종료.
    transport = FakeTransport()
    gateway = GoogleSheetsGateway("spreadsheet-id", transport)
    closed = _row().with_value(SheetField.CLOSE_STATUS, "종료")

    # When: the exact row is overwritten.
    gateway.overwrite_row(2026, 23, closed)

    # Then: A remains yellow and B:AJ receives the live sheet's gray close color.
    payload = transport.calls[-1][2]
    assert payload is not None
    requests = _sequence(payload["requests"])
    repeat_cells = [
        _mapping(_mapping(request)["repeatCell"])
        for request in requests
        if "repeatCell" in _mapping(request)
    ]
    service_range = _mapping(repeat_cells[0]["range"])
    closed_range = _mapping(repeat_cells[1]["range"])
    assert service_range["startRowIndex"] == 22
    assert service_range["startColumnIndex"] == 0
    assert closed_range["startColumnIndex"] == 1
    assert closed_range["endColumnIndex"] == 36
    assert _mapping(repeat_cells[1]["cell"])["userEnteredFormat"] == {
        "backgroundColorStyle": {
            "rgbColor": {
                "red": 0.9372549,
                "green": 0.9372549,
                "blue": 0.9372549,
            }
        }
    }
