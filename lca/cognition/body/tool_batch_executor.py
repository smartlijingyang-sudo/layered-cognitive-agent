"""Close model-emitted tool batches behind one execution seam.

``ToolBatchExecutor`` owns the complete in-process path from a validated list of
``ToolCall`` facts to one aggregate ``Observation``: tool lookup, scheduling-plan
selection, segment validation, SafeExecutor dispatch, and tool-history packaging.
``UseToolOperation`` remains responsible only for action-level validation and the
wire gate, while ``SafeExecutor`` remains the narrow boundary for every world
effect.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import cast

from lca.contracts.atoms.enums import MemoryRecordKind
from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import OBS_RESULT_KIND, OBS_TOOL_RESULTS
from lca.contracts.models.core.decision import Observation, ToolCall
from lca.contracts.models.core.result import ToolExecutionError
from lca.contracts.models.team.role_team import CacheConfig, RetryPolicy
from lca.contracts.protocols import SafeExecutor, Tool, ToolRegistry
from lca.contracts.protocols.act.tool_batch_execution import (
    ToolBatchEntry,
    ToolBatchExecutionMode,
    ToolBatchExecutionPolicy,
    ToolBatchExecutionSegment,
    ToolBatchSegmentPlanningPolicy,
    validate_tool_batch_execution_segments,
)


class ToolBatchExecutor:
    """Execute one validated tool-call batch through the SafeExecutor seam.

    This module deliberately accepts only the three dependencies needed to make
    scheduling decisions and invoke the existing effect gate. It does not inspect
    ``AgentState``, authorize a tool, or emit world effects directly, preserving
    locality for batch scheduling policy replacement.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        safe_executor: SafeExecutor,
        *,
        policy: ToolBatchExecutionPolicy,
    ) -> None:
        self._tool_registry = tool_registry
        self._safe_executor = safe_executor
        self._policy = policy

    async def execute(self, tool_calls: Sequence[ToolCall]) -> Observation:
        """Resolve, schedule, dispatch, and package one non-empty tool batch."""

        resolved = self._resolve_tools(tool_calls)
        if len(resolved) == 1:
            tool_call, tool = resolved[0]
            return self._as_tool_result(
                await self._execute_one(tool_call, tool),
            )

        entries = tuple(
            ToolBatchEntry(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                is_idempotent=tool.is_idempotent,
            )
            for tool_call, tool in resolved
        )
        observations: list[Observation] = []
        for segment in self._select_segments(entries):
            observations.extend(await self._execute_segment(resolved, segment))
        return self._combine_observations(observations, tool_calls)

    def _resolve_tools(self, tool_calls: Sequence[ToolCall]) -> list[tuple[ToolCall, Tool]]:
        """Resolve every tool before dispatching any world effect."""

        resolved: list[tuple[ToolCall, Tool]] = []
        for tool_call in tool_calls:
            tool = self._tool_registry.get(tool_call.tool_name)
            if tool is None:
                raise ToolExecutionError(f"未注册工具: {tool_call.tool_name}")
            resolved.append((tool_call, tool))
        return resolved

    def _select_segments(
        self,
        entries: tuple[ToolBatchEntry, ...],
    ) -> tuple[ToolBatchExecutionSegment, ...]:
        """Select and validate contiguous dispatch segments before execution."""

        if isinstance(self._policy, ToolBatchSegmentPlanningPolicy):
            segmented_policy = cast("ToolBatchSegmentPlanningPolicy", self._policy)
            segments = cast(
                "tuple[ToolBatchExecutionSegment, ...]",
                segmented_policy.select_segments(entries),
            )
        else:
            segments = (
                ToolBatchExecutionSegment(
                    start=0,
                    stop=len(entries),
                    mode=self._policy.select_mode(entries),
                ),
            )
        try:
            validate_tool_batch_execution_segments(segments, entry_count=len(entries))
        except ValueError as exc:
            raise ToolExecutionError(f"invalid tool batch execution plan: {exc}") from exc
        return segments

    async def _execute_segment(
        self,
        resolved: Sequence[tuple[ToolCall, Tool]],
        segment: ToolBatchExecutionSegment,
    ) -> list[Observation]:
        """Dispatch one validated segment through the existing effect seam."""

        selected = resolved[segment.start : segment.stop]
        if segment.mode is ToolBatchExecutionMode.SEQUENTIAL:
            return [await self._execute_one(tool_call, tool) for tool_call, tool in selected]
        if segment.mode is ToolBatchExecutionMode.PARALLEL:
            return list(
                await asyncio.gather(
                    *(self._execute_one(tool_call, tool) for tool_call, tool in selected)
                )
            )
        raise ToolExecutionError(f"unsupported tool batch execution mode: {segment.mode!r}")

    async def _execute_one(self, tool_call: ToolCall, tool: Tool) -> Observation:
        """Execute one resolved call through the common retry and cache policy."""

        return await self._safe_executor.execute(
            tool,
            tool_call.arguments,
            RetryPolicy(),
            CacheConfig(),
            invocation_id=tool_call.call_id or "",
        )

    @staticmethod
    def _as_tool_result(observation: Observation) -> Observation:
        """Mark a singleton result with the same result-kind contract as a batch."""

        extra = dict(observation.extra or {})
        extra.setdefault(OBS_RESULT_KIND, MemoryRecordKind.TOOL_RESULT)
        observation.extra = extra
        return observation

    @staticmethod
    def _combine_observations(
        observations: Sequence[Observation],
        tool_calls: Sequence[ToolCall],
    ) -> Observation:
        """Package ordered batch results for the tool-history projection."""

        all_ok = all(observation.success for observation in observations)
        errors = [
            error
            for error in (
                observation.error for observation in observations if not observation.success
            )
            if error
        ]
        return Observation(
            observation_id=new_id("obs"),
            success=all_ok,
            payload={
                "tool_count": len(observations),
                "all_success": all_ok,
            },
            error="; ".join(errors) if errors else "",
            extra={
                OBS_RESULT_KIND: MemoryRecordKind.TOOL_RESULT,
                OBS_TOOL_RESULTS: [
                    {
                        "call_id": tool_call.call_id,
                        "tool_name": tool_call.tool_name,
                        "observation": observation,
                    }
                    for tool_call, observation in zip(tool_calls, observations, strict=True)
                ],
            },
        )


__all__ = ["ToolBatchExecutor"]
