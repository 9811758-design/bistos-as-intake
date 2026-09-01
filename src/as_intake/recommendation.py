from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Final

from .columns import SheetField
from .feedback import case_feedback_key
from .records import SheetRow

MINIMUM_SCORE: Final = 0.25
RECOMMENDATION_LIMIT: Final = 5
FEEDBACK_BOOST_PER_APPLY: Final = 0.015
MAXIMUM_FEEDBACK_APPLICATIONS: Final = 10
_TEXT_PARTS: Final = re.compile(r"[0-9a-z가-힣]+")
_CANONICAL_REPLACEMENTS: Final = (
    ("켜지지않음", "켜짐불가"),
    ("안켜짐", "켜짐불가"),
    ("잡히지않음", "수신불가"),
    ("안잡힘", "수신불가"),
    ("작동하지않음", "작동불가"),
    ("작동안됨", "작동불가"),
)


@dataclass(frozen=True, slots=True)
class RecommendationQuery:
    year: int
    symptom: str
    cause: str = ""
    model: str = ""


@dataclass(frozen=True, slots=True)
class CaseRecommendation:
    source: SheetRow
    score_percent: int


@dataclass(frozen=True, slots=True)
class RecommendationReport:
    analyzed_rows: int
    recommendations: tuple[CaseRecommendation, ...]


def recommend_cases(
    rows: tuple[SheetRow, ...],
    query: RecommendationQuery,
    feedback_counts: Mapping[str, int] | None = None,
) -> RecommendationReport:
    if not query.symptom.strip() and not query.cause.strip():
        return RecommendationReport(len(rows), ())

    ranked: list[tuple[float, SheetRow]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for row in rows:
        action = row.value(SheetField.ACTION).strip()
        signature = (
            row.value(SheetField.MODEL).strip().casefold(),
            row.value(SheetField.SYMPTOM).strip().casefold(),
            row.value(SheetField.FAILURE_CAUSE).strip().casefold(),
            action.casefold(),
        )
        if not action or signature in seen:
            continue
        seen.add(signature)
        applied_count = (feedback_counts or {}).get(case_feedback_key(row), 0)
        feedback_boost = (
            min(applied_count, MAXIMUM_FEEDBACK_APPLICATIONS) * FEEDBACK_BOOST_PER_APPLY
        )
        score = min(_case_score(row, query) + feedback_boost, 1.0)
        if score >= MINIMUM_SCORE:
            ranked.append((score, row))

    ranked.sort(key=lambda item: item[0], reverse=True)
    recommendations = tuple(
        CaseRecommendation(row, round(score * 100))
        for score, row in ranked[:RECOMMENDATION_LIMIT]
    )
    return RecommendationReport(len(rows), recommendations)


def _case_score(row: SheetRow, query: RecommendationQuery) -> float:
    weighted_scores: list[tuple[float, float]] = []
    if query.symptom.strip():
        weighted_scores.append(
            (0.60, _phrase_similarity(query.symptom, row.value(SheetField.SYMPTOM)))
        )
    if query.cause.strip():
        weighted_scores.append(
            (0.30, _phrase_similarity(query.cause, row.value(SheetField.FAILURE_CAUSE)))
        )
    if query.model.strip():
        model_score = _phrase_similarity(query.model, row.value(SheetField.MODEL))
        weighted_scores.append((0.10, model_score))
    total_weight = sum(weight for weight, _score in weighted_scores)
    return sum(weight * score for weight, score in weighted_scores) / total_weight


def _phrase_similarity(left: str, right: str) -> float:
    normalized_left = _normalized(left)
    normalized_right = _normalized(right)
    if not normalized_left or not normalized_right:
        return 0.0
    sequence = SequenceMatcher(
        None,
        normalized_left,
        normalized_right,
        autojunk=False,
    ).ratio()
    return max(sequence, _dice_similarity(normalized_left, normalized_right))


def _normalized(value: str) -> str:
    normalized = "".join(_TEXT_PARTS.findall(value.casefold()))
    for original, canonical in _CANONICAL_REPLACEMENTS:
        normalized = normalized.replace(original, canonical)
    return normalized


def _dice_similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    size = 2 if min(len(left), len(right)) >= 2 else 1
    left_parts = {left[index : index + size] for index in range(len(left) - size + 1)}
    right_parts = {right[index : index + size] for index in range(len(right) - size + 1)}
    return 2 * len(left_parts & right_parts) / (len(left_parts) + len(right_parts))
