from __future__ import annotations

from datetime import date

import pytest

from as_intake.policy import (
    FIXED_PROCESSOR,
    normalized_model,
    parse_production_month_end,
    warranty_months,
    warranty_status,
)


def test_fixed_processor_is_jang_jinyoung() -> None:
    # Given: the intake domain has a single fixed processor.
    # When: the policy constant is read.
    # Then: the observable processor value is fixed.
    assert FIXED_PROCESSOR == "장진영"


@pytest.mark.parametrize(
    ("raw_model", "expected_model", "expected_months"),
    [
        ("BT700", "BT700", 12),
        ("신규BT700", "BT700", 12),
        (" 신규 bt700 x ", "BT700X", 12),
        ("BT200L", "BT200L", 12),
        ("BT220C", "BT220C", 12),
        ("BT350L", "BT350L", 24),
        ("BCM350N", "BCM350N", 24),
        ("", "", 24),
        ("ABT700", "ABT700", 24),
    ],
)
def test_warranty_months_when_model_is_normalized(
    raw_model: str,
    expected_model: str,
    expected_months: int,
) -> None:
    # Given: model text may contain casing, spaces, or a leading 신규 marker.
    # When: the model policy is applied.
    # Then: only BT700/BT200/BT220 prefixes receive a 12-month warranty.
    assert normalized_model(raw_model) == expected_model
    assert warranty_months(raw_model) == expected_months


@pytest.mark.parametrize(
    "raw_month",
    ["25년8월", "2025년 8월", "2025-08", "2025.08"],
)
def test_parse_production_month_end_when_supported_format(raw_month: str) -> None:
    # Given: production month text in a supported sheet format.
    # When: it is parsed.
    # Then: the month-end date is returned.
    assert parse_production_month_end(raw_month) == date(2025, 8, 31)


@pytest.mark.parametrize(
    ("raw_month", "expected_status"),
    [("", "N/A"), ("   ", "N/A"), ("N/A", "N/A"), ("n/a", "N/A")],
)
def test_warranty_status_when_production_month_is_blank_or_na(
    raw_month: str,
    expected_status: str,
) -> None:
    # Given: production month text explicitly has no usable value.
    # When: warranty status is calculated.
    # Then: the status is N/A rather than an automatic in/out verdict.
    assert warranty_status("BT350L", raw_month, date(2026, 8, 31)) == expected_status


@pytest.mark.parametrize("raw_month", ["2025년 13월", "2025-00", "2025/08", "August 2025"])
def test_warranty_status_when_production_month_is_malformed(raw_month: str) -> None:
    # Given: production month text is present but malformed.
    # When: warranty status is calculated.
    # Then: no automatic verdict is returned.
    assert warranty_status("BT700", raw_month, date(2026, 1, 1)) is None


@pytest.mark.parametrize(
    ("model", "received_on", "expected_status"),
    [
        ("BT200L", date(2025, 8, 30), None),
        ("BT200L", date(2025, 8, 31), "내"),
        ("BT200L", date(2026, 8, 31), "내"),
        ("BT200L", date(2026, 9, 1), "외"),
        ("BT350L", date(2027, 8, 31), "내"),
        ("BT350L", date(2027, 9, 1), "외"),
    ],
)
def test_warranty_status_when_receipt_date_crosses_boundaries(
    model: str,
    received_on: date,
    expected_status: str | None,
) -> None:
    # Given: a fixed production month and model-specific warranty duration.
    # When: the receipt date is before, on, or after the policy boundaries.
    # Then: the inclusive month-end warranty status is returned.
    assert warranty_status(model, "2025-08", received_on) == expected_status
