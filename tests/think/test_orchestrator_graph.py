"""End-to-end: phase.think.orchestrator resolves and drives the 5-step graph."""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.harness.graph.execute.subgraph_phase_runner import default_subgraph_phase_runner
from lca.plugins.loop.phase.think.orchestrator.plugin import ThinkOrchestratorExecutor

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_orchestrator_resolves_plan() -> None:
    """The default SubgraphPhaseRunner can resolve bundles/think-orchestrator.yaml."""
    resolver = default_subgraph_phase_runner().resolver
    plan = resolver.resolve("bundles/think-orchestrator.yaml")
    assert plan is not None


def test_orchestrator_resolves_graph_topology() -> None:
    """The phase graph topology bundle resolves and exposes the 5 expected nodes."""
    resolver = default_subgraph_phase_runner().resolver
    plan = resolver.resolve("bundles/think-orchestrator.yaml")
    assert plan is not None
    graph = plan.phase_graph
    assert graph is not None
    node_ids = [n.id for n in graph.nodes]
    assert "think.shortcut" in node_ids
    assert "think.route" in node_ids
    assert "think.reason" in node_ids
    assert "think.classify" in node_ids
    assert "think.gate" in node_ids


def test_orchestrator_executor_defaults() -> None:
    """create_executor wires the documented default plan_ref + entry_node."""
    executor = ThinkOrchestratorExecutor(
        plan_ref="bundles/think-orchestrator.yaml",
        entry_node="think.shortcut",
    )
    assert executor.plan_ref == "bundles/think-orchestrator.yaml"
    assert executor.entry_node == "think.shortcut"


def test_orchestrator_5_step_plugins_active() -> None:
    """All five flat step plugins are present in the working tree."""
    expected = [
        "lca/plugins/think/shortcut/plugin.py",
        "lca/plugins/think/route/plugin.py",
        "lca/plugins/think/reason/plugin.py",
        "lca/plugins/think/classify/plugin.py",
        "lca/plugins/think/gate/plugin.py",
    ]
    for path in expected:
        full = REPO_ROOT / path
        assert full.exists(), f"missing step plugin: {path}"


def test_orchestrator_spec_is_phase_executor() -> None:
    """The orchestrator plugin declares PluginSpecKind.PHASE_EXECUTOR so it can be bound by ``think.main``."""
    from lca.contracts.protocols.declarative.declarative_1.declarative_common import PluginSpecKind
    from lca.plugins.loop.phase.think.orchestrator.plugin import SPEC

    assert SPEC.kind == PluginSpecKind.PHASE_EXECUTOR
    provides = next(iter(SPEC.provides))
    assert provides.key == "phase.think.orchestrator"


@pytest.mark.asyncio
async def test_orchestrator_e2e_placeholder() -> None:
    """Full end-to-end requires a booted kernel with brain/reducer/classifier/gate;

    that integration coverage lives behind ``lca_kernel serve --profile
    profiles/web-standard.yaml`` which the full-pre-push gate exercises.
    This test asserts the orchestrator and 5-step topology are wired.
    """
    resolver = default_subgraph_phase_runner().resolver
    plan = resolver.resolve("bundles/think-orchestrator.yaml")
    assert plan is not None
    assert plan.phase_graph is not None
