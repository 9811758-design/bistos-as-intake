from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, PositiveInt

from .columns import SheetField
from .config import default_config_path
from .records import SheetRow


class RecommendationFeedbackStore(Protocol):
    def counts(self) -> Mapping[str, int]: ...

    def record(self, row: SheetRow) -> None: ...


class FeedbackProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    applied_counts: dict[str, PositiveInt] = Field(default_factory=dict)


def default_feedback_path() -> Path:
    return default_config_path().with_name("recommendation-feedback.json")


def case_feedback_key(row: SheetRow) -> str:
    fields = (
        SheetField.MODEL,
        SheetField.SYMPTOM,
        SheetField.FAILURE_CAUSE,
        SheetField.ACTION,
    )
    normalized = "\x1f".join(row.value(field).strip().casefold() for field in fields)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class LocalRecommendationFeedbackStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def counts(self) -> Mapping[str, int]:
        return dict(self._load().applied_counts)

    def record(self, row: SheetRow) -> None:
        profile = self._load()
        counts = dict(profile.applied_counts)
        key = case_feedback_key(row)
        counts[key] = counts.get(key, 0) + 1
        self._save(FeedbackProfile(applied_counts=counts))

    def _load(self) -> FeedbackProfile:
        if not self._path.is_file():
            return FeedbackProfile()
        return FeedbackProfile.model_validate_json(self._path.read_text(encoding="utf-8"))

    def _save(self, profile: FeedbackProfile) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(f"{self._path.suffix}.tmp")
        temporary.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(self._path)
