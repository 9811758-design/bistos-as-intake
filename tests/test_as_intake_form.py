from __future__ import annotations

import tkinter as tk
from datetime import date

from as_intake.columns import SheetField
from as_intake.policy import FIXED_PROCESSOR
from as_intake.records import SheetRow
from as_intake.ui_form import RecordForm
from receivables_reconciliation.main import create_root


def _form(default_receiver: str = "김명훈") -> tuple[tk.Tk, RecordForm]:
    root = create_root()
    root.withdraw()
    form = RecordForm(root, default_receiver)
    root.update_idletasks()
    return root, form


def _legacy_row() -> SheetRow:
    cells = [""] * 36
    cells[SheetField.SERVICE_NUMBER] = "DS26082401"
    cells[SheetField.RECEIVER] = "김명훈"
    cells[SheetField.MODEL] = "BT200L"
    cells[SheetField.PRODUCTION_MONTH] = "2025-08"
    cells[SheetField.WARRANTY] = "외"
    cells[SheetField.PROCESSOR] = "홍석환"
    return SheetRow(tuple(cells), row_number=7)


def test_clear_keeps_receiver_configurable_and_processor_fixed() -> None:
    # Given
    root, form = _form(default_receiver="김명훈")

    # When
    form.clear()

    # Then
    try:
        assert form.fields[SheetField.RECEIVER].get() == "김명훈"
        assert form.fields[SheetField.PROCESSOR].get() == FIXED_PROCESSOR
        assert form.draft().values[SheetField.PROCESSOR] == FIXED_PROCESSOR
    finally:
        root.destroy()


def test_load_preserves_stored_warranty_but_fixes_processor_for_overwrite() -> None:
    # Given
    root, form = _form()
    row = _legacy_row()

    # When
    form.load(row)

    # Then
    try:
        assert form.fields[SheetField.WARRANTY].get() == "외"
        assert form.fields[SheetField.PROCESSOR].get() == FIXED_PROCESSOR
        assert form.sheet_row().value(SheetField.PROCESSOR) == FIXED_PROCESSOR
        assert row.value(SheetField.PROCESSOR) == "홍석환"
    finally:
        root.destroy()


def test_warranty_updates_when_policy_inputs_change_after_load() -> None:
    # Given
    root, form = _form()
    form.load(_legacy_row())

    # When
    form.receipt_date.set(date(2026, 8, 31).isoformat())
    form.set_value(SheetField.MODEL, "신규 BT220C")

    # Then
    try:
        assert form.fields[SheetField.WARRANTY].get() == "내"
    finally:
        root.destroy()


def test_invalid_automatic_warranty_does_not_clear_existing_value() -> None:
    # Given
    root, form = _form()
    form.set_value(SheetField.MODEL, "BT500")
    form.set_value(SheetField.PRODUCTION_MONTH, "2025-08")
    form.receipt_date.set(date(2026, 8, 31).isoformat())
    previous = form.fields[SheetField.WARRANTY].get()

    # When
    form.set_value(SheetField.PRODUCTION_MONTH, "2025-99")

    # Then
    try:
        assert previous == "내"
        assert form.fields[SheetField.WARRANTY].get() == previous
    finally:
        root.destroy()


def test_bcm_model_autofills_serial_and_production_na() -> None:
    root, form = _form()

    try:
        form.set_value(SheetField.SERIAL_NUMBER, "TEMP")
        form.set_value(SheetField.PRODUCTION_MONTH, "2026-01")
        form.set_value(SheetField.MODEL, " bcm350n ")

        assert form.fields[SheetField.SERIAL_NUMBER].get() == "N/A"
        assert form.fields[SheetField.PRODUCTION_MONTH].get() == "N/A"
    finally:
        root.destroy()


def test_sheet_row_preserves_loaded_google_row_number() -> None:
    root, form = _form()

    try:
        form.load(_legacy_row())
        assert form.sheet_row().row_number == 7
    finally:
        root.destroy()
