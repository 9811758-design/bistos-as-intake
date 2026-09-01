from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from .columns import COLUMN_COUNT, SheetField


class InvalidSheetRowError(ValueError):
    pass


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return str(value)


@dataclass(frozen=True, slots=True)
class SheetRow:
    values: tuple[str, ...]
    row_number: int | None = None

    def __post_init__(self) -> None:
        if len(self.values) != COLUMN_COUNT:
            raise InvalidSheetRowError(f"A:AJ에는 {COLUMN_COUNT}개 값이 필요합니다.")
        if self.values[SheetField.SPACER] != "":
            raise InvalidSheetRowError("AF 구분 열은 비워 두어야 합니다.")

    @classmethod
    def from_google_values(cls, row_number: int, values: Sequence[object]) -> SheetRow:
        normalized = tuple(_cell_text(value) for value in values[:COLUMN_COUNT])
        normalized += ("",) * (COLUMN_COUNT - len(normalized))
        normalized_values = list(normalized)
        normalized_values[SheetField.SPACER] = ""
        return cls(tuple(normalized_values), row_number)

    def value(self, field: SheetField) -> str:
        return self.values[field]

    def with_value(self, field: SheetField, value: str) -> SheetRow:
        changed = list(self.values)
        changed[field] = "" if field is SheetField.SPACER else value.strip()
        return SheetRow(tuple(changed), self.row_number)


@dataclass(frozen=True, slots=True)
class RecordDraft:
    receipt_date: date
    values: tuple[str, ...]

    @classmethod
    def create(
        cls,
        receipt_date: date,
        values: Mapping[SheetField, str],
    ) -> RecordDraft:
        row_values = [""] * COLUMN_COUNT
        for field, value in values.items():
            if field not in (
                SheetField.SERVICE_NUMBER,
                SheetField.RECEIPT_MONTH,
                SheetField.SPACER,
            ):
                row_values[field] = value.strip()
        return cls(receipt_date, tuple(row_values))

    def to_sheet_row(self, service_number: str) -> SheetRow:
        row_values = list(self.values)
        row_values[SheetField.SERVICE_NUMBER] = service_number
        row_values[SheetField.RECEIPT_MONTH] = f"{self.receipt_date.month}월"
        row_values[SheetField.SPACER] = ""
        return SheetRow(tuple(row_values))
