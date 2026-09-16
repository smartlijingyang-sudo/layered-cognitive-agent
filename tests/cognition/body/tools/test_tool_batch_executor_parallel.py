"""PR-3 (G-19, ADR-0232) — ToolBatchExecutor parallel default for read-only batches.

The PR-3 default policy (``ParallelReadOnlyToolBatchPolicy``) must:

1. PARALLEL when every entry is ``effects="read"`` AND grant carries ``concurrent``.
2. SEQUENTIAL when any entry is ``"write"`` / ``"external"``.
3. SEQUENTIAL when ``concurrent`` is absent even on a read-only batch (C5 monotonic).

The three tests below pin each branch on the actual ``ToolBatchExecutor``
output (a synthetic observation) by counting how many calls overlapped
in time inside the injected ``SafeExecutor``.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from lca.contracts.models.core.execution.decision import Observation, ToolCall
from lca.contracts.models.core.execution.tool import ToolApi, ToolManifest
from lca.contracts.protocols import SafeExecutor, Tool, ToolRegistry
from lca.cognition.body.tools.execution_policy import (
    ParallelReadOnlyToolBatchPolicy,
    ReadOnlyToolBatchEntry,
)
from lca.cognition.body.tools.tool_batch_executor import ToolBatchExecutor


# ----- Test doubles -----------------------------------------------------------


class _Registry:
    def __init__(self, by_name: dict[str, Tool]) -> None:
        self._by_name = by_name

    def get(self, name: str) -> Tool | None:
        return self._by_name.get(name)

    def register(self, tool: Tool) -> None:  # pragma: no cover — discovery seam only
        self._by_name[tool.name] = tool


class _SafeExecutor:
    """Tracks per-call enter / exit timestamps to verify overlap."""

    def __init__(self, *, per_call_latency_s: float = 0.05) -> None:
        self.per_call_latency_s = per_call_latency_s
        self.active = 0
        self.max_active = 0
        self.completed: list[tuple[str, float, float]] = []
        self.lock = asyncio.Lock()

    async def execute(
        self,
        tool: Tool,
        args: dict,
        retry_policy,
        cache_config,
        invocation_id: str = "",
    ) -> Observation:
        async with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            start = time.monotonic()
        try:
            await asyncio.sleep(self.per_call_latency_s)
        finally:
            async with self.lock:
                self.active -= 1
                self.completed.append((invocation_id, start, time.monotonic()))
        return Observation(
            observation_id=f"obs_{invocation_id}",
            success=True,
            payload={"tool": tool.name, "args": args},
            error="",
            latency_ms=int(self.per_call_latency_s * 1000),
        )


def _make_tool(
    name: str, *, effects: str, grant_concurrent: bool, is_idempotent: bool = True
) -> Tool:
    """Build a minimal Tool-shaped test double with the requested metadata."""

    manifest = ToolManifest(
        identifier=name,
        type="builtin",
        api=(
            ToolApi(
                name=name,
                description=f"probe {name}",
                parameters={"type": "object", "properties": {}},
                is_idempotent=is_idempotent,
                effects=effects,  # type: ignore[arg-type]
            ),
        ),
    )

    tool = type(
        f"Tool_{name}",
        (),
        {
            "name": name,
            "description": f"probe {name}",
            "parameters": {"type": "object", "properties": {}},
            "is_idempotent": is_idempotent,
            "default_timeout_s": 5,
            "effect_kind": "ephemeral",
            "manifest": manifest,
            "grant": {"concurrent": grant_concurrent},
        },
    )()
    return tool  # type: ignore[return-value]


def _calls(names: list[str]) -> list[ToolCall]:
    return [
        ToolCall(call_id=f"call_{name}_{i}", tool_name=name, arguments={})
        for i, name in enumerate(names)
    ]


# ----- Tests ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_read_only_with_concurrent_grant_runs_parallel() -> None:
    """5 read-only tools with grant.concurrent=true ⇒ max_active > 1 (overlap)."""

    tools = {
        f"tool_{i}": _make_tool(
            f"tool_{i}", effects="read", grant_concurrent=True
        )
        for i in range(5)
    }
    registry = _Registry(tools)
    safe = _SafeExecutor(per_call_latency_s=0.05)
    executor = ToolBatchExecutor(registry, safe)  # default policy

    observation = await executor.execute(_calls(list(tools)))

    assert observation.success
    assert safe.max_active >= 2, (
        f"expected overlapping execution for read-only concurrent batch, "
        f"got max_active={safe.max_active}"
    )
    assert len(safe.completed) == 5


@pytest.mark.asyncio
async def test_any_write_runs_serial() -> None:
    """A single ``effects="write"`` entry collapses the batch to SEQUENTIAL."""

    tools = {
        "reader_a": _make_tool("reader_a", effects="read", grant_concurrent=True),
        "writer": _make_tool("writer", effects="write", grant_concurrent=True),
        "reader_b": _make_tool("reader_b", effects="read", grant_concurrent=True),
    }
    registry = _Registry(tools)
    safe = _SafeExecutor(per_call_latency_s=0.02)
    executor = ToolBatchExecutor(registry, safe)

    await executor.execute(_calls(["reader_a", "writer", "reader_b"]))

    # SEQUENTIAL ⇒ at most one active at a time.
    assert safe.max_active == 1, (
        f"write entry must force serial; got max_active={safe.max_active}"
    )


@pytest.mark.asyncio
async def test_mixed_external_runs_serial() -> None:
    """External (bash-like) entries force serial execution even with concurrent grant."""

    tools = {
        "external_a": _make_tool("external_a", effects="external", grant_concurrent=True),
        "external_b": _make_tool("external_b", effects="external", grant_concurrent=True),
    }
    registry = _Registry(tools)
    safe = _SafeExecutor(per_call_latency_s=0.02)
    executor = ToolBatchExecutor(registry, safe)

    await executor.execute(_calls(["external_a", "external_b"]))

    assert safe.max_active == 1, (
        f"external entries must run serial; got max_active={safe.max_active}"
    )


@pytest.mark.asyncio
async def test_read_only_without_concurrent_grant_runs_serial() -> None:
    """Even read-only tools without ``grant.concurrent`` stay serial (C5 monotonic)."""

    tools = {
        "r1": _make_tool("r1", effects="read", grant_concurrent=False),
        "r2": _make_tool("r2", effects="read", grant_concurrent=False),
    }
    registry = _Registry(tools)
    safe = _SafeExecutor(per_call_latency_s=0.02)
    executor = ToolBatchExecutor(registry, safe)

    await executor.execute(_calls(["r1", "r2"]))

    assert safe.max_active == 1, (
        f"missing grant.concurrent must force serial; got max_active={safe.max_active}"
    )


def test_default_policy_is_parallel_read_only() -> None:
    """``ToolBatchExecutor()`` (no policy) resolves to ``ParallelReadOnlyToolBatchPolicy``."""

    from lca.cognition.body.tools.execution_policy import default_tool_batch_policy

    assert isinstance(default_tool_batch_policy(), ParallelReadOnlyToolBatchPolicy)


def test_select_mode_with_audit_picks_parallel_for_read_only_concurrent() -> None:
    """Direct unit test of the policy's audit-aware overload."""

    policy = ParallelReadOnlyToolBatchPolicy()
    audited = tuple(
        ReadOnlyToolBatchEntry(
            call_id=f"c{i}",
            tool_name=f"t{i}",
            effects="read",
            grant={"concurrent": True},
        )
        for i in range(3)
    )
    from lca.contracts.protocols.act.tool.batch_execution import ToolBatchExecutionMode

    assert policy.select_mode_with_audit(audited) == ToolBatchExecutionMode.PARALLEL


def test_select_mode_with_audit_falls_back_to_sequential_on_mixed() -> None:
    """Mixed effects in the audit tuple ⇒ SEQUENTIAL."""

    policy = ParallelReadOnlyToolBatchPolicy()
    audited = (
        ReadOnlyToolBatchEntry(call_id="a", tool_name="r", effects="read", grant={"concurrent": True}),
        ReadOnlyToolBatchEntry(call_id="b", tool_name="w", effects="write", grant={"concurrent": True}),
    )
    from lca.contracts.protocols.act.tool.batch_execution import ToolBatchExecutionMode

    assert policy.select_mode_with_audit(audited) == ToolBatchExecutionMode.SEQUENTIAL
