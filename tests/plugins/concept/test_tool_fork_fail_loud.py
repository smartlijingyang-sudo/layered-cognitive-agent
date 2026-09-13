"""Fail-loud contract: Profile → Bindings → ForkedTools surfaces sandbox APIs."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from lca.contracts.models.cognition.boundary import BindingsView
from lca.contracts.models.core.state.plane import PlaneKind, PlaneRef
from lca.infrastructure.capability.tools.tools import ToolsService
from lca.plugins.concept.tool_fork.dispatch import (
    ToolForkDispatchExecutor,
    _assert_sandbox_tools_visible,
)


def test_assert_sandbox_tools_visible_passes_when_apis_present() -> None:
    bindings = BindingsView(sandbox=object())
    items = (SimpleNamespace(name="g2a:runCommand"), SimpleNamespace(name="g2a:executeCode"))
    _assert_sandbox_tools_visible(bindings, items)


def test_assert_sandbox_tools_visible_fails_when_apis_missing() -> None:
    bindings = BindingsView(sandbox=object())
    with pytest.raises(RuntimeError, match="runCommand"):
        _assert_sandbox_tools_visible(bindings, (SimpleNamespace(name="ask_user"),))


def test_assert_sandbox_tools_visible_noop_without_sandbox() -> None:
    bindings = BindingsView(sandbox=None)
    _assert_sandbox_tools_visible(bindings, ())


def test_sandbox_plane_without_sandbox_capability_fails_in_default_tools() -> None:
    from lca.infrastructure.tools.default.set import _tools_for_ref

    plane = PlaneRef(
        id="sbx",
        label="sandbox",
        kind=PlaneKind.SANDBOX,
        root="/",
        outputs_dir="/out",
    )
    with pytest.raises(RuntimeError, match="SANDBOX plane"):
        _tools_for_ref(plane, file_store=object(), sandbox=None, machine_resolver=None)


@pytest.mark.asyncio
async def test_tool_fork_dispatch_fail_loud_when_sandbox_tools_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = ToolForkDispatchExecutor()

    class _Runtime:
        tools = ToolsService()

    class _Ctx:
        runtime = _Runtime()

    # Register a factory that returns non-sandbox tools even when sandbox set.
    _Runtime.tools.register_factory("g2a", lambda _b: [SimpleNamespace(name="ask_user")])

    from lca.contracts.protocols.declarative.declarative_1.node_executor import NodeInput

    bindings = BindingsView(sandbox=object())
    with pytest.raises(RuntimeError, match="missing"):
        await executor.node_execute(
            _Ctx(),  # type: ignore[arg-type]
            NodeInput(port_values={"bindings": bindings}),
        )
