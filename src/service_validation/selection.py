from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil

MAX_BATCH_SIZE = 500


@dataclass(slots=True)
class BatchSelection:
    total: int = 0
    page: int = 0
    selected: set[int] = field(default_factory=set)

    @property
    def page_count(self) -> int:
        return max(1, ceil(self.total / MAX_BATCH_SIZE))

    @property
    def page_indices(self) -> range:
        start = self.page * MAX_BATCH_SIZE
        return range(start, min(start + MAX_BATCH_SIZE, self.total))

    def reset(self, total: int) -> None:
        self.total = total
        self.page = 0
        self.selected.clear()

    def move(self, offset: int) -> None:
        self.page = min(max(self.page + offset, 0), self.page_count - 1)
        self.selected.clear()

    def toggle(self, index: int) -> bool:
        if index in self.selected:
            self.selected.remove(index)
            return True
        if len(self.selected) >= MAX_BATCH_SIZE:
            return False
        self.selected.add(index)
        return True

    def select_page(self) -> None:
        self.selected = set(self.page_indices)

    def clear(self) -> None:
        self.selected.clear()
