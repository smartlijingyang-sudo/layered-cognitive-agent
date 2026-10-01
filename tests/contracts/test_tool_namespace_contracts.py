"""Tests for Tool.namespace and DeferPolicy 8-domain contracts (ADR-0256)."""

from __future__ import annotations

from lca.contracts.models.core.execution.tool import ToolApi
from lca.contracts.protocols import Tool
from lca.infrastructure.tool_defer.policy import STANDARD_NAMESPACES, DeferPolicy


def test_tool_protocol_requires_namespace() -> None:
    class IncompleteTool:
        name = "test"
        description = "test"
        parameters = {}
        is_idempotent = True
        effect_kind = "ephemeral"
        default_timeout_s = 10

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


def test_defer_policy_standard_eight_namespaces() -> None:
    policy = DeferPolicy.default()
    assert policy.eager_namespaces == frozenset({"core"})
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
    }
    assert "shell" in policy.namespace_approval
    assert policy.namespace_approval["shell"] == "require_approval"
