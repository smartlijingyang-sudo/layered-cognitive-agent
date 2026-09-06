"""Cooperative tool timeout guard — DSH timeout-policy analog (ADR-0197)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import FAILURE_KIND, FAILURE_KIND_EXECUTION
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.protocols.act.tool.guards import ExecuteWrapper, ToolGuardContribution
from lca.contracts.protocols.act.tool.pipeline import ToolExecutionContext
from lca.contracts.protocols.runtime.infra.infra import Tool

_TOOL_TIMEOUT = "TOOL_TIMEOUT"


class ToolTimeoutGuard(ToolGuardContribution):
    """Arm asyncio deadline from ``Tool.default_timeout_s`` (cooperative)."""

    def __init__(self, *, enabled: bool = True) -> None:
        self._enabled = enabled

    @property
    def id(self) -> str:
        return "guard.tool-timeout"

    def wrap_execute(self, inner: ExecuteWrapper) -> ExecuteWrapper:
        if not self._enabled:
            return inner

        async def wrapper(
            tool: Tool,
            args: dict[str, object],
            run: Callable[[], Awaitable[Observation]],
        ) -> Observation:
            timeout_s = max(1, tool.default_timeout_s)
            try:
                return await asyncio.wait_for(run(), timeout=timeout_s)
            except TimeoutError:
                return Observation(
                    observation_id=new_id("obs"),
                    success=False,
                    payload=None,
                    error=f"工具调用超时（>{timeout_s}s）",
                    extra={
                        FAILURE_KIND: FAILURE_KIND_EXECUTION,
                        "error_code": _TOOL_TIMEOUT,
                        "timeout_s": timeout_s,
                        "tool_name": tool.name,
                    },
                )

        return wrapper

    def transform_result(
        self, ctx: ToolExecutionContext, observation: Observation
    ) -> Observation:
        return observation


__all__ = ["_TOOL_TIMEOUT", "ToolTimeoutGuard"]
