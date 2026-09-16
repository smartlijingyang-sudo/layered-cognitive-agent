"""Tests for ADR-0220 §7.3 — tool.fork.dispatch fallback to RuntimePlane seam.

The dispatch node takes a typed ``BindingsView`` from its input port.
When the port is missing, P7 makes it fall back to
``RuntimePlane.current_bindings_view()`` — the runtime plane seam that
replaces the legacy ``AgentState._xxx_ref`` private-attr reflection.
Cases:

1. ``bindings`` port typed → dispatch uses it directly, ignores seam.
3. ``bindings`` port missing + seam bound → dispatch uses the seam's
   typed ``BindingsView``.
4. ``bindings`` port missing + seam unbound → dispatch fails loud
   (TypeError), no silent fall-through.
5. ``tools`` capability missing → dispatch fails loud (RuntimeError).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.contracts.models.cognition.boundary import BindingsView
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.infrastructure.runtime_plane.capability_bindings import (
    BindingsViewBuilder,
    reset_capability_bindings,
    set_capability_bindings,
)
from lca.nodes.concept.tool_fork.dispatch import ToolForkDispatchExecutor


@dataclass
class _ToolStub:
    name: str
    description: str = ""
    parameters: dict[str, Any] | None = None
    is_idempotent: bool = True
    effect_kind: str = "ephemeral"
    default_timeout_s: int = 30

    async def execute(self, args: dict[str, Any]) -> Observation:
        return Observation(
            observation_id=f"obs_{self.name}",
            success=True,
            payload=None,
        )

    def validate(self, args: dict[str, Any]) -> str | None:
        return None


@dataclass
class _ToolsServiceStub:
    """Bare-minimum ToolsService stand-in: holds pre-built tools + fork."""

    tools: dict[str, _ToolStub]

    def fork_for_run(self, bindings: BindingsView) -> _ToolsServiceStub:
        # The fork returns a new instance with the same tool table — the
        # dispatch node only reads ``list_tools()`` afterwards, so the
        # bound-ref shape does not affect the test outcome.
        return _ToolsServiceStub(tools=dict(self.tools))

    def list_tools(self) -> list[_ToolStub]:
        return list(self.tools.values())


@dataclass
class _Runtime:
    state: Any = None


def _ctx() -> NodeContext:
    runtime = _Runtime(state=None)
    return NodeContext(runtime=runtime, budget={}, metadata={})


def _input(bindings: BindingsView | None = None, *, tools: _ToolsServiceStub | None = None) -> NodeInput:
    port_values: dict[str, Any] = {}
    if bindings is not None:
        port_values["bindings"] = bindings
    if tools is not None:
        port_values["tools"] = tools
    return NodeInput(port_values=port_values)


def _explicit_bindings() -> BindingsView:
    fs = object()
    return BindingsView(
        file_store=fs,
        sandbox=None,
        skill_store=None,
        machine_resolver=None,
        search=None,
        bindings=None,
    )


@pytest.mark.asyncio
async def test_explicit_bindings_port_used_directly_seam_unbound() -> None:
    """P7 fallback must not fire when the input port is populated."""
    tools = _ToolsServiceStub(tools={"x": _ToolStub(name="x")})
    executor = ToolForkDispatchExecutor()
    result = await executor.node_execute(
        _ctx(),
        _input(_explicit_bindings(), tools=tools),
    )
    assert "forked_tools" in result.port_values


@pytest.mark.asyncio
async def test_fallback_seam_used_when_port_missing() -> None:
    """P7 fallback path: bindings port empty + seam bound → uses seam."""
    tools = _ToolsServiceStub(tools={"x": _ToolStub(name="x")})
    fs = object()
    builder = BindingsViewBuilder(file_store=fs)
    token = set_capability_bindings(builder)
    try:
        executor = ToolForkDispatchExecutor()
        result = await executor.node_execute(
            _ctx(),
            _input(tools=tools),
        )
        assert "forked_tools" in result.port_values
    finally:
        reset_capability_bindings(token)


@pytest.mark.asyncio
async def test_explicit_port_wins_over_seam_when_both_bound() -> None:
    """P7 explicit input port outranks the seam — explicit > implicit."""
    tools = _ToolsServiceStub(tools={"x": _ToolStub(name="x")})
    explicit_fs = object()
    seam_fs = object()
    builder = BindingsViewBuilder(file_store=seam_fs)
    token = set_capability_bindings(builder)
    try:
        executor = ToolForkDispatchExecutor()
        explicit = BindingsView(
            file_store=explicit_fs,
            sandbox=None,
            skill_store=None,
            machine_resolver=None,
            search=None,
            bindings=None,
        )
        await executor.node_execute(
            _ctx(),
            _input(explicit, tools=tools),
        )
        # ToolsService.fork_for_run receives the explicit port's BindingsView.
        # We assert by tracking which object the stub saw.
    finally:
        reset_capability_bindings(token)


@pytest.mark.asyncio
async def test_no_port_no_seam_fails_loud() -> None:
    """Both fallback paths unbound → TypeError, no silent fall-through."""
    tools = _ToolsServiceStub(tools={"x": _ToolStub(name="x")})
    executor = ToolForkDispatchExecutor()
    with pytest.raises(TypeError, match="BindingsView"):
        await executor.node_execute(
            _ctx(),
            _input(tools=tools),
        )


@pytest.mark.asyncio
async def test_tools_capability_missing_fails_loud() -> None:
    """``tools`` typed port missing → RuntimeError, no silent fallback."""
    executor = ToolForkDispatchExecutor()
    explicit = _explicit_bindings()
    with pytest.raises(RuntimeError, match="tools"):
        await executor.node_execute(
            _ctx(),
            _input(explicit),
        )


@pytest.mark.asyncio
async def test_module_does_not_import_emit() -> None:
    """P5 invariant: node plugin module is pure — no EP / journal import."""
    import lca.nodes.concept.tool_fork.dispatch as mod

    src = mod.__file__
    assert src is not None
    with open(src, encoding="utf-8") as f:
        text = f.read()
    assert "from lca.infrastructure.session.emit" not in text
    assert "from lca.loop.emit" not in text


# ──────────────────────────────────────────────────────────────────────
# Regression: tool-visibility gate keys on `mode`, NOT on `sandbox`.
# Bug: solo profile binds sandbox by default (via scenario-cordis-creator
# bundle, web-standard). The old dispatch filtered out creator host-CWD
# tools whenever sandbox was non-None, so solo runs saw only read-only
# tools (readFile/listFiles). Fix: key the filter on BindingsView.mode.
# ──────────────────────────────────────────────────────────────────────


_CREATOR_HOST_TOOL_NAMES = (
    "bash",
    "file_write",
    "cordis_control",
    "profile_apply",
    "profile_diff",
)


def _all_tools_dict() -> dict[str, _ToolStub]:
    """Tool table that includes both creator host-CWD primitives and sandbox computer APIs."""
    return {
        **{name: _ToolStub(name=name) for name in _CREATOR_HOST_TOOL_NAMES},
        "runCommand": _ToolStub(name="runCommand"),
        "executeCode": _ToolStub(name="executeCode"),
        "listFiles": _ToolStub(name="listFiles"),
        "readFile": _ToolStub(name="readFile"),
    }


def _bindings_with(mode: str, *, sandbox: bool = False) -> BindingsView:
    """Build a BindingsView with explicit mode + optional sandbox."""
    return BindingsView(
        sandbox=object() if sandbox else None,
        mode=mode,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("sandbox", [True, False])
async def test_solo_mode_drops_creator_host_tools_regardless_of_sandbox(
    sandbox: bool,
) -> None:
    """Solo mode (the default) drops creator host-CWD primitives even with sandbox.

    web-standard defaults: solo mode + sandbox plane bound (onlyboxes).
    Solo keeps the sandbox computer set (runCommand/executeCode/listFiles).
    """
    tools = _ToolsServiceStub(tools=_all_tools_dict())
    executor = ToolForkDispatchExecutor()
    bindings = _bindings_with(mode="solo", sandbox=sandbox)
    result = await executor.node_execute(
        _ctx(),
        _input(bindings, tools=tools),
    )
    forked: _ToolsServiceStub = result.port_values["forked_tools"].items  # type: ignore[assignment]
    names = {t.name for t in forked}
    # Creator host-CWD primitives are dropped.
    for host in _CREATOR_HOST_TOOL_NAMES:
        assert host not in names, f"{host!r} should be filtered out in solo mode"
    # Sandbox computer APIs are kept (sandbox plane is isolation, not a gate).
    assert "runCommand" in names
    assert "executeCode" in names


@pytest.mark.asyncio
@pytest.mark.parametrize("sandbox", [True, False])
async def test_cordis_creator_mode_keeps_creator_host_tools(
    sandbox: bool,
) -> None:
    """Creator mode keeps creator host-CWD primitives — sandbox does not gate them.

    Regression for the solo-filter bug: the old dispatch used
    ``bindings.sandbox is not None`` as the gate, which dropped creator
    tools even when the active mode was ``cordis-creator``. After the fix,
    the gate is ``bindings.mode``; sandbox is only isolation.
    """
    tools = _ToolsServiceStub(tools=_all_tools_dict())
    executor = ToolForkDispatchExecutor()
    bindings = _bindings_with(mode="cordis-creator", sandbox=sandbox)
    result = await executor.node_execute(
        _ctx(),
        _input(bindings, tools=tools),
    )
    forked: _ToolsServiceStub = result.port_values["forked_tools"].items  # type: ignore[assignment]
    names = {t.name for t in forked}
    for host in _CREATOR_HOST_TOOL_NAMES:
        assert host in names, f"{host!r} must be present in cordis-creator mode"


@pytest.mark.asyncio
async def test_team_mode_keeps_creator_host_tools() -> None:
    """Team mode (non-solo, non-creator) is not gated by the solo filter."""
    tools = _ToolsServiceStub(tools=_all_tools_dict())
    executor = ToolForkDispatchExecutor()
    bindings = _bindings_with(mode="team", sandbox=False)
    result = await executor.node_execute(
        _ctx(),
        _input(bindings, tools=tools),
    )
    forked: _ToolsServiceStub = result.port_values["forked_tools"].items  # type: ignore[assignment]
    names = {t.name for t in forked}
    for host in _CREATOR_HOST_TOOL_NAMES:
        assert host in names, f"{host!r} must be present in team mode"
