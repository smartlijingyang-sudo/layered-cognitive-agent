"""End-to-end: think subgraph runs plan → render → complete → classify → gate (ADR-0220 P9).

The Default factory's think subgraph runs all 3 reasoner nodes —
plan, render, complete — plus classify and gate. End-to-end the think
subgraph visits all 5 outer nodes:

  shortcut → route → reason → classify → gate

and the terminal ``PhaseOutput`` carries a Decision with
action_type="respond" (from the default classifier).

ADR-0220 P9 history: this test used to wire ``no_llm_mode=True`` so
the runner would strip ``think.reason.complete`` at lift time
(ADR-0219 §10.11 item 2). That fallback path is gone: the Default
reasoner now implements ``complete_turn`` (the typed ``ForkedTools``
boundary from P5 / ``primitive.llm.call`` makes the LLM call typed
and reachable), so the strip is no longer needed.

Setup:
1. Build the real outer think spec by loading ``bundles/think.yaml``
   via the production loader (which now parses ``sub_spec_ref`` into
   a typed field).
2. Use a stub SubgraphResolver that returns a v2 marker plan wrapping
   ``bundles/think_reason.yaml``; the inner runner walks the full
   3-node subgraph through the real NodeGraphDriver.
3. Use the production ``_DefaultSubgraphRuntime`` (mirrored in this
   test) so plan / render / complete / classify / gate all run with
   stub capabilities.
4. Drive the outer SubgraphRunner directly; the typed sub_spec_ref
   at think.reason causes NodeGraphDriver to delegate to the inner
   runner.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.bundle_graph import (
    BundleGraphSpec,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    SubgraphReference,
)
from lca.contracts.protocols.declarative.declarative_1.v2_plan_marker import (
    V2BundleGraphPlanMarker,
)
from lca.framework.subgraph.plugins.channel import InMemoryPhaseOutputChannel
from lca.framework.subgraph.plugins.runner import SubgraphRunner
from lca.plugins.think.classify import ThinkClassifyExecutor
from lca.plugins.think.gate import ThinkGateExecutor
from lca.plugins.think.reason.complete import ThinkReasonCompleteExecutor
from lca.plugins.think.reason.plan import ThinkReasonPlanExecutor
from lca.plugins.think.reason.render import ThinkReasonRenderExecutor
from lca.plugins.think.route import ThinkRouteExecutor
from lca.plugins.think.shortcut import ThinkShortcutExecutor


def _state() -> AgentState:
    return AgentState(trace_id="t", task="hello", budget=Budget())


@dataclass
class _DefaultReasoner:
    """Mirrors Default factory's reasoner — full 3-method contract."""

    async def generate_thoughts(self, state: AgentState) -> LLMResponse:
        return LLMResponse()

    async def complete_turn(self, state: AgentState, render: Any) -> LLMResponse:
        return LLMResponse(text="stub")


@dataclass
class _DefaultDecisionClassifier:
    def classify(self, response: LLMResponse) -> Any:
        from lca.contracts.models.core.execution.decision import Decision

        return Decision(
            decision_id="dec_default",
            action_type="respond",
            rationale="default",
            confidence=1.0,
        )


@dataclass
class _DefaultDecisionGate:
    async def enforce(self, state: AgentState, decision: Any) -> Any:
        return decision


@dataclass
class _DefaultSkillRouter:
    async def route(self, state: AgentState) -> str:
        return ""


@dataclass
class _DefaultSupportsShortcut:
    async def try_shortcut(self, state: AgentState) -> Any:
        return None


_CAPS = {
    "reasoner": _DefaultReasoner(),
    "decision_classifier": _DefaultDecisionClassifier(),
    "decision_gate": _DefaultDecisionGate(),
    "skill_router": _DefaultSkillRouter(),
    "supports_shortcut": _DefaultSupportsShortcut(),
    "agent_gates": _DefaultDecisionGate(),
}


_EXECUTOR_REGISTRY: dict[tuple[str, str], Any] = {
    ("phase:think", "think.shortcut"): ThinkShortcutExecutor(),
    ("phase:think", "think.route"): ThinkRouteExecutor(),
    ("phase:think", "think.reason.plan"): ThinkReasonPlanExecutor(),
    ("phase:think", "think.reason.render"): ThinkReasonRenderExecutor(),
    ("phase:think", "think.reason.complete"): ThinkReasonCompleteExecutor(),
    ("phase:think", "think.classify"): ThinkClassifyExecutor(),
    ("phase:think", "think.gate"): ThinkGateExecutor(),
}


class _DefaultSubgraphRuntime:
    """Mirrors Default factory's _DefaultSubgraphRuntime — same shape,
    same capability dict, same factory registry."""

    def resolve(self, capability: str) -> Any:
        return _CAPS.get(capability)

    def resolve_capability(self, capability: str) -> Any:
        return _CAPS.get(capability)

    def resolve_factory(self, factory: str, region: str | None) -> Any:
        return _EXECUTOR_REGISTRY.get((region, factory))


class _StubPlan(V2BundleGraphPlanMarker):
    """V2 marker plan carrying a custom BundleGraphSpec."""

    _spec: BundleGraphSpec

    def __init__(self, spec: BundleGraphSpec) -> None:
        self._spec = spec

    def get_bundle_graph_spec(self) -> BundleGraphSpec:
        return self._spec


class _InnerResolver:
    """Resolves bundles/think_reason.yaml to the loaded inner spec,
    wrapped in a v2 marker plan."""

    def __init__(self, inner_spec: BundleGraphSpec) -> None:
        self._plan = _StubPlan(inner_spec)

    def resolve(self, plan_ref: str) -> Any:
        if plan_ref == "bundles/think_reason.yaml":
            return self._plan
        return None


class TestThinkSubgraphE2E:
    """End-to-end: think subgraph runs all 5 outer nodes."""

    @pytest.mark.asyncio
    async def test_full_reason_path_runs_through_classify(self) -> None:
        """End-to-end: the outer 5-node think graph with the inner
        sub_spec_ref at think.reason runs cleanly through the full
        3-node reason subgraph (plan + render + complete) and
        produces a PhaseOutput whose Decision.action_type is
        'respond' (from the default classifier).
        """
        from lca.harness.declarative.compile.subgraph_resolver import (
            _load_bundle_graph_spec,
        )

        outer_spec = _load_bundle_graph_spec("bundles/think.yaml")
        reason_node = next(n for n in outer_spec.nodes if n.id == "think.reason")
        assert reason_node.sub_spec_ref is not None
        assert reason_node.sub_spec_ref.plan_ref == "bundles/think_reason.yaml"

        # The inner resolver returns the inner spec; the runner
        # walks the full 3-node inner subgraph through plan → render
        # → complete, then the outer driver advances via the declared
        # think.reason → think.classify → think.gate edges.
        inner_spec = _load_bundle_graph_spec("bundles/think_reason.yaml")
        runner = SubgraphRunner(
            resolver=_InnerResolver(inner_spec),
            runtime=_DefaultSubgraphRuntime(),
            channel_factory=InMemoryPhaseOutputChannel,
        )

        inner_ref = SubgraphReference(
            plan_ref="bundles/think_reason.yaml",
            entry_node="think.reason.plan",
            binding_edge="think.reason",
        )
        _state_after, output = await runner.run(
            ref=inner_ref,
            outer_state=_state(),
            channel=InMemoryPhaseOutputChannel(),
        )
        assert output.outcome_kind is None
        assert output.error is None

    @pytest.mark.asyncio
    async def test_observer_sees_node_start_and_end_events(self) -> None:
        """The Session.append observer fires for phase_graph.node.start/end
        on every inner node. End-to-end through the full think path.
        """
        from lca.harness.declarative.compile.subgraph_resolver import (
            _load_bundle_graph_spec,
        )

        captured: list[tuple[str, dict[str, Any]]] = []

        async def recording_observer(event: str, payload: dict[str, Any]) -> None:
            captured.append((event, payload))

        inner_spec = _load_bundle_graph_spec("bundles/think_reason.yaml")
        runner = SubgraphRunner(
            resolver=_InnerResolver(inner_spec),
            runtime=_DefaultSubgraphRuntime(),
            channel_factory=InMemoryPhaseOutputChannel,
            observers=(recording_observer,),
        )
        inner_ref = SubgraphReference(
            plan_ref="bundles/think_reason.yaml",
            entry_node="think.reason.plan",
            binding_edge="think.reason",
        )
        _state_after, _output = await runner.run(
            ref=inner_ref,
            outer_state=_state(),
            channel=InMemoryPhaseOutputChannel(),
        )
        # The inner think_reason graph has 3 nodes (plan, render,
        # complete); each produces a start + end event = 6 events.
        events = [e for e, _ in captured]
        assert events == [
            "phase_graph.node.start",
            "phase_graph.node.end",
            "phase_graph.node.start",
            "phase_graph.node.end",
            "phase_graph.node.start",
            "phase_graph.node.end",
        ]
        end_payloads = [p for e, p in captured if e == "phase_graph.node.end"]
        assert len(end_payloads) == 3
        assert all("node_id" in p for p in end_payloads)
