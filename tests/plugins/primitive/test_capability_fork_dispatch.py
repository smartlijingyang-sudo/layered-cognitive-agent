"""Conformance pins for ``phase.primitive.capability.fork.dispatch``.

``CapabilityForkDispatchExecutor.node_execute`` is the typed boundary
between the declarative graph and the tools plane (ADR-0220 §4.1):
a ``BindingsView`` goes in, a ``ForkedTools`` typed boundary comes out.
These pins lock the three fail-closed invariants:

1. the ``bindings`` port must be a ``BindingsView`` instance (TypeError);
2. the ``tools`` capability must be present on the runtime scope
   (RuntimeError);
3. the emitted ``forked_tools`` port is a ``ForkedTools`` whose
   ``binding_keys`` always mirror ``_FORKED_BINDING_KEYS``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from lca.contracts.models.cognition.boundary import BindingsView, ForkedTools
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.plugins.primitive.capability_fork.dispatch import (
    _FORKED_BINDING_KEYS,
    CapabilityForkDispatchExecutor,
)


class _FakeForked:
    """Minimal stand-in for the object returned by ``fork_for_run``."""

    def __init__(self, tools: tuple[object, ...] = ()) -> None:
        self._tools = tools

    def list_tools(self) -> tuple[object, ...]:
        return self._tools


class _FakeToolsService:
    def __init__(self, forked: _FakeForked) -> None:
        self._forked = forked
        self.seen_bindings: list[BindingsView] = []

    def fork_for_run(self, bindings: BindingsView) -> _FakeForked:
        self.seen_bindings.append(bindings)
        return self._forked


def _ctx(*, tools: object | None) -> NodeContext:
    runtime = SimpleNamespace(tools=tools)
    return NodeContext(runtime=runtime, budget={}, metadata={})  # type: ignore[arg-type]


def _input(bindings: object) -> NodeInput:
    return NodeInput(port_values={PortName("bindings"): bindings})


async def test_rejects_non_bindings_view_port() -> None:
    executor = CapabilityForkDispatchExecutor()
    service = _FakeToolsService(_FakeForked())
    for bad in (None, {}, "bindings", 42):
        with pytest.raises(TypeError, match="must be a BindingsView"):
            await executor.node_execute(_ctx(tools=service), _input(bad))


async def test_requires_tools_capability_in_runtime() -> None:
    executor = CapabilityForkDispatchExecutor()
    with pytest.raises(RuntimeError, match="'tools' capability missing"):
        await executor.node_execute(
            _ctx(tools=None), _input(BindingsView())
        )


async def test_emits_typed_forked_tools_boundary() -> None:
    executor = CapabilityForkDispatchExecutor()
    service = _FakeToolsService(_FakeForked())
    bindings = BindingsView(mode="solo")

    output = await executor.node_execute(_ctx(tools=service), _input(bindings))

    assert service.seen_bindings == [bindings]
    forked_tools = output.port_values[PortName("forked_tools")]
    assert isinstance(forked_tools, ForkedTools)
    assert forked_tools.items == ()
    assert forked_tools.binding_keys == _FORKED_BINDING_KEYS
