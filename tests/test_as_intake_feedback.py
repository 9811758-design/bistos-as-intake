from __future__ import annotations

from datetime import date
from pathlib import Path

from as_intake.columns import SheetField
from as_intake.feedback import LocalRecommendationFeedbackStore, case_feedback_key
from as_intake.records import RecordDraft, SheetRow


def _resolved_case() -> SheetRow:
    draft = RecordDraft.create(
        date(2026, 8, 25),
        {
            SheetField.MODEL: "BT350L",
            SheetField.SYMPTOM: "전원이 켜지지 않음",
            SheetField.FAILURE_CAUSE: "DC JACK 불량",
            SheetField.ACTION: "DC JACK 교체",
        },
    )
    return draft.to_sheet_row("DS26082501")


def test_feedback_store_persists_applied_case_count(tmp_path: Path) -> None:
    # Given
    path = tmp_path / "recommendation-feedback.json"
    case = _resolved_case()

    # When
    LocalRecommendationFeedbackStore(path).record(case)
    counts = LocalRecommendationFeedbackStore(path).counts()

    # Then
    assert counts[case_feedback_key(case)] == 1
    assert "BT350L" not in path.read_text(encoding="utf-8")


def test_feedback_store_increments_the_same_solution(tmp_path: Path) -> None:
    # Given
    path = tmp_path / "recommendation-feedback.json"
    case = _resolved_case()
    store = LocalRecommendationFeedbackStore(path)

    # When
    store.record(case)
    store.record(case)

    # Then
    assert store.counts()[case_feedback_key(case)] == 2
