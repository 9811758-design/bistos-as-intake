from dataclasses import replace
from datetime import date

import pytest

from service_validation.domain import ServiceRecord, ValidationError, classify_customer
from service_validation.validation_rules import Result, build_validation_plan


def _record(model: str, category: str = "", symptom: str = "") -> ServiceRecord:
    return ServiceRecord(
        service_number="DS26070601",
        receipt_date=date(2026, 7, 6),
        receiver="장진영",
        requester="국제메디칼",
        hospital="미즈피아병원",
        customer=classify_customer("국제메디칼", "미즈피아병원"),
        model=model,
        defect_category=category,
        service_details=symptom,
        processing_details="수리 완료",
        completion_date=date(2026, 7, 6),
        processor="장진영",
    )


def test_bt380_screen_issue_keeps_base_pass_and_optional_na() -> None:
    plan = build_validation_plan(_record("BT380", "화면불량", "화면이 나오지 않음"))

    assert plan.template_model == "BT380"
    assert plan.result_for("main") is Result.PASS
    assert plan.result_for("lcd") is Result.PASS
    assert plan.result_for("printer") is Result.PASS
    assert plan.result_for("dop") is Result.NA
    assert plan.result_for("temp") is Result.NA


def test_bt380_dop_issue_selects_only_related_optional_group() -> None:
    plan = build_validation_plan(_record("BT380", "DOP 불량", "도플러 감도 저하"))

    assert plan.result_for("dop") is Result.PASS
    assert plan.result_for("uc") is Result.NA
    assert plan.result_for("ecg") is Result.NA


def test_touch_text_does_not_false_match_uc_acronym() -> None:
    plan = build_validation_plan(_record("BT380", "화면", "Touch 동작 확인"))

    assert plan.result_for("uc") is Result.NA


def test_bt350_alias_uses_bt350_rules_without_changing_source_model() -> None:
    record = _record("BT350L", "UC불량", "자궁수축 값 이상")
    plan = build_validation_plan(record)

    assert record.model == "BT350L"
    assert plan.template_model == "BT350"
    assert plan.result_for("uc") is Result.PASS
    assert plan.result_for("dop") is Result.NA


@pytest.mark.parametrize("model", ["BT740", "BT-770", "BT770V", "BT780"])
def test_patient_monitor_vitals_are_linked(model: str) -> None:
    plan = build_validation_plan(_record(model, "SpO2 불량", "산소포화도 측정 안됨"))

    assert plan.result_for("nibp") is Result.PASS
    assert plan.result_for("spo2") is Result.PASS
    assert plan.result_for("ecg") is Result.PASS
    assert plan.result_for("temp") is Result.NA
    assert plan.result_for("cms") is Result.NA


def test_patient_monitor_cms_requires_related_text() -> None:
    base = _record("BT740", "통신 불량", "CMS 연결 안됨")

    assert build_validation_plan(base).result_for("cms") is Result.PASS
    unrelated = replace(base, defect_category="화면", service_details="터치")
    assert build_validation_plan(unrelated).result_for("cms") is Result.NA


@pytest.mark.parametrize(
    "model",
    [
        "BT36",
        "BT100",
        "BT200L",
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
        "BT720N",
    ],
)
def test_always_inspected_models_use_all_pass(model: str) -> None:
    plan = build_validation_plan(_record(model))

    assert plan.all_pass


def test_unknown_model_is_rejected() -> None:
    with pytest.raises(ValidationError, match="지원하지 않는 모델"):
        build_validation_plan(_record("BCM350"))
