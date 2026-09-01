from __future__ import annotations

import calendar
import re
from datetime import date
from typing import Final, Literal, TypeAlias

FIXED_PROCESSOR: Final = "장진영"
NO_PRODUCTION_MONTH_STATUS: Final = "N/A"
WARRANTY_INSIDE_STATUS: Final = "내"
WARRANTY_OUTSIDE_STATUS: Final = "외"

WarrantyStatus: TypeAlias = Literal["내", "외", "N/A"]

_ONE_YEAR_PREFIXES: Final = ("BT700", "BT200", "BT220")
_BCM_PREFIX: Final = "BCM"
_NA_MARKERS: Final = frozenset({"", "N/A"})
_PRODUCTION_MONTH_PATTERNS: Final = (
    re.compile(r"^(?P<year>\d{2})년(?P<month>\d{1,2})월$"),
    re.compile(r"^(?P<year>\d{4})년\s*(?P<month>\d{1,2})월$"),
    re.compile(r"^(?P<year>\d{4})-(?P<month>\d{1,2})$"),
    re.compile(r"^(?P<year>\d{4})\.(?P<month>\d{1,2})$"),
)


def normalized_model(raw_model: str) -> str:
    return "".join(raw_model.upper().split()).removeprefix("신규")


def is_bcm_model(raw_model: str) -> bool:
    return normalized_model(raw_model).startswith(_BCM_PREFIX)


def warranty_months(raw_model: str) -> int:
    model = normalized_model(raw_model)
    if model.startswith(_ONE_YEAR_PREFIXES):
        return 12
    return 24


def parse_production_month_end(raw_month: str) -> date | None:
    text = raw_month.strip()
    for pattern in _PRODUCTION_MONTH_PATTERNS:
        match = pattern.fullmatch(text)
        if match is not None:
            return _month_end(_full_year(match.group("year")), int(match.group("month")))
    return None


def warranty_status(
    raw_model: str,
    raw_production_month: str,
    received_on: date,
) -> WarrantyStatus | None:
    if raw_production_month.strip().upper() in _NA_MARKERS:
        return NO_PRODUCTION_MONTH_STATUS

    production_month_end = parse_production_month_end(raw_production_month)
    if production_month_end is None:
        return None

    expiry_month_end = _add_months_end(production_month_end, warranty_months(raw_model))
    if received_on < production_month_end:
        return None
    if received_on <= expiry_month_end:
        return WARRANTY_INSIDE_STATUS
    return WARRANTY_OUTSIDE_STATUS


def _full_year(raw_year: str) -> int:
    year = int(raw_year)
    if len(raw_year) == 2:
        return 2000 + year
    return year


def _month_end(year: int, month: int) -> date | None:
    if not 1 <= month <= 12:
        return None
    return date(year, month, calendar.monthrange(year, month)[1])


def _add_months_end(month_end: date, months: int) -> date:
    month_index = month_end.year * 12 + month_end.month - 1 + months
    year = month_index // 12
    month = month_index % 12 + 1
    return date(year, month, calendar.monthrange(year, month)[1])
