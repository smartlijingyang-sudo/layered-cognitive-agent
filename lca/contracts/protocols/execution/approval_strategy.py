from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from lca.contracts.models.core.execution.approval import ApprovalRequirement
from lca.contracts.models.core.execution.decision import ToolCall
from lca.contracts.models.core.state.plane import PlaneRef


class ApprovalStrategy(Protocol):
    """Protocol for single-purpose approval policy evaluation strategies."""

    @property
    def strategy_name(self) -> str: ...

    def evaluate(
        self,
        tool_calls: Sequence[ToolCall],
        plane: PlaneRef | None = None,
    ) -> ApprovalRequirement | None:
        """Evaluate tool calls sequence.

        Returns ApprovalRequirement if this strategy triggers, or None to yield
        to the next strategy in the chain of responsibility.
        """
        ...
