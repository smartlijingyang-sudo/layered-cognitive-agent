"""Tests for Tool.namespace and DeferPolicy 8-domain contracts (ADR-0256)."""

from __future__ import annotations

from typing import Any, ClassVar

from lca.contracts.models.core.execution.tool import ToolApi
from lca.contracts.protocols import Tool
from lca.infrastructure.tool_defer.policy import STANDARD_NAMESPACES, DeferPolicy


def test_tool_protocol_requires_namespace() -> None:
    class IncompleteTool:
        name: ClassVar[str] = "test"
        description: ClassVar[str] = "test"
        parameters: ClassVar[dict[str, Any]] = {}
        is_idempotent: ClassVar[bool] = True
        effect_kind: ClassVar[str] = "ephemeral"
        default_timeout_s: ClassVar[int] = 10

        async def execute(self, args):
            return None

        def validate(self, args):
            return None

    # Lacks namespace -> not an instance of Tool protocol
    assert not isinstance(IncompleteTool(), Tool)

    class CompleteTool(IncompleteTool):
        namespace = "file"

    assert isinstance(CompleteTool(), Tool)


def test_tool_api_has_namespace_field() -> None:
    api = ToolApi(name="foo", description="bar", parameters={}, namespace="file")
    assert api.namespace == "file"


def test_defer_policy_standard_namespaces() -> None:
    policy = DeferPolicy.default()
    assert policy.eager_namespaces == frozenset({"core", "memory"})
    assert set(policy.namespace_descriptions.keys()) == set(STANDARD_NAMESPACES)
    assert set(STANDARD_NAMESPACES) == {
        "core",
        "file",
        "shell",
        "memory",
        "skill",
        "web",
        "agent",
        "ext",
        "lca",
        "cron",
        "avatar",
    }
    assert "shell" in policy.namespace_approval
    assert policy.namespace_approval["shell"] == "require_approval"


def test_defer_policy_for_vocal_mode_gated_keeps_agent_eager() -> None:
    """Gated vocal mode must expose ``send_message`` from the first turn."""
    policy = DeferPolicy.for_vocal_mode("gated")
    assert "core" in policy.eager_namespaces
    assert "memory" in policy.eager_namespaces
    assert "agent" in policy.eager_namespaces


def test_defer_policy_for_vocal_mode_direct_unchanged() -> None:
    policy = DeferPolicy.for_vocal_mode("direct")
    assert policy.eager_namespaces == frozenset({"core", "memory"})


def test_defer_policy_keeps_memory_eager_on_wire() -> None:
    """Memory namespace tools stay eager on wire to align with ADR-0260."""
    from lca.infrastructure.tool_defer.session import ToolDeferSession

    search = _stub_tool("tool_search", "core")
    mem_add = _stub_tool("memory_add", "memory")
    file_tool = _stub_tool("writeFile", "file")
    session = ToolDeferSession(DeferPolicy.default())
    session.update_turn((search, mem_add, file_tool))
    wire, catalog = session.render_turn()
    names = [spec["function"]["name"] for spec in wire]
    assert "tool_search" in names
    assert "memory_add" in names
    assert "writeFile" not in names
    assert "- file:" in catalog
    assert "- memory:" not in catalog


def test_per_tool_eager_file_read_on_the_wire() -> None:
    """Per-tool eager override: file read tools stay on wire while write tools stay deferred."""
    from lca.infrastructure.tool_defer.session import ToolDeferSession

    search = _stub_tool("tool_search", "core")
    read_tool = _stub_tool("readFile", "file", eager=True)
    write_tool = _stub_tool("writeFile", "file", eager=False)
    session = ToolDeferSession(DeferPolicy.default())
    session.update_turn((search, read_tool, write_tool))
    wire, catalog = session.render_turn()
    names = [spec["function"]["name"] for spec in wire]
    assert "tool_search" in names
    assert "readFile" in names
    assert "writeFile" not in names
    assert "- file:" in catalog

    # Loading namespace 'file' brings writeFile onto the wire and clears catalog line
    session.load_namespace("file")
    wire_after, catalog_after = session.render_turn()
    names_after = [spec["function"]["name"] for spec in wire_after]
    assert "writeFile" in names_after
    assert "- file:" not in catalog_after


def _stub_tool(name: str, namespace: str, eager: bool = False) -> Any:
    async def _execute(self, args):  # pragma: no cover - stub
        return None

    def _validate(self, args):  # pragma: no cover - stub
        return None

    return type(
        f"_StubTool_{name}",
        (),
        {
            "name": name,
            "namespace": namespace,
            "eager": eager,
            "description": f"description for {name}",
            "parameters": {"type": "object", "properties": {}},
            "execute": _execute,
            "validate": _validate,
        },
    )()


def test_gated_policy_renders_send_message_on_the_wire() -> None:
    """Gated policy: send_message schema is model-visible, not a catalog line."""
    from lca.infrastructure.tool_defer.session import ToolDeferSession

    search = _stub_tool("tool_search", "core")
    send = _stub_tool("send_message", "agent")
    session = ToolDeferSession(DeferPolicy.for_vocal_mode("gated"))
    session.update_turn((search, send))
    wire, catalog = session.render_turn()
    names = [spec["function"]["name"] for spec in wire]
    assert "send_message" in names
    assert "send_message" not in catalog


def test_direct_policy_defers_send_message_to_catalog() -> None:
    """Direct policy keeps deferring send_message until tool_search loads it."""
    from lca.infrastructure.tool_defer.session import ToolDeferSession

    search = _stub_tool("tool_search", "core")
    send = _stub_tool("send_message", "agent")
    session = ToolDeferSession(DeferPolicy.default())
    session.update_turn((search, send))
    wire, catalog = session.render_turn()
    names = [spec["function"]["name"] for spec in wire]
    assert "send_message" not in names
    assert "- agent:" in catalog
