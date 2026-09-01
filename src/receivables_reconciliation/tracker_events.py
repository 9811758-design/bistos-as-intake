from dataclasses import dataclass
from typing import TypeAlias

from receivables_reconciliation.tracker_models import RefreshResult


@dataclass(frozen=True, slots=True)
class RefreshSuccessEvent:
    result: RefreshResult


@dataclass(frozen=True, slots=True)
class RefreshFailureEvent:
    detail: str


TrackerUiEvent: TypeAlias = RefreshSuccessEvent | RefreshFailureEvent
