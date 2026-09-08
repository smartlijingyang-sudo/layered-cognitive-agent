"""toolbox graph wiring + adapter + node tests.

Covers:
  - toolbox.yaml loads + compiles without validation errors
  - LcaToolboxRegistryProvider loads a YAML registry fixture
  - LcaToolboxResolveProvider resolves a tool name from a fixture registry
  - The full toolbox graph runs via agent_lab's runner
"""

from __future__ import annotations

import sys
from pathlib import Path

from agent_lab.graph.compile import compile as compile_spec
from agent_lab.graphs import load_registry
from agent_lab.primitives.artifact import Artifact, ArtifactKind

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# (1) graph load + compile
# ---------------------------------------------------------------------------


def test_toolbox_graph_loads_and_compiles() -> None:
    specs = load_registry("toolbox")
    assert "toolbox" in specs
    spec = specs["toolbox"]
    assert {n.id for n in spec.nodes} == {
        "load_registry",
        "trust_classify",
        "dedup",
        "resolve_tool",
    }
    bundle = compile_spec(spec)
    assert bundle.spec_id == "toolbox"
    flat = [nid for layer in bundle.layers for nid in layer]
    assert flat.index("load_registry") < flat.index("trust_classify")
    assert flat.index("trust_classify") < flat.index("dedup")
    assert flat.index("dedup") < flat.index("resolve_tool")


# ---------------------------------------------------------------------------
# (2) registry provider
# ---------------------------------------------------------------------------


def test_lca_toolbox_registry_provider_loads_yaml(tmp_path: Path) -> None:
    """LcaToolboxRegistryProvider loads a YAML fixture path."""
    from agent_lab.adapters.lca_toolbox import LcaToolboxRegistryProvider

    yaml_content = """\
tools:
  - ref: lca.plugins.tools.bash:build_bash_tool
    kwargs: {}
  - ref: lca.plugins.tools.file_write:build_file_write_tool
    kwargs: {}
"""
    yaml_path = tmp_path / "test_registry.yaml"
    yaml_path.write_text(yaml_content, encoding="utf-8")

    provider = LcaToolboxRegistryProvider.from_node_config({"registry_path": str(yaml_path)})
    artifact = provider.load({"registry_path": str(yaml_path)})
    assert artifact.kind == ArtifactKind.FACT
    assert artifact.schema_ref == "toolbox.registry_payload.v1"
    entries = artifact.content["entries"]
    assert len(entries) == 2
    assert "bash" in entries[0]["ref"]
    assert "file_write" in entries[1]["ref"]


# ---------------------------------------------------------------------------
# (3) resolve provider
# ---------------------------------------------------------------------------


def test_lca_toolbox_resolve_provider_with_fixture() -> None:
    """Register a fixture ToolRegistry with 2 named tools, assert resolve works."""
    from agent_lab.adapters.lca_toolbox import (
        LcaToolboxResolveProvider,
        register_fixture_tool_registry,
        unregister_fixture_tool_registry,
    )
    from agent_lab.tools.registry import ToolRegistry

    # Build a real ToolRegistry with 2 tools
    registry = ToolRegistry()
    registry.load_from_yaml(REPO_ROOT / "agent_lab" / "tools" / "registry.yaml")
    registered_names = registry.names()
    assert len(registered_names) >= 2, f"Expected >= 2 tools, got {registered_names}"

    fixture_name = "test-toolbox-resolve"
    register_fixture_tool_registry(fixture_name, registry)
    try:
        provider = LcaToolboxResolveProvider.from_node_config(
            {"provider_config": {"fixture_tool_registry_name": fixture_name}}
        )
        first_tool_name = registered_names[0]
        tool_name_artifact = Artifact(
            kind=ArtifactKind.TEXT,
            content=first_tool_name,
        )
        result = provider.resolve(tool_name_artifact=tool_name_artifact)
        assert result.kind == ArtifactKind.FACT
        assert result.schema_ref == "toolbox.tool_instance.v1"
        assert result.content["name"] == first_tool_name
        assert "description" in result.content
        assert "parameters" in result.content

        # Resolve second tool
        second_tool_name = registered_names[1]
        tool_name_artifact2 = Artifact(
            kind=ArtifactKind.TEXT,
            content=second_tool_name,
        )
        result2 = provider.resolve(tool_name_artifact=tool_name_artifact2)
        assert result2.content["name"] == second_tool_name
    finally:
        unregister_fixture_tool_registry(fixture_name)


# ---------------------------------------------------------------------------
# (4) runner integration
# ---------------------------------------------------------------------------


def test_toolbox_graph_runs_via_runner() -> None:
    """The toolbox graph runs end-to-end through agent_lab's runner."""
    from agent_lab.adapters.lca_toolbox import (
        register_fixture_tool_registry,
        unregister_fixture_tool_registry,
    )
    from agent_lab.runtime.runner import run as run_graph
    from agent_lab.tools.registry import ToolRegistry

    # Build and register a fixture ToolRegistry
    registry = ToolRegistry()
    registry.load_from_yaml(REPO_ROOT / "agent_lab" / "tools" / "registry.yaml")
    registered_names = registry.names()
    assert len(registered_names) >= 1

    fixture_name = "test-toolbox-runner"
    register_fixture_tool_registry(fixture_name, registry)

    specs = load_registry("toolbox")
    toolbox_spec = specs["toolbox"]

    # Point resolve_tool at the fixture registry
    for n in toolbox_spec.nodes:
        if n.id == "resolve_tool":
            n.config["provider_config"] = {
                "fixture_tool_registry_name": fixture_name,
            }

    target_tool = registered_names[0]
    initial = {
        "in_tool_name": Artifact(
            kind=ArtifactKind.TEXT,
            content=target_tool,
            schema_ref="raw",
        ),
    }
    try:
        trace = run_graph(toolbox_spec, initial=initial, sub_registry=specs)
        assert "tool_instance" in trace.final_artifacts, (
            f"toolbox graph must emit tool_instance; got {sorted(trace.final_artifacts)}"
        )
        tool_instance = trace.final_artifacts["tool_instance"]
        assert tool_instance.kind == ArtifactKind.FACT
        assert tool_instance.content["name"] == target_tool
    finally:
        unregister_fixture_tool_registry(fixture_name)
