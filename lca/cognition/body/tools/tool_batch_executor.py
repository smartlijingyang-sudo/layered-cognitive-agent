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
import re
from collections.abc import Sequence

from lca.contracts.atoms.enums.enums import MemoryRecordKind
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import OBS_RESULT_KIND, OBS_TOOL_RESULTS
from lca.contracts.models.core.execution.decision import Observation, ToolCall
from lca.contracts.models.core.execution.result import ToolExecutionError
from lca.contracts.models.team.role.team import CacheConfig, RetryPolicy
from lca.contracts.protocols import SafeExecutor, Tool, ToolRegistry
from lca.contracts.protocols.act.tool.batch_execution import (
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
        policy: ToolBatchExecutionPolicy | None = None,
    ) -> None:
        # PR-3 (G-19, ADR-0232): default policy is the parallel-read-only
        # strategy.  Callers may still inject an explicit policy (tests,
        # specialised bundles); the ``None`` path resolves to the new
        # default rather than the pre-PR-3 ``SequentialToolBatchExecutionPolicy``.
        from lca.cognition.body.tools.execution_policy import (
            default_tool_batch_policy,
        )

        self._tool_registry = tool_registry
        self._safe_executor = safe_executor
        self._policy = policy if policy is not None else default_tool_batch_policy()

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
        # PR-3 (G-19, ADR-0232): if the policy exposes the audit-aware
        # ``select_mode_with_audit`` overload (new in PR-3), prefer it so
        # the parallel default can see per-entry ``effects`` and grant
        # metadata.  Fall back to the protocol-level ``select_mode`` for
        # any pre-existing policy that has not been upgraded.
        selected_mode = self._select_mode_with_optional_audit(entries, resolved)
        observations: list[Observation] = []
        for segment in self._select_segments(entries, override_mode=selected_mode):
            observations.extend(await self._execute_segment(resolved, segment))
        return self._combine_observations(observations, tool_calls)

    def _select_mode_with_optional_audit(
        self,
        entries: tuple[ToolBatchEntry, ...],
        resolved: Sequence[tuple[ToolCall, Tool]],
    ) -> ToolBatchExecutionMode | None:
        """Resolve the batch mode, preferring the audit-aware overload when present.

        Returns ``None`` when the policy only exposes the protocol-level
        ``select_mode`` (no audit channel); the caller then defers to
        ``_select_segments`` which uses that legacy path.
        """

        select_with_audit = getattr(self._policy, "select_mode_with_audit", None)
        if select_with_audit is None:
            return None
        from lca.cognition.body.tools.execution_policy import (
            ReadOnlyToolBatchEntry,
        )

        audited = tuple(
            ReadOnlyToolBatchEntry(
                call_id=entry.call_id,
                tool_name=entry.tool_name,
                effects=_resolve_tool_effects(tool),
                grant=_resolve_tool_grant(tool),
            )
            for entry, (_call, tool) in zip(entries, resolved, strict=True)
        )
        return select_with_audit(audited)

    def _resolve_tools(self, tool_calls: Sequence[ToolCall]) -> list[tuple[ToolCall, Tool]]:
        """Resolve every tool before dispatching any world effect.

        Includes a tolerant fallback: when the LLM emits a snake_case name
        like ``export_file`` while the registered name is camelCase
        (``exportFile``), fall back to a normalised lookup. LLM name
        hallucination across case styles is observed in production; this
        keeps the wire-name stable (we still log the canonical tool name)
        without surfacing a noisy ``未注册工具`` error.
        """

        resolved: list[tuple[ToolCall, Tool]] = []
        for tool_call in tool_calls:
            tool = self._tool_registry.get(tool_call.tool_name)
            if tool is None:
                tool = self._tool_registry.get(_canonicalise_tool_name(tool_call.tool_name))
            if tool is None:
                raise ToolExecutionError(f"未注册工具: {tool_call.tool_name}")
            resolved.append((tool_call, tool))
        return resolved

    def _select_segments(
        self,
        entries: tuple[ToolBatchEntry, ...],
        *,
        override_mode: ToolBatchExecutionMode | None = None,
    ) -> tuple[ToolBatchExecutionSegment, ...]:
        """Select and validate contiguous dispatch segments before execution.

        ``override_mode`` is the audit-aware mode resolved by
        ``_select_mode_with_optional_audit``; when present it replaces
        the protocol-level ``select_mode`` call so PR-3's
        ``ParallelReadOnlyToolBatchPolicy`` can gate on per-entry
        ``effects`` / ``grant`` metadata.  When ``None`` the legacy
        path is used.
        """

        if isinstance(self._policy, ToolBatchSegmentPlanningPolicy):
            segments = self._policy.select_segments(entries)
        else:
            mode = (
                override_mode
                if override_mode is not None
                else self._policy.select_mode(entries)
            )
            segments = (
                ToolBatchExecutionSegment(
                    start=0,
                    stop=len(entries),
                    mode=mode,
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


_CAMEL_BOUNDARY_RE = re.compile(r"(?<!^)(?=[A-Z])")


def _canonicalise_tool_name(name: str) -> str:
    """Return a snake/camel-equivalent candidate for a tool name.

    Examples:
      ``export_file`` → ``exportFile``
      ``ExportFile`` → ``export_file``
      ``run_command`` → ``runCommand``
      ``execute_code`` → ``executeCode``

    The lookup is purely string-level: the LLM tends to emit either
    snake_case or camelCase depending on prompt context, but the
    registry keeps one canonical form (camelCase, per LobeHub wire
    convention — see ``lca/infrastructure/tools/lca_computer/types.py``).
    """
    if not name:
        return name
    if "_" in name:
        # snake_case → camelCase: export_file → exportFile
        parts = name.split("_")
        return parts[0] + "".join(p.capitalize() for p in parts[1:] if p)
    if any(ch.isupper() for ch in name[1:]):
        # camelCase → snake_case: exportFile → export_file
        return _CAMEL_BOUNDARY_RE.sub("_", name).lower()
    return name


def _resolve_tool_effects(tool: Tool) -> str:
    """Return the declared ``effects`` value for ``tool``, defaulting to ``external``.

    The lookup prefers the manifest's first ``ToolApi.effects`` value
    because most tools expose exactly one API; for multi-API tools
    the first declared effect wins (the audit must opt the whole tool
    in to a non-default value at registration time, see
    ``lca/contracts/cognition/body/tools/registry.py``).
    """

    manifest = getattr(tool, "manifest", None)
    if manifest is not None and getattr(manifest, "api", None):
        effects = getattr(manifest.api[0], "effects", "external")
        if effects in ("read", "write", "external"):
            return effects
    # Fallback: tools without a manifest (legacy Protocol-only shape)
    # are conservatively treated as ``external`` so the parallel
    # default refuses to overlap an unaudited tool.
    return "external"


def _resolve_tool_grant(tool: Tool) -> dict[str, object]:
    """Return the per-tool grant map used to check ``concurrent``.

    The Body owns the authoritative capability grant; this helper only
    surfaces the static ``tool.grant`` map (defaults to ``{}``) so the
    policy's ``grant.concurrent`` check degrades to ``False`` for
    tools that have not been wired with a grant channel.  This keeps
    the parallel default safe-by-default: any tool whose grant is not
    explicitly granted ``concurrent`` falls back to sequential.
    """

    grant = getattr(tool, "grant", None)
    if isinstance(grant, dict):
        return grant
    return {}
