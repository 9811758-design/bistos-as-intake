from __future__ import annotations

from datetime import date

from as_intake.columns import SheetField
from as_intake.feedback import case_feedback_key
from as_intake.recommendation import RecommendationQuery, recommend_cases
from as_intake.records import RecordDraft, SheetRow


def _case(
    row_number: int,
    number: str,
    *,
    model: str,
    symptom: str,
    cause: str,
    action: str,
) -> SheetRow:
    draft = RecordDraft.create(
        date(2026, 8, 24),
        {
            SheetField.MODEL: model,
            SheetField.SYMPTOM: symptom,
            SheetField.FAILURE_CAUSE: cause,
            SheetField.ACTION: action,
        },
    )
    return SheetRow(draft.to_sheet_row(number).values, row_number)


def test_recommend_cases_returns_the_matching_solution_first() -> None:
    # Given
    power_case = _case(
        5,
        "DS26082401",
        model="BT350L",
        symptom="전원이 켜지지 않음",
        cause="DC JACK 불량",
        action="DC JACK 교체",
    )
    unrelated = _case(
        6,
        "DS26082402",
        model="BT350L",
        symptom="인쇄 흐림",
        cause="프린터 헤드 오염",
        action="프린터 헤드 청소",
    )

    # When
    report = recommend_cases(
        (unrelated, power_case),
        RecommendationQuery(2026, "전원 안켜짐", "DC JACK 불량", "BT350L"),
    )

    # Then
    assert report.analyzed_rows == 2
    assert report.recommendations[0].source == power_case
    assert report.recommendations[0].score_percent >= 70


def test_recommend_cases_prefers_the_same_model_for_equal_symptoms() -> None:
    # Given
    other_model = _case(
        5,
        "DS26082401",
        model="BT740",
        symptom="DOP 신호가 잡히지 않음",
        cause="DOP 케이블 단선",
        action="DOP 케이블 교체",
    )
    same_model = _case(
        6,
        "DS26082402",
        model="BT350L",
        symptom="DOP 신호가 잡히지 않음",
        cause="DOP 케이블 단선",
        action="DOP 케이블 재납땜",
    )

    # When
    report = recommend_cases(
        (other_model, same_model),
        RecommendationQuery(2026, "DOP 신호 안잡힘", model="BT350L"),
    )

    # Then
    assert report.recommendations[0].source == same_model


def test_recommend_cases_excludes_rows_without_an_action_and_exact_duplicates() -> None:
    # Given
    resolved = _case(
        5,
        "DS26082401",
        model="BT350L",
        symptom="화면이 켜지지 않음",
        cause="LCD 케이블 접촉 불량",
        action="LCD 케이블 재결합",
    )
    duplicate = SheetRow(resolved.values, row_number=6)
    unresolved = _case(
        7,
        "DS26082403",
        model="BT350L",
        symptom="화면이 켜지지 않음",
        cause="점검 중",
        action="",
    )

    # When
    report = recommend_cases(
        (resolved, duplicate, unresolved),
        RecommendationQuery(2026, "화면 안켜짐", model="BT350L"),
    )

    # Then
    assert tuple(item.source for item in report.recommendations) == (resolved,)


def test_recommend_cases_returns_empty_when_symptom_and_cause_are_blank() -> None:
    # Given
    resolved = _case(
        5,
        "DS26082401",
        model="BT350L",
        symptom="화면이 켜지지 않음",
        cause="LCD 케이블 접촉 불량",
        action="LCD 케이블 재결합",
    )

    # When
    report = recommend_cases((resolved,), RecommendationQuery(2026, "", model="BT350L"))

    # Then
    assert report.recommendations == ()


def test_recommend_cases_promotes_a_previously_applied_solution() -> None:
    # Given
    first = _case(
        5,
        "DS26082401",
        model="BT350L",
        symptom="전원이 켜지지 않음",
        cause="DC JACK 불량",
        action="DC JACK 교체",
    )
    learned = _case(
        6,
        "DS26082402",
        model="BT350L",
        symptom="전원이 켜지지 않음",
        cause="MAIN PCB 전원부 불량",
        action="MAIN PCB 교체",
    )

    # When
    report = recommend_cases(
        (first, learned),
        RecommendationQuery(2026, "전원 안켜짐", model="BT350L"),
        {case_feedback_key(learned): 3},
    )

    # Then
    assert report.recommendations[0].source == learned
