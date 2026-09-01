from __future__ import annotations

from collections.abc import Sequence

from receivables_reconciliation.tracker_models import DepositTask


def filter_tasks_by_depositor_name(
    tasks: Sequence[DepositTask],
    depositor_name: str,
) -> tuple[DepositTask, ...]:
    needle = _normalize(depositor_name)
    if not needle:
        return tuple(tasks)
    return tuple(
        task
        for task in tasks
        if needle in _normalize(task.depositor_name)
    )


def _normalize(text: str) -> str:
    return "".join(text.split()).casefold()
