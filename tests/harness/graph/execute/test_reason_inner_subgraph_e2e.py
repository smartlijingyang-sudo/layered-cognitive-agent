"""think.reason inner_graph end-to-end driver test (ADR-0217 §3.3, PR-3).

Loads the real ``bundles/think_reason.yaml`` and runs the
:class:`NodeGraphDriver` through all three nodes (plan → render →
complete) against the real 3 executors + a stub ``Reasoner``. Verifies:

1. yaml loads cleanly (no PG-005 schema/structure failures).
2. driver walks plan → render → complete in order.
3. emit_on_enter / emit_on_exit EPs fire in spec-declared order
   (matching ``bundles/think_reason.yaml`` config):
     - plan.enter=[]  → no enter EP
     - plan.exit=[]   → no exit EP
     - render.enter=[] → no enter EP
     - render.exit=[prompt_assembler_end, reasoner_meta] → 2 EPs
     - complete.enter=[reasoner_reason_start] → 1 EP
     - complete.exit=[reasoner_reason_end] → 1 EP
   Total: 4 EPs across 3 nodes (3 routed via ``emit_for_node`` +
   1 routed via ``emit_reasoner_meta_for_node``).
4. Port ``response`` reaches the channel ``PhaseOutput.response``
   (same-named passthrough to outer; ADR-0217 §3.3.3 铁律 1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import pytest

from lca.contracts.models.cognition.reasoner_turn import (
    ReasonerTurnPlan,
    ReasonerTurnRender,
)
from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.framework.subgraph.plugins.channel import (
    InMemoryPhaseOutputChannel,
    PhaseOutput,
)
from lca.framework.subgraph.plugins.node_graph_driver import NodeGraphDriver
from lca.harness.declarative.compile.subgraph_resolver import (
    BundleSubgraphResolver,
    _load_bundle_graph_spec,
)
from lca.plugins.think.reason.complete import ThinkReasonCompleteExecutor
from lca.plugins.think.reason.plan import ThinkReasonPlanExecutor
from lca.plugins.think.reason.render import ThinkReasonRenderExecutor

INNER_BUNDLE = "bundles/think_reason.yaml"


def _state() -> AgentState:
    return AgentState(trace_id="trace:reason-inner-e2e", task="test", budget=Budget())


def _plan() -> ReasonerTurnPlan:
    return ReasonerTurnPlan(
        state_id="t",
        template_id="react",
        decision_path="legacy",
        activated_skill_ids=(),
        tools_count=0,
        available_skills_count=0,
        sections_preview=(),
        variant_preview=None,
    )


def _render() -> ReasonerTurnRender:
    return ReasonerTurnRender(
        prompt="p",
        trace=None,
        section_count=0,
        manifest=None,
        activated_skill_ids=(),
        section_outputs=None,
        total_chars=None,
        variant=None,
    )


def _response() -> LLMResponse:
    return LLMResponse(text="hi", tool_calls=())


def _stub_role_profile() -> Any:
    from lca.contracts.models.team.role.team import (
        RoleProfile,
        ToolPermissionManifest,
    )

    return RoleProfile(
        role="assistant",
        goal="answer",
        backstory="b",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )


@dataclass
class _StubReasoner:
    """Duck-typed: implements the three methods the 3 executors call.

    ADR-0220 P4: ``render_turn`` now takes typed boundary DTOs
    ``(context, template, role)``; we expose ``role_profile`` so the
    ``phase.think.reason.render`` adapter can build ``RoleSnapshot``.
    """

    plan: ReasonerTurnPlan = field(default_factory=_plan)
    render: ReasonerTurnRender = field(default_factory=_render)
    response: LLMResponse = field(default_factory=_response)
    calls: list[str] = field(default_factory=list)
    role_profile: Any = field(default_factory=_stub_role_profile)

    def build_turn_plan(self, state: AgentState) -> ReasonerTurnPlan:
        self.calls.append("build_turn_plan")
        return self.plan

    def render_turn(
        self,
        context: Any,
        template: Any,
        role: Any,
    ) -> ReasonerTurnRender:
        self.calls.append("render_turn")
        return self.render

    async def complete_turn(self, state: AgentState, render: ReasonerTurnRender) -> LLMResponse:
        self.calls.append("complete_turn")
        return self.response


class _StubScope:
    """Minimal SubgraphRuntime scope — exposes ``resolve`` + ``resolve_factory``.

    The driver's ``build_node_context`` reads capabilities via
    ``scope.resolve(key)`` (defaults to ``None`` on miss). The executor
    wrapping layer overrides ``runtime.reasoner`` after the fact, so the
    capability exposed here is the *real* reasoner for assertion purposes.
    """

    def __init__(self, reasoner: _StubReasoner) -> None:
        self._reasoner = reasoner
        self._executors: dict[str, Any] = {
            "think.reason.plan": ThinkReasonPlanExecutor(),
            "think.reason.render": ThinkReasonRenderExecutor(),
            "think.reason.complete": ThinkReasonCompleteExecutor(),
        }

    def resolve(self, capability: str) -> Any:
        # Match ``_try_resolve`` semantics: raise on unknown so the
        # factory returns None cleanly. We only need reasoner here.
        if capability == "reasoner":
            return self._reasoner
        raise KeyError(capability)

    def resolve_factory(self, factory: str, region: str | None) -> Any:
        ex = self._executors.get(factory)
        if ex is None:
            raise LookupError(f"no stub executor for factory={factory!r}")
        return ex


def _build_driver(reasoner: _StubReasoner) -> NodeGraphDriver:
    """Resolve the inner bundle and build a driver pointed at it."""
    spec = _load_bundle_graph_spec(INNER_BUNDLE)
    return NodeGraphDriver(
        spec=spec,
        plan_ref=INNER_BUNDLE,
        scope=_StubScope(reasoner),
    )


class TestInnerSubgraphE2E:
    """End-to-end run of the inner graph spec via the production driver."""

    def test_yaml_resolves_via_resolver(self) -> None:
        """Step 1:yaml loads & resolves through the production resolver."""
        resolver = BundleSubgraphResolver()
        plan = resolver.resolve(INNER_BUNDLE)
        assert plan is not None

    def test_yaml_has_three_nodes_and_two_edges(self) -> None:
        """Step 1 cont'd:spec shape is 3 nodes + 2 edges + entry=plan."""
        spec = _load_bundle_graph_spec(INNER_BUNDLE)
        assert len(spec.nodes) == 3
        assert len(spec.edges) == 2
        # entry defaults to first node when not declared
        assert spec.entry in (None, "think.reason.plan")
        ids = {n.id for n in spec.nodes}
        assert ids == {
            "think.reason.plan",
            "think.reason.render",
            "think.reason.complete",
        }
        # factory values match executor ``semantic_name``
        factories = {n.factory for n in spec.nodes}
        assert factories == {
            "think.reason.plan",
            "think.reason.render",
            "think.reason.complete",
        }

    @pytest.mark.asyncio
    async def test_inner_driver_walks_all_three_nodes_in_order(self) -> None:
        """Step 2:driver walks plan → render → complete with the real executors.

        Uses a scope that returns a stub Reasoner via ``resolve("reasoner")``
        so the real executors (think.reason.plan/render/complete) call into
        the stub and the call order can be asserted end-to-end.
        """
        reasoner = _StubReasoner()
        driver = _build_driver(reasoner)
        channel = InMemoryPhaseOutputChannel()
        state = _state()

        result = await driver.run(
            outer_state=state,
            channel=channel,
            artifacts={},
            outer_input=None,
        )

        # Visit order:plan → render → complete
        node_ids = [v.node_id for v in result.visits]
        assert node_ids == [
            "think.reason.plan",
            "think.reason.render",
            "think.reason.complete",
        ]
        # Reasoner methods invoked in order
        assert reasoner.calls == [
            "build_turn_plan",
            "render_turn",
            "complete_turn",
        ]

    @pytest.mark.asyncio
    async def test_inner_driver_publishes_response_port_to_channel(self) -> None:
        """Step 4:port ``response`` reaches the channel PhaseOutput.

        The terminal node (``think.reason.complete``) emits
        ``port_values={"response": LLMResponse}``; the driver's terminal
        projection writes it into ``PhaseOutput.response`` on the channel
        — same-named passthrough (ADR-0217 §3.3.3 铁律 1).
        """
        reasoner = _StubReasoner()
        driver = _build_driver(reasoner)
        channel = InMemoryPhaseOutputChannel()
        state = _state()

        await driver.run(
            outer_state=state,
            channel=channel,
            artifacts={},
            outer_input=None,
        )

        snapshot = channel.snapshot()
        assert len(snapshot) == 1
        output = next(iter(snapshot.values()))
        assert isinstance(output, PhaseOutput)
        assert output.response is reasoner.response

    @pytest.mark.asyncio
    async def test_inner_driver_fires_node_emits_per_config(self) -> None:
        """Step 3:node-level emit dispatcher fires EPs in spec-declared order.

        4 EPs total per ``bundles/think_reason.yaml``:

          - think.reason.plan: enter=[], exit=[]
          - think.reason.render: enter=[], exit=[prompt_assembler_end, reasoner_meta]
          - think.reason.complete: enter=[reasoner_reason_start], exit=[reasoner_reason_end]

        ``emit_for_node`` is called 3× (reasoner_reason_start,
        prompt_assembler_end, reasoner_reason_end). ``reasoner_meta``
        bypasses ``emit_for_node`` (it has a separate helper that takes
        ``plan`` + ``render`` parameters) and is patched separately.
        """
        reasoner = _StubReasoner()
        driver = _build_driver(reasoner)
        channel = InMemoryPhaseOutputChannel()
        state = _state()

        with (
            patch(
                "lca.framework.subgraph.plugins.node_graph_driver.emit_for_node",
                autospec=True,
            ) as emit,
            patch(
                "lca.framework.subgraph.plugins.node_graph_driver.emit_reasoner_meta_for_node",
                autospec=True,
            ) as emit_meta,
        ):
            await driver.run(
                outer_state=state,
                channel=channel,
                artifacts={},
                outer_input=None,
            )

        # Order:render.exit(prompt_assembler_end; reasoner_meta routes
        # via a separate helper) → complete.enter(reasoner_reason_start)
        # → complete.exit(reasoner_reason_end).
        ep_calls = [call.args[0] for call in emit.call_args_list]
        assert ep_calls == [
            "prompt_assembler_end",
            "reasoner_reason_start",
            "reasoner_reason_end",
        ]
        # ``reasoner_meta`` EP fired via its dedicated helper once.
        assert emit_meta.call_count == 1
        plan_arg = emit_meta.call_args.args[1]
        render_arg = emit_meta.call_args.args[2]
        assert plan_arg is reasoner.plan
        assert render_arg is reasoner.render
