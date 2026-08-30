"""Regression tests for custom phase capabilities and node implementations."""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.harness.composer import AgentGraphContribution, merge_agent_graphs
from lca.layer2_runtime.runtime_bindings import RuntimePhaseCapabilities


def _complete_contribution(
    *,
    phase_capabilities: dict[str, object],
    composer: str,
) -> AgentGraphContribution:
    """Build a structurally complete graph contribution for mapping-only tests."""

    return AgentGraphContribution(
        brain=object(),
        body=object(),
        memory=object(),
        state_store=object(),
        perceive_hub=object(),
        hooks=object(),
        observability=object(),
        llm=object(),
        phase_capabilities=phase_capabilities,
        metadata={"composer": composer},
    )


def test_agent_graph_freezes_custom_capabilities_and_derives_standard_ones() -> None:
    stop_policy = object()
    source = {"custom.phase.input": object(), "stop_policy": stop_policy}

    graph = merge_agent_graphs(
        _complete_contribution(phase_capabilities=source, composer="fixture")
    )

    source["late"] = object()

    assert graph.phase_capabilities["custom.phase.input"] is not None
    assert graph.phase_capabilities["brain"] is graph.brain
    assert graph.phase_capabilities["body"] is graph.body
    assert graph.phase_capabilities["memory"] is graph.memory
    assert graph.phase_capabilities["perceive_hub"] is graph.perceive_hub
    assert graph.phase_capabilities["stop_policy"] is stop_policy
    assert not hasattr(graph, "stop_rule")
    assert "late" not in graph.phase_capabilities
    with pytest.raises(TypeError):
        graph.phase_capabilities["late"] = object()  # type: ignore[index]


def test_agent_graph_rejects_duplicate_phase_capability_owners() -> None:
    first = _complete_contribution(
        phase_capabilities={"custom.phase.input": object()},
        composer="first",
    )
    duplicate = AgentGraphContribution(
        phase_capabilities={"custom.phase.input": object()},
        metadata={"composer": "second"},
    )

    with pytest.raises(ValueError, match="phase capability conflict"):
        merge_agent_graphs(first, duplicate)


def test_agent_graph_rejects_standard_phase_capability_redeclaration() -> None:
    contribution = _complete_contribution(
        phase_capabilities={"brain": object()},
        composer="fixture",
    )

    with pytest.raises(ValueError, match="standard phase capabilities"):
        merge_agent_graphs(contribution)


def test_runtime_phase_capabilities_accept_custom_contribution_keys() -> None:
    source = {"custom.phase.input": object(), "body": object(), "memory": object()}

    capabilities = RuntimePhaseCapabilities(source)
    source["late"] = object()

    assert capabilities.require("custom.phase.input") is not None
    assert capabilities.body is not None
    assert capabilities.memory is not None
    assert capabilities.get("late") is None


def test_standard_nodes_do_not_route_through_shared_semantic_branching() -> None:
    """Every default node owns its behavior in its selected plugin module."""

    common = Path("lca/plugins/phase_executors/common.py").read_text(encoding="utf-8")
    assert "if self.phase" not in common
    assert "StandardPhaseExecutor" not in common

    expected_modules = {
        "act.py": "StandardActExecutor",
        "perceive.py": "StandardPerceiveExecutor",
        "reflect.py": "StandardReflectExecutor",
        "remember.py": "StandardRememberExecutor",
        "stop.py": "StandardStopExecutor",
        "think.py": "StandardThinkExecutor",
    }
    for filename, executor_name in expected_modules.items():
        source = (Path("lca/plugins/phase_executors") / filename).read_text(encoding="utf-8")
        assert f"class {executor_name}" in source
