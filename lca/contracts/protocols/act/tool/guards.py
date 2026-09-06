"""Tool guard contributions — act-plane hooks mirroring DSH guard plugins (ADR-0197)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.protocols.act.tool.pipeline import ToolExecutionContext
from lca.contracts.protocols.runtime.infra.infra import Tool

ExecuteWrapper = Callable[
    [Tool, dict[str, object], Callable[[], Awaitable[Observation]]],
    Awaitable[Observation],
]

PostExecuteTransform = Callable[[ToolExecutionContext, Observation], Observation]


class ToolGuardContribution(Protocol):
    """One act-plane guard plugin contribution."""

    @property
    def id(self) -> str: ...

    def wrap_execute(self, inner: ExecuteWrapper) -> ExecuteWrapper: ...

    def transform_result(
        self, ctx: ToolExecutionContext, observation: Observation
    ) -> Observation: ...


__all__ = ["ExecuteWrapper", "PostExecuteTransform", "ToolGuardContribution"]
