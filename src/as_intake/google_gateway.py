from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import quote

from pydantic import BaseModel, Field, JsonValue

from .columns import SheetField
from .google_transport import JsonTransport
from .records import SheetRow


class SheetProperties(BaseModel):
    sheet_id: int = Field(alias="sheetId")
    title: str


class SheetMetadata(BaseModel):
    properties: SheetProperties


class SpreadsheetMetadata(BaseModel):
    sheets: list[SheetMetadata] = Field(default_factory=list)


class ValuesPayload(BaseModel):
    values: list[list[str | int | float | bool | None]] = Field(default_factory=list)


class MissingYearSheetError(LookupError):
    pass


class GoogleSheetsGateway:
    def __init__(self, spreadsheet_id: str, transport: JsonTransport) -> None:
        self._spreadsheet_id = spreadsheet_id
        self._transport = transport
        self._sheet_ids: dict[int, int] = {}

    def read_rows(self, year: int) -> tuple[SheetRow, ...]:
        tab = _tab_name(year)
        range_name = quote(f"'{tab}'!A5:AJ", safe="")
        url = (
            f"https://sheets.googleapis.com/v4/spreadsheets/{self._spreadsheet_id}"
            f"/values/{range_name}?majorDimension=ROWS&valueRenderOption=FORMATTED_VALUE"
        )
        payload = ValuesPayload.model_validate(self._transport.request("GET", url))
        return tuple(
            SheetRow.from_google_values(row_number, values)
            for row_number, values in enumerate(payload.values, start=5)
        )

    def insert_row(self, year: int, row: SheetRow) -> SheetRow:
        sheet_id = self._sheet_id(year)
        insert_request: dict[str, JsonValue] = {
            "insertDimension": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": 4,
                    "endIndex": 5,
                },
                "inheritFromBefore": False,
            }
        }
        self._batch_update(
            (
                _copy_row_format_request(sheet_id),
                insert_request,
                _update_cells_request(sheet_id, 4, row),
                _service_number_format_request(sheet_id, 4, row),
                _row_status_format_request(sheet_id, 4, row),
            ),
        )
        return SheetRow(row.values, row_number=5)

    def overwrite_row(self, year: int, row_number: int, row: SheetRow) -> SheetRow:
        sheet_id = self._sheet_id(year)
        row_index = row_number - 1
        self._batch_update(
            (
                _update_cells_request(sheet_id, row_index, row),
                _service_number_format_request(sheet_id, row_index, row),
                _row_status_format_request(sheet_id, row_index, row),
            )
        )
        return SheetRow(row.values, row_number=row_number)

    def _sheet_id(self, year: int) -> int:
        cached = self._sheet_ids.get(year)
        if cached is not None:
            return cached
        url = (
            f"https://sheets.googleapis.com/v4/spreadsheets/{self._spreadsheet_id}"
            "?fields=sheets.properties(sheetId,title)"
        )
        metadata = SpreadsheetMetadata.model_validate(self._transport.request("GET", url))
        tab = _tab_name(year)
        for sheet in metadata.sheets:
            if sheet.properties.title == tab:
                sheet_id = sheet.properties.sheet_id
                self._sheet_ids[year] = sheet_id
                return sheet_id
        raise MissingYearSheetError(f"Google 시트 탭을 찾을 수 없습니다: {tab}")

    def _batch_update(self, requests: tuple[dict[str, JsonValue], ...]) -> None:
        url = (
            f"https://sheets.googleapis.com/v4/spreadsheets/{self._spreadsheet_id}"
            ":batchUpdate"
        )
        payload: Mapping[str, JsonValue] = {"requests": list(requests)}
        self._transport.request("POST", url, payload)


def _tab_name(year: int) -> str:
    return f"{year} 국내 서비스 접수/처리 내역"


def _update_cells_request(sheet_id: int, row_index: int, row: SheetRow) -> dict[str, JsonValue]:
    cells: list[JsonValue] = [
        {"userEnteredValue": {"stringValue": value}} for value in row.values
    ]
    start: dict[str, JsonValue] = {
        "sheetId": sheet_id,
        "rowIndex": row_index,
        "columnIndex": 0,
    }
    update_cells: dict[str, JsonValue] = {
        "start": start,
        "rows": [{"values": cells}],
        "fields": "userEnteredValue",
    }
    return {"updateCells": update_cells}


def _copy_row_format_request(sheet_id: int) -> dict[str, JsonValue]:
    return {
        "copyPaste": {
            "source": {
                "sheetId": sheet_id,
                "startRowIndex": 5,
                "endRowIndex": 6,
                "startColumnIndex": 0,
                "endColumnIndex": 36,
            },
            "destination": {
                "sheetId": sheet_id,
                "startRowIndex": 4,
                "endRowIndex": 5,
                "startColumnIndex": 0,
                "endColumnIndex": 36,
            },
            "pasteType": "PASTE_FORMAT",
            "pasteOrientation": "NORMAL",
        }
    }


def _service_number_format_request(
    sheet_id: int,
    row_index: int,
    row: SheetRow,
) -> dict[str, JsonValue]:
    service_number = row.value(SheetField.SERVICE_NUMBER).strip().upper()
    color: dict[str, JsonValue] = (
        {"red": 1.0, "green": 0.9490196, "blue": 0.8}
        if service_number.startswith("DS")
        else {"red": 1.0, "green": 1.0, "blue": 1.0}
    )
    cell_range: dict[str, JsonValue] = {
        "sheetId": sheet_id,
        "startRowIndex": row_index,
        "endRowIndex": row_index + 1,
        "startColumnIndex": 0,
        "endColumnIndex": 1,
    }
    background: dict[str, JsonValue] = {"rgbColor": color}
    entered_format: dict[str, JsonValue] = {"backgroundColorStyle": background}
    cell: dict[str, JsonValue] = {"userEnteredFormat": entered_format}
    repeat_cell: dict[str, JsonValue] = {
        "range": cell_range,
        "cell": cell,
        "fields": "userEnteredFormat.backgroundColorStyle",
    }
    request: dict[str, JsonValue] = {
        "repeatCell": repeat_cell
    }
    return request


def _row_status_format_request(
    sheet_id: int,
    row_index: int,
    row: SheetRow,
) -> dict[str, JsonValue]:
    is_closed = row.value(SheetField.CLOSE_STATUS).strip() == "종료"
    channel = 0.9372549 if is_closed else 1.0
    color: dict[str, JsonValue] = {
        "red": channel,
        "green": channel,
        "blue": channel,
    }
    cell_range: dict[str, JsonValue] = {
        "sheetId": sheet_id,
        "startRowIndex": row_index,
        "endRowIndex": row_index + 1,
        "startColumnIndex": 1,
        "endColumnIndex": 36,
    }
    background: dict[str, JsonValue] = {"rgbColor": color}
    entered_format: dict[str, JsonValue] = {"backgroundColorStyle": background}
    cell: dict[str, JsonValue] = {"userEnteredFormat": entered_format}
    repeat_cell: dict[str, JsonValue] = {
        "range": cell_range,
        "cell": cell,
        "fields": "userEnteredFormat.backgroundColorStyle",
    }
    request: dict[str, JsonValue] = {
        "repeatCell": repeat_cell
    }
    return request
