"""Tests for tool namespace declaration across factories and manifests (ADR-0256 Task 2)."""

from __future__ import annotations

from lca.contracts.models.core.execution.tool import ToolApi, ToolManifest, ToolMeta
from lca.infrastructure.capability.tools.tools import ToolsService
from lca.infrastructure.tool_defer.policy import STANDARD_NAMESPACES
from lca.infrastructure.tools.builder.builder import build_tools_from_manifest


def test_builder_propagates_namespace() -> None:
    manifest = ToolManifest(
        identifier="test",
        type="builtin",
        api=(ToolApi(name="foo", description="d", parameters={}, namespace="file"),),
        meta=ToolMeta(avatar="x", title="t", description="d"),
    )
    tools = build_tools_from_manifest(manifest, object())
    assert len(tools) == 1
    assert tools[0].namespace == "file"


def test_tools_service_has_no_central_tool_namespaces_dict() -> None:
    service = ToolsService()
    assert not hasattr(service, "_tool_namespaces")
    assert not hasattr(service, "tool_namespaces")


def test_standard_builtins_have_declared_namespace() -> None:
    from lca.infrastructure.tool_defer.tool_search import ToolSearchTool
    from lca.infrastructure.tools.web_search import MANIFEST as WEB_MANIFEST
    from lca.infrastructure.tools.ask_user import MANIFEST as HIL_MANIFEST
    from lca.infrastructure.tools.lca_computer.manifest import CLOUD_SANDBOX_MANIFEST

    assert ToolSearchTool.namespace == "core"

    # web_search
    assert WEB_MANIFEST.api[0].namespace == "web"

    # ask_user
    assert HIL_MANIFEST.api[0].namespace == "agent"

    # lca_computer: file vs shell separation
    file_apis = {
        "listFiles",
        "readFile",
        "writeFile",
        "editFile",
        "searchFiles",
        "moveFiles",
        "grepContent",
        "globFiles",
        "exportFile",
    }
    shell_apis = {"runCommand", "getCommandOutput", "killCommand", "executeCode"}
    for api in CLOUD_SANDBOX_MANIFEST.api:
        if api.name in file_apis:
            assert api.namespace == "file", f"{api.name} should have namespace='file', got {api.namespace}"
        elif api.name in shell_apis:
            assert api.namespace == "shell", f"{api.name} should have namespace='shell', got {api.namespace}"
        else:
            assert api.namespace in STANDARD_NAMESPACES, f"unknown api {api.name}"
