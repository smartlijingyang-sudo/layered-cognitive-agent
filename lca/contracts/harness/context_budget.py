"""Deterministic context budgeting for long-horizon Agent runs."""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.models.core.perception import ContextItem


@dataclass(frozen=True)
class ContextBudgeter:
    max_chars: int

    def __post_init__(self) -> None:
        if self.max_chars <= 0:
            raise ValueError("context budget must be positive")

    def trim(self, items: tuple[ContextItem, ...]) -> tuple[ContextItem, ...]:
        selected: list[ContextItem] = []
        used = 0
        for item in items:
            size = len(str(item.payload))
            if used + size > self.max_chars:
                continue
            selected.append(item)
            used += size
        return tuple(selected)


__all__ = ["ContextBudgeter"]
