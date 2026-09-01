from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from .domain import ServiceRecord, ValidationError


class Result(StrEnum):
    PASS = "Pass"
    NA = "N/A"


@dataclass(frozen=True, slots=True)
class GroupDecision:
    group_id: str
    label: str
    result: Result


@dataclass(frozen=True, slots=True)
class ValidationPlan:
    template_model: str
    decisions: tuple[GroupDecision, ...]
    all_pass: bool = False

    def result_for(self, group_id: str) -> Result:
        for decision in self.decisions:
            if decision.group_id == group_id:
                return decision.result
        if self.all_pass:
            return Result.PASS
        raise ValidationError(f"검증 규칙에 없는 항목입니다: {group_id}")

    @property
    def summary(self) -> str:
        if self.all_pass:
            return "전체 Pass"
        passed = ", ".join(item.label for item in self.decisions if item.result is Result.PASS)
        na = ", ".join(item.label for item in self.decisions if item.result is Result.NA)
        return f"Pass: {passed} | N/A: {na}"


MODEL_ALIASES: Final = {
    "BT350L": "BT350",
    "BT200L": "BT200",
    "BT200V": "BT200",
    "BT200S": "BT200",
    "BT720N": "BT720",
    "BT-770": "BT770",
    "BT770V": "BT770",
}
ALL_PASS_MODELS: Final = frozenset(
    {
        "BT36",
        "BT100",
        "BT200",
        "BT220C",
        "BT250",
        "BT300",
        "BT400",
        "BT410",
        "BT450",
        "BT500",
        "BT550",
        "BT700",
        "신규BT700",
        "BT710",
        "BT720",
    }
)
SUPPORTED_MODELS: Final = ALL_PASS_MODELS | {"BT350", "BT380", "BT740", "BT770", "BT780"}
NON_WORDS: Final = re.compile(r"[^0-9a-z가-힣]+")

BT350_GROUPS: Final = (
    ("main", "CPU/Main B/D", True, ()),
    ("lcd", "LCD Head", True, ()),
    ("led", "LED", True, ()),
    ("key", "Key/Knob/Power", True, ()),
    ("printer", "Print Engine", True, ()),
    ("dop", "DOP", False, ("dop", "도플러")),
    ("uc", "UC", False, ("uc", "자궁수축")),
    ("mark", "Mark", False, ("mark", "마크")),
    ("ast", "AST", False, ("ast",)),
    ("communication", "유/무선 통신", False, ("cms", "통신", "wifi", "bluetooth", "유선", "무선")),
)
BT380_GROUPS: Final = (
    ("main", "Fetal Monitor/Main B/D", True, ()),
    ("lcd", "LCD Head", True, ()),
    ("key", "Knob/Power", True, ()),
    ("printer", "Print Engine", True, ()),
    ("dop", "DOP", False, ("dop", "도플러")),
    ("uc", "UC", False, ("uc", "자궁수축")),
    ("mark", "Mark", False, ("mark", "마크")),
    ("ast", "AST", False, ("ast",)),
    ("communication", "유/무선 통신", False, ("cms", "통신", "wifi", "bluetooth", "유선", "무선")),
    ("spo2", "SpO2", False, ("spo2", "산소포화도")),
    ("ecg", "ECG", False, ("ecg", "심전도")),
    ("nibp", "NiBP", False, ("nibp", "혈압")),
    ("temp", "TEMP", False, ("temp", "온도")),
)
PATIENT_MONITOR_GROUPS: Final = (
    ("main", "Main B/D", True, ()),
    ("lcd_touch", "LCD/Touch", True, ()),
    ("key", "Key/Knob", True, ()),
    ("nibp", "NIBP", False, ("nibp", "혈압", "spo2", "산소포화도", "ecg", "심전도")),
    ("spo2", "SpO2", False, ("nibp", "혈압", "spo2", "산소포화도", "ecg", "심전도")),
    ("ecg", "ECG", False, ("nibp", "혈압", "spo2", "산소포화도", "ecg", "심전도")),
    ("temp", "TEMP", False, ("temp", "온도")),
    ("co2", "CO2", False, ("co2", "etco2")),
    ("ibp", "IBP", False, ("ibp",)),
    ("printer", "Printer", False, ("printer", "프린터", "프린트", "인쇄")),
    ("cms", "CMS", False, ("cms", "통신", "wifi", "bluetooth", "유선", "무선")),
)


def canonical_model(model: str) -> str:
    source = model.strip()
    return MODEL_ALIASES.get(source, source)


def normalize_rule_text(value: str) -> str:
    return NON_WORDS.sub("", value.casefold())


def _matched(raw_text: str, normalized_text: str, keywords: tuple[str, ...]) -> bool:
    for keyword in keywords:
        normalized_keyword = normalize_rule_text(keyword)
        if (
            normalized_keyword.isascii()
            and len(normalized_keyword) <= 4
            and normalized_keyword != "wifi"
        ):
            pattern = rf"(?<![a-z0-9]){re.escape(normalized_keyword)}(?![a-z0-9])"
            if re.search(pattern, raw_text.casefold()) is not None:
                return True
        elif normalized_keyword in normalized_text:
            return True
    return False


def build_validation_plan(record: ServiceRecord) -> ValidationPlan:
    model = canonical_model(record.model)
    if model not in SUPPORTED_MODELS:
        raise ValidationError(f"지원하지 않는 모델입니다: {record.model}")
    if model in ALL_PASS_MODELS:
        return ValidationPlan(template_model=model, decisions=(), all_pass=True)
    raw_text = f"{record.defect_category} {record.service_details}"
    normalized_text = normalize_rule_text(raw_text)
    if model == "BT350":
        groups = BT350_GROUPS
    elif model == "BT380":
        groups = BT380_GROUPS
    else:
        groups = PATIENT_MONITOR_GROUPS
    decisions = tuple(
        GroupDecision(
            group_id=group_id,
            label=label,
            result=(
                Result.PASS
                if always_pass or _matched(raw_text, normalized_text, keywords)
                else Result.NA
            ),
        )
        for group_id, label, always_pass, keywords in groups
    )
    return ValidationPlan(template_model=model, decisions=decisions)
