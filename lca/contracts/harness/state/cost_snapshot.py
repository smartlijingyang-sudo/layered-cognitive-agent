"""Task-level cost snapshot for Hermes budget governance."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostSnapshot:
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    cost_usd: float = 0.0

    def __post_init__(self) -> None:
        if self.input_tokens < 0 or self.output_tokens < 0 or self.tool_calls < 0:
            raise ValueError("cost counters must be non-negative")
        if self.cost_usd < 0:
            raise ValueError("cost must be non-negative")

    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def within(self, *, max_tokens: int | None = None, max_cost_usd: float | None = None) -> bool:
        return (max_tokens is None or self.total_tokens() <= max_tokens) and (
            max_cost_usd is None or self.cost_usd <= max_cost_usd
        )


__all__ = ["CostSnapshot"]
