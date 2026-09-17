"""Unit tests for the ``think.history.assemble`` node.

The hand-written :class:`HistoryDeriveExecutor` in
:mod:`lca.nodes.think.history.assemble` wraps the writer→ModelVisibleRequest
logic as a ``NodeExecutor``-shaped dataclass and is registered under the
composite key ``phase:think::history.derive`` via the cordis ``@plugin(...)``
carrier — matches the ``factory: history.derive`` node declared in
``bundles/concept/history_assemble.yaml``.

delete-when: N/A — typed-boundary adapter required by the inner graph bundle.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any
from unittest.mock import MagicMock

import pytest

from lca.contracts.models.cognition.boundary import ForkedTools
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.contracts.protocols.session.model.context import ModelVisibleRequest
from lca.nodes.think.history import assemble as history_module
from lca.nodes.think.history.assemble import HistoryDeriveExecutor

# ── Minimal tool stub (Tool is runtime_checkable Protocol + Pydantic is_instance) ──


def _make_stub_tool(name: str) -> type:
    """Build a Tool Protocol-conforming class with ClassVars + async execute.

    Tool Protocol declares ``name/description/parameters`` as ClassVar;
    Pydantic ``is_instance_of`` checks Protocol via ``isinstance`` which
    honors ClassVar as class attributes. Instance attributes are NOT seen.
    """

    async def _execute(self, args):  # pragma: no cover - stub
        return None

    def _validate(self, args):  # pragma: no cover - stub
        return None

    return type(
        f"_StubTool_{name}",
        (),
        {
            "name": name,
            "description": f"description for {name}",
            "parameters": {"type": "object", "properties": {}},
            "execute": _execute,
            "validate": _validate,
        },
    )


# ── Minimal fixtures ────────────────────────────────────────────


@dataclass
class _StoredHeader:
    system: str | None


class _FakeWriter:
    """Minimal ``RunSessionWriterProtocol`` stand-in."""

    def __init__(self, messages: list[dict[str, Any]], system: str | None = None) -> None:
        self._messages = messages
        self._header = _StoredHeader(system=system)

    def derive_messages(self) -> list[dict[str, Any]]:
        return list(self._messages)

    def request_header(self) -> _StoredHeader | None:
        return self._header


def _make_state() -> AgentState:
    """Construct a real ``AgentState`` so the isinstance gate passes."""
    return AgentState(
        trace_id="trace-test",
        task="",
        budget=Budget(),
    )


def _node_context(runtime: dict[str, Any] | None = None) -> NodeContext:
    return NodeContext(
        runtime=runtime if runtime is not None else {},
        budget={},
        metadata={},
    )


# ── Tests ────────────────────────────────────────────────────────


def test_executor_declares_history_derive_semantic_name_in_think_region() -> None:
    """``semantic_name`` must match ``factory: history.derive`` in the bundle.

    ``declared_inputs`` grew from ``(state, writer)`` to
    ``(state, writer, forked_tools, turn_render)`` — ``forked_tools`` was
    added by PR-3.8.borrow-tools-wire (spec §E) and ``turn_render`` is the
    spec §G system-prompt seam, named after its producer
    (``think.reason.render``). Both ports are optional in the wiring seam —
    see ``test_node_execute_tools_empty_when_forked_tools_missing`` and
    ``test_system_empty_when_no_header_no_render_no_role_profile``.
    """
    assert HistoryDeriveExecutor().semantic_name == "history.derive"
    assert HistoryDeriveExecutor().region == "think"
    assert HistoryDeriveExecutor().declared_inputs == (
        "state",
        "writer",
        "forked_tools",
        "turn_render",
    )
    assert HistoryDeriveExecutor().declared_outputs == ("model_visible_request",)


def test_plugin_module_exposes_setup_carrier() -> None:
    """The plugin module exposes a ``@plugin(...)`` carrier at module level."""
    module = import_module("lca.nodes.think.history")
    assert hasattr(module, "setup")
    # cordis carrier has a ``.setup`` attribute that the @plugin
    # decorator names the inner fn.
    assert hasattr(module.setup, "setup")
    assert callable(module.setup.setup)


async def test_node_execute_returns_model_visible_request_with_orphan_dropped_messages() -> None:
    """``node_execute`` calls the wrapped logic and returns the typed request."""
    executor = HistoryDeriveExecutor()
    writer = _FakeWriter(
        messages=[
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ],
        system="You are a helpful assistant.",
    )
    state = _make_state()
    out = await executor.node_execute(
        context=_node_context(),
        input=NodeInput(port_values={"state": state, "writer": writer}),
    )

    assert set(out.port_values) == {"model_visible_request"}
    request = out.port_values["model_visible_request"]
    assert isinstance(request, ModelVisibleRequest)
    assert request.messages == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    assert request.system == "You are a helpful assistant."
    assert request.tools == ()


async def test_node_execute_falls_back_to_context_runtime_when_writer_missing_from_ports() -> None:
    """Writer in ``context.runtime`` is honored as fallback when port_values lacks it."""
    executor = HistoryDeriveExecutor()
    writer = _FakeWriter(messages=[{"role": "user", "content": "q"}])
    state = _make_state()
    out = await executor.node_execute(
        context=_node_context(runtime={"state": state, "writer": writer}),
        input=NodeInput(port_values={}),
    )

    request = out.port_values["model_visible_request"]
    assert isinstance(request, ModelVisibleRequest)
    assert request.messages == [{"role": "user", "content": "q"}]
    assert request.system == ""


async def test_node_execute_missing_writer_raises_type_error() -> None:
    """``writer`` is required; missing on both ports and runtime → TypeError."""
    executor = HistoryDeriveExecutor()
    state = _make_state()
    with pytest.raises(TypeError, match="'writer' port must be"):
        await executor.node_execute(
            context=_node_context(runtime={"state": state}),
            input=NodeInput(port_values={"state": state}),
        )


async def test_node_execute_wrong_state_type_propagates_to_user_fn() -> None:
    """``state`` is passed through to the wrapped logic unchanged.

    The hand-written executor does not perform per-port isinstance
    guards; the user fn's type signature remains the typed-boundary
    contract. A wrong-type ``state`` is passed through verbatim so
    downstream decides the failure mode.
    """
    executor = HistoryDeriveExecutor()
    writer = _FakeWriter(messages=[])
    out = await executor.node_execute(
        context=_node_context(),
        input=NodeInput(port_values={"state": "not-a-state", "writer": writer}),
    )
    request = out.port_values["model_visible_request"]
    assert isinstance(request, ModelVisibleRequest)
    assert request.messages == []


async def test_setup_registers_executor_under_composite_key() -> None:
    """``setup.setup()`` calls ``ctx.provide('think::history.derive', executor)``."""
    captured: dict[str, Any] = {}
    ctx = MagicMock()
    ctx.provide = MagicMock(side_effect=lambda key, value: captured.__setitem__(key, value))

    await history_module.setup.setup(ctx, config=None)

    assert list(captured) == ["think::history.derive"]
    assert isinstance(captured["think::history.derive"], HistoryDeriveExecutor)


# ── ForkedTools → ModelVisibleRequest.tools (spec §E) ────────────


def _stub_tool(name: str):
    return _make_stub_tool(name)()


async def test_node_execute_populates_tools_from_forked_tools_port() -> None:
    """ForkedTools 透传到 ``ModelVisibleRequest.tools``(spec §E)。

    修复点:history.derive 之前 ``tools=()`` 写死,导致 LLM 看不到任何
    tool schema(spec §J test_run_with_tool_use 失败的原因)。

    用 ``model_construct`` 绕过 Pydantic ``is_instance_of`` Protocol 校验
    —— 真实生产路径上 ForkedTools 由 tool_fork.dispatch 构造,其 items
    来自 ToolsService.fork_for_run() 返回的真实 Tool 实现,本测试只关心
    history.derive 是否正确读 ForkedTools.items 并序列化为 tool spec。
    """
    executor = HistoryDeriveExecutor()
    writer = _FakeWriter(messages=[{"role": "user", "content": "q"}])
    stub_run = _make_stub_tool("runCommand")()
    stub_exec = _make_stub_tool("executeCode")()
    forked = ForkedTools.model_construct(
        items=(stub_run, stub_exec),
        binding_keys=frozenset({"sandbox"}),
    )
    out = await executor.node_execute(
        context=_node_context(),
        input=NodeInput(
            port_values={"state": _make_state(), "writer": writer, "forked_tools": forked}
        ),
    )
    request = out.port_values["model_visible_request"]
    assert isinstance(request, ModelVisibleRequest)
    assert len(request.tools) == 2
    by_name = {spec["function"]["name"]: spec for spec in request.tools}
    assert set(by_name) == {"runCommand", "executeCode"}
    assert by_name["runCommand"]["function"]["parameters"]["type"] == "object"


async def test_node_execute_tools_empty_when_forked_tools_missing() -> None:
    """ForkedTools 缺失 → ``request.tools == ()``,不抛(向后兼容测试/无工具 run)。"""
    executor = HistoryDeriveExecutor()
    writer = _FakeWriter(messages=[{"role": "user", "content": "q"}])
    out = await executor.node_execute(
        context=_node_context(),
        input=NodeInput(port_values={"state": _make_state(), "writer": writer}),
    )
    request = out.port_values["model_visible_request"]
    assert isinstance(request, ModelVisibleRequest)
    assert request.tools == ()


# ── System prompt seam (spec §G + run_a0cdcd40d8b9 regression) ─────────
#
# Spec §G mandates the per-run system prompt lands in
# ``ModelVisibleRequest.system``. The folded header (``EpochHeader.system``)
# publishes only when ``ModelVisibleHook.capture_pre_llm`` runs *inside*
# the LLM adapter — too late for ``think.history.assemble`` which prepares
# the request before ``think.llm.dispatch``. Three fallbacks fill the gap
# in priority order; each must be exercised.


@dataclass
class _StubSectionTrace:
    name: str


@dataclass
class _StubPromptTrace:
    template_id: str = "react_prompt"
    system_prompt_text: str = ""


@dataclass
class _StubReasonerTurnRender:
    """Mimics ``ReasonerTurnRender`` — only ``trace.system_prompt_text`` is read."""

    trace: _StubPromptTrace | None = None


def _render(system_text: str) -> _StubReasonerTurnRender:
    return _StubReasonerTurnRender(trace=_StubPromptTrace(system_prompt_text=system_text))


async def test_system_falls_back_to_turn_render_trace_when_header_missing() -> None:
    """``writer.request_header() is None`` ⇒ system sourced from ``turn_render.trace``.

    Per-run Session journals do not yet contain ``spine.llm.request.header``
    at history.assemble time; the only authoritative source at this seam
    is the upstream ``ReasonerTurnRender`` already produced by
    ``think.reason.render`` (one step earlier in the subgraph). Without
    this fallback the LLM sees ``system=""`` and runs with no identity /
    rules (run_a0cdcd40d8b9 regression).
    """
    executor = HistoryDeriveExecutor()
    writer = _FakeWriter(messages=[{"role": "user", "content": "hi"}], system=None)
    out = await executor.node_execute(
        context=_node_context(),
        input=NodeInput(
            port_values={
                "state": _make_state(),
                "writer": writer,
                "turn_render": _render("You are LobeHub 助手."),
            }
        ),
    )
    request = out.port_values["model_visible_request"]
    assert request.system == "You are LobeHub 助手."


async def test_system_prefers_header_when_folded() -> None:
    """``header.system`` wins over ``turn_render.trace`` (replay-safe fold path).

    On second turns / replay the Session fold has populated
    ``EpochHeader.system``; the fold is the SSOT for *reconstructed* runs.
    The render port only carries the latest render — older turns in
    the journal replay must keep the historical header even if a newer
    render is in flight.
    """
    executor = HistoryDeriveExecutor()
    writer = _FakeWriter(messages=[{"role": "user", "content": "hi"}], system="from-fold")
    out = await executor.node_execute(
        context=_node_context(),
        input=NodeInput(
            port_values={
                "state": _make_state(),
                "writer": writer,
                "turn_render": _render("from-render"),
            }
        ),
    )
    request = out.port_values["model_visible_request"]
    assert request.system == "from-fold"


async def test_system_role_profile_no_longer_falls_back() -> None:
    """PR-B: ``_system_from_role_profile`` was removed — no header + no
    render ⇒ empty system prompt.

    The third-tier ``role_profile`` fallback was retired. ``brain.role_profile``
    is the sole authority and is consumed by ``think.reason.render``,
    which surfaces the rendered prompt through ``turn_render.trace.system_prompt_text``.
    If the writer's request header is empty AND the render port
    carries no rendered system prompt, the LLM is dispatched with
    ``system=""`` — the same outcome the live render path produces
    when ``system_prompt_text`` is empty.
    """
    from lca.contracts.models.team.role.team import (
        RoleProfile,
        ToolPermissionManifest,
    )

    role_profile = RoleProfile(
        role="助手",
        goal="帮助用户完成日常任务",
        backstory="我是 LobeHub 助手.",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )
    executor = HistoryDeriveExecutor()
    writer = _FakeWriter(messages=[{"role": "user", "content": "hi"}], system=None)
    out = await executor.node_execute(
        context=_node_context(runtime={"role_profile": role_profile}),
        input=NodeInput(port_values={"state": _make_state(), "writer": writer}),
    )
    request = out.port_values["model_visible_request"]
    assert request.system == ""
    assert "LobeHub 助手" not in request.system
    assert "帮助用户" not in request.system


async def test_system_empty_when_no_header_no_render_no_role_profile() -> None:
    """No source at all ⇒ empty string (existing behavior; no regression)."""
    executor = HistoryDeriveExecutor()
    writer = _FakeWriter(messages=[{"role": "user", "content": "hi"}], system=None)
    out = await executor.node_execute(
        context=_node_context(),
        input=NodeInput(port_values={"state": _make_state(), "writer": writer}),
    )
    request = out.port_values["model_visible_request"]
    assert request.system == ""


async def test_system_empty_when_turn_render_trace_is_none() -> None:
    """PR-B: ``turn_render.trace is None`` ⇒ empty system prompt (no fallback).

    When the Reasoner renders without a section registry the trace is
    ``None`` and ``system_prompt_text == ""``. The prior role_profile
    fallback (now removed) used to mask this; the new 2-tier contract
    propagates the empty string so downstream observers see the real
    reason the LLM had no system prompt.
    """
    from lca.contracts.models.team.role.team import (
        RoleProfile,
        ToolPermissionManifest,
    )

    role_profile = RoleProfile(
        role="助手",
        goal="帮助用户",
        backstory="我是 LobeHub 助手.",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )
    executor = HistoryDeriveExecutor()
    writer = _FakeWriter(messages=[{"role": "user", "content": "hi"}], system=None)
    out = await executor.node_execute(
        context=_node_context(runtime={"role_profile": role_profile}),
        input=NodeInput(
            port_values={
                "state": _make_state(),
                "writer": writer,
                "turn_render": _StubReasonerTurnRender(trace=None),
            }
        ),
    )
    request = out.port_values["model_visible_request"]
    assert request.system == ""
    assert "LobeHub 助手" not in request.system
