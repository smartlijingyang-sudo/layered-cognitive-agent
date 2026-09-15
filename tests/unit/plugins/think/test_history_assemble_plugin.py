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

from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.contracts.protocols.session.model.context import ModelVisibleRequest
from lca.nodes.think.history import assemble as history_module
from lca.nodes.think.history.assemble import HistoryDeriveExecutor

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
    """``semantic_name`` must match ``factory: history.derive`` in the bundle."""
    assert HistoryDeriveExecutor().semantic_name == "history.derive"
    assert HistoryDeriveExecutor().region == "phase:think"
    assert HistoryDeriveExecutor().declared_inputs == ("state", "writer")
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
    """``setup.setup()`` calls ``ctx.provide('phase:think::history.derive', executor)``."""
    captured: dict[str, Any] = {}
    ctx = MagicMock()
    ctx.provide = MagicMock(side_effect=lambda key, value: captured.__setitem__(key, value))

    await history_module.setup.setup(ctx, config=None)

    assert list(captured) == ["phase:think::history.derive"]
    assert isinstance(captured["phase:think::history.derive"], HistoryDeriveExecutor)
