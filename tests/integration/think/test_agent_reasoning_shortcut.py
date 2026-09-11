"""End-to-end: agent.reasoning.shortcut + think.classify/gate cutover (ADR-0220 §11 P6).

Verifies the P6 cutover:

  - ``agent.reasoning.shortcut`` graph (1 node ``shortcut.try`` →
    ``concept.decision.shortcut_try``) parses cleanly and drives
    end-to-end with a stub SubgraphRunner that emits a pre-canned
    Decision.
  - ``bundles/think.yaml`` cutover: ``think.classify`` and ``think.gate``
    nodes changed from inline factories (``think.classify`` /
    ``think.gate``) to ``sub_spec_ref`` delegates pointing at the
    new concept graphs (``concept.decision.classify`` /
    ``concept.decision.enforce``). Topology still parses; both
    ref nodes carry valid ``sub_spec_ref`` typed fields.

The driver test does not depend on a live LLM or on the production
sub_runner pipeline: it stubs the SubgraphRunner to emit pre-canned
typed PhaseOutputs per binding_edge.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.bundle_graph import (
    BundleGraphNode,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    ExecutionOutcome,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    SubgraphReference,
)
from lca.framework.subgraph.plugins.channel import (
    InMemoryPhaseOutputChannel,
    PhaseOutput,
)
from lca.framework.subgraph.plugins.node_graph_driver import NodeGraphDriver
from lca.harness.declarative.compile.subgraph_resolver import (
    _load_bundle_graph_spec,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SHORTCUT_BUNDLE = "bundles/agent/reasoning_shortcut.yaml"
THINK_BUNDLE = "bundles/think.yaml"


def _state() -> AgentState:
    return AgentState(trace_id="t", task="ping", budget=Budget())


def _stub_decision() -> Decision:
    return Decision(
        decision_id="dec_shortcut_v2",
        action_type=ActionType.RESPOND.value,
        rationale="stub-shortcut",
        confidence=1.0,
        response_text="shortcut-hit",
    )


_STUB_DECISION_FOR_SHORTCUT = _stub_decision()


@dataclass
class _ShortcutSubRunner:
    """Returns a pre-canned Decision on the shortcut.try binding_edge.

    Other binding_edges (none in this graph) would receive an empty
    PhaseOutput. The stub mirrors the production runner's publish/absorb
    contract: every inner PhaseOutput gets published so the outer
    driver's close-out projection can fold typed payloads into
    ``outer_input``.
    """

    async def run(
        self,
        *,
        ref: SubgraphReference,
        outer_state: AgentState,
        channel: InMemoryPhaseOutputChannel,
    ) -> tuple[AgentState, PhaseOutput]:
        if ref.binding_edge == "shortcut.try":
            output = PhaseOutput(decision=_STUB_DECISION_FOR_SHORTCUT)
        else:
            output = PhaseOutput()
        channel.publish(
            producer_node=ref.binding_edge,
            phase="agent",
            output=output,
        )
        return outer_state, output


@dataclass
class _StaticScope:
    """Stub SubgraphRuntime scope; the test never resolves a real factory."""

    def resolve(self, capability: str) -> Any:
        return None

    def resolve_capability(self, capability: str) -> Any:
        return None

    def resolve_factory(self, factory: str, region: str | None) -> Any:
        del factory, region
        return None


class TestAgentReasoningShortcutBundleTopology:
    """§3.4 + §11 P6 acceptance: bundle structure invariants."""

    def test_bundle_yaml_resolves_to_single_node_no_edge_graph(self) -> None:
        spec = _load_bundle_graph_spec(SHORTCUT_BUNDLE)
        assert spec.id == "agent.reasoning.shortcut"
        assert spec.region == "agent"
        assert len(spec.nodes) == 1
        assert len(spec.edges) == 0

    def test_shortcut_node_delegates_to_concept_decision_shortcut_try(self) -> None:
        spec = _load_bundle_graph_spec(SHORTCUT_BUNDLE)
        node = spec.nodes[0]
        assert isinstance(node, BundleGraphNode)
        assert node.id == "shortcut.try"
        assert node.sub_spec_ref is not None
        assert node.sub_spec_ref.plan_ref == "bundles/concept/decision_shortcut_try.yaml"
        assert node.sub_spec_ref.entry_node == "shortcut.try"
        assert node.sub_spec_ref.binding_edge == "shortcut.try"

    def test_inner_concept_graph_is_loadable(self) -> None:
        spec = _load_bundle_graph_spec(SHORTCUT_BUNDLE)
        node = spec.nodes[0]
        assert node.sub_spec_ref is not None
        inner = _load_bundle_graph_spec(node.sub_spec_ref.plan_ref)
        assert inner.id == "concept.decision.shortcut_try"
        assert len(inner.nodes) == 1


class TestAgentReasoningShortcutE2E:
    """End-to-end drive: agent.reasoning.shortcut → typed Decision."""

    @pytest.mark.asyncio
    async def test_shortcut_returns_typed_decision_when_capability_hits(self) -> None:
        spec = _load_bundle_graph_spec(SHORTCUT_BUNDLE)
        driver = NodeGraphDriver(
            spec=spec,
            plan_ref=SHORTCUT_BUNDLE,
            scope=_StaticScope(),
            sub_runner=_ShortcutSubRunner(),
            channel_factory=InMemoryPhaseOutputChannel,
        )

        channel = InMemoryPhaseOutputChannel()
        result = await driver.run(
            outer_state=_state(),
            channel=channel,
            artifacts={},
            outer_input=None,
        )

        assert result.output.outcome_kind is not ExecutionOutcome.FAILED
        assert result.output.error is None

        snap = channel.snapshot()
        assert any(
            getattr(out, "decision", None) is not None
            and getattr(out.decision, "decision_id", None) == "dec_shortcut_v2"
            for out in snap.values()
        ), (
            f"ADR-0220 §3.4 violated: agent.reasoning.shortcut must end with "
            f"the typed Decision emitted by shortcut.try. Published: {sorted(snap)}"
        )


class TestThinkYamlClassifyGateCutover:
    """§11 P6 acceptance: think.classify + think.gate switched to sub_spec_ref."""

    def test_think_yaml_classify_node_delegates_to_concept_decision_classify(self) -> None:
        spec = _load_bundle_graph_spec(THINK_BUNDLE)
        classify_node = next(n for n in spec.nodes if n.id == "think.classify")
        assert classify_node.sub_spec_ref is not None
        assert classify_node.sub_spec_ref.plan_ref == "bundles/concept/decision_classify.yaml"
        assert classify_node.sub_spec_ref.entry_node == "decision.parse.tool_calls"
        assert classify_node.sub_spec_ref.binding_edge == "think.classify"

    def test_think_yaml_gate_node_delegates_to_concept_decision_enforce(self) -> None:
        spec = _load_bundle_graph_spec(THINK_BUNDLE)
        gate_node = next(n for n in spec.nodes if n.id == "think.gate")
        assert gate_node.sub_spec_ref is not None
        assert gate_node.sub_spec_ref.plan_ref == "bundles/concept/decision_enforce.yaml"
        assert gate_node.sub_spec_ref.entry_node == "gate.chain.run"
        assert gate_node.sub_spec_ref.binding_edge == "think.gate"

    def test_think_yaml_classify_declares_response_port(self) -> None:
        """The outer think.classify node must declare a typed `response`
        input port so the upstream think.reason response typed payload
        gets routed through the close-out projection.

        The yaml ``inputs:`` / ``outputs:`` fields are silently ignored
        by the BundleGraphNode loader (ADR-0219 §5.5 — port contract
        lives on the plugin's ``declared_inputs`` typed attribute, not
        on the graph node). Read the raw yaml for these assertions so
        the test exercises the actual authored bundle shape.
        """
        raw = yaml.safe_load((REPO_ROOT / THINK_BUNDLE).read_text(encoding="utf-8"))
        classify_node = next(n for n in raw["nodes"] if n["id"] == "think.classify")
        assert "response" in classify_node["inputs"]
        assert "decision" in classify_node["outputs"]

    def test_think_yaml_gate_declares_decision_port(self) -> None:
        """The outer think.gate node must declare a typed `decision`
        port on both input and output (gate is decision transformer,
        per ADR §7).
        """
        raw = yaml.safe_load((REPO_ROOT / THINK_BUNDLE).read_text(encoding="utf-8"))
        gate_node = next(n for n in raw["nodes"] if n["id"] == "think.gate")
        assert "decision" in gate_node["inputs"]
        assert "decision" in gate_node["outputs"]

    def test_think_yaml_topology_unchanged_after_cutover(self) -> None:
        """5 nodes + 5 edges — the cutover only changes node
        factories, not the topology.
        """
        spec = _load_bundle_graph_spec(THINK_BUNDLE)
        assert len(spec.nodes) == 5
        assert len(spec.edges) == 5
        node_ids = {n.id for n in spec.nodes}
        assert node_ids == {
            "think.shortcut",
            "think.route",
            "think.reason",
            "think.classify",
            "think.gate",
        }
