"""End-to-end HITL loop: askUserQuestion → pause → answer → resume.

Exercises the full chain without LLM or server:

1. ``_compose()`` with askUserQuestion tool_calls → needs_approval=True
2. ``ApproveGateExecutor`` → routes to intervene.interrupt
3. ``InterruptExecutor`` → Command + should_terminate=True
4. ``_pause_from_interrupt()`` detects pause signal
5. ``_paused_outcome_parts()`` builds approval_request with questions
6. ``HumanAnswerResumeInputAdapter.normalize()`` folds answer into state
7. ``EventTranslator._spine_close()`` emits waiting_input WS events

Pins the contract that ties these pieces together so a future change
to any step fails this test rather than silently breaking the loop.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.conversation.llm import LLMResponse, NativeToolCall
from lca.contracts.models.core.execution.decision import (
    Decision,
    ToolCall,
    requires_human_input,
)
from lca.contracts.models.core.state.plane import PlaneBindings, PlaneKind, PlaneRef
from lca.contracts.protocols.graph.command import Command
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.infrastructure.runtime_plane.access.classify import machine_calls_need_approval
from lca.infrastructure.runtime_plane.bindings.bindings import plane_bindings_scope
from lca.loop.driver import _pause_from_interrupt, _paused_outcome_parts
from lca.nodes.concept.decision_classify.compose_action import _compose
from lca.nodes.intervene.approve_gate import ApproveGateExecutor
from lca.nodes.intervene.interrupt import InterruptExecutor
from lca.plugins.gate.decision_classifier_provider import DefaultDecisionClassifier
from lca.runtime.support.resume_input import HumanAnswerResumeInputAdapter


def _tool_call_response(name: str, arguments: dict[str, object]) -> LLMResponse:
    """A native function-calling response carrying one tool call."""
    return LLMResponse(
        text="",
        finish_reason="tool_calls",
        tool_calls=[NativeToolCall(call_id="c-native", name=name, arguments=arguments)],
    )


_QUESTIONS = [
    {
        "question": "Which color?",
        "header": "Color",
        "options": [
            {"label": "Red", "description": "red"},
            {"label": "Blue", "description": "blue"},
        ],
    }
]


def _ask_decision() -> Decision:
    """Decision produced by _compose when the LLM calls askUserQuestion."""
    return _compose(
        tool_calls=(
            ToolCall(
                call_id="tc-1",
                tool_name="askUserQuestion",
                arguments={"questions": _QUESTIONS},
            ),
        ),
        delegations=(),
        intent="",
    )


class TestStep1ComposeSetsNeedsApproval:
    """_compose recognises askUserQuestion and sets needs_approval=True."""

    def test_ask_user_question_sets_needs_approval(self) -> None:
        decision = _ask_decision()
        assert decision.needs_approval is True
        assert decision.action_type == ActionType.USE_TOOL.value
        assert len(decision.tool_calls) == 1
        assert decision.tool_calls[0].tool_name == "askUserQuestion"

    def test_regular_tool_does_not_set_needs_approval(self) -> None:
        decision = _compose(
            tool_calls=(
                ToolCall(
                    call_id="tc-2",
                    tool_name="bash",
                    arguments={"command": "echo hi"},
                ),
            ),
            delegations=(),
            intent="",
        )
        assert decision.needs_approval is False

    def test_requires_human_input_predicate(self) -> None:
        calls = (ToolCall(call_id="c", tool_name="askUserQuestion", arguments={}),)
        assert requires_human_input(calls) is True
        calls = (ToolCall(call_id="c", tool_name="bash", arguments={}),)
        assert requires_human_input(calls) is False
        assert requires_human_input(None) is False
        assert requires_human_input([]) is False


class TestStep2ApproveGateRoutesToInterrupt:
    """approve_gate sends needs_approval=True (no command) to intervene.interrupt."""

    @pytest.mark.asyncio
    async def test_interrupt_routing(self) -> None:
        gate = ApproveGateExecutor()
        decision = _ask_decision()
        ctx = SimpleNamespace()
        node_input = SimpleNamespace(port_values={"decision": decision, "command": None})
        output = await gate.node_execute(ctx, node_input)
        routing = output.port_values["approval_routing"]
        assert routing.next_hint == "approve_interrupt"
        assert routing.next_node == "intervene.interrupt"

    @pytest.mark.asyncio
    async def test_skipped_for_regular_tool(self) -> None:
        gate = ApproveGateExecutor()
        decision = _compose(
            tool_calls=(ToolCall(call_id="tc", tool_name="bash", arguments={}),),
            delegations=(),
            intent="",
        )
        ctx = SimpleNamespace()
        node_input = SimpleNamespace(port_values={"decision": decision, "command": None})
        output = await gate.node_execute(ctx, node_input)
        routing = output.port_values["approval_routing"]
        assert routing.next_hint == "approve_skipped"
        assert routing.next_node == "act.envelope"


class TestStep3InterruptEmitsTerminate:
    """interrupt creates Command + should_terminate=True."""

    @pytest.mark.asyncio
    async def test_interrupt_output(self) -> None:
        interrupt = InterruptExecutor()
        decision = _ask_decision()
        ctx = SimpleNamespace()
        node_input = SimpleNamespace(port_values={"decision": decision, "spine_seq": 42})
        output = await interrupt.node_execute(ctx, node_input)
        cmd = output.port_values["command"]
        routing = output.port_values["routing"]
        assert isinstance(cmd, Command)
        assert cmd.kind == "approve"
        assert cmd.payload["decision_id"] == decision.decision_id
        assert cmd.issued_at_seq == 42
        assert routing.should_terminate is True
        assert routing.next_hint == "intervene.resume"


class TestStep4PauseDetection:
    """_pause_from_interrupt scans visits and extracts the pause signal."""

    def test_pause_detected(self) -> None:
        decision = _ask_decision()
        routing = RoutingDecision(
            action_type=ActionType.ASK_HUMAN,
            should_terminate=True,
            next_hint="intervene.resume",
        )
        visits = (
            SimpleNamespace(
                node_id="intervene.interrupt",
                outputs={"decision": decision, "routing": routing},
            ),
        )
        pause = _pause_from_interrupt(visits)
        assert pause is not None
        assert pause["node_id"] == "intervene.interrupt"
        assert pause["decision"] is decision


class TestStep5ApprovalRequestShape:
    """_paused_outcome_parts builds the approval_request with questions."""

    def test_approval_request_contains_questions(self) -> None:
        decision = _ask_decision()
        routing = RoutingDecision(
            action_type=ActionType.ASK_HUMAN,
            should_terminate=True,
            next_hint="intervene.resume",
        )
        visits = (
            SimpleNamespace(
                node_id="intervene.interrupt",
                outputs={"decision": decision, "routing": routing},
            ),
        )
        pause = _pause_from_interrupt(visits)
        assert pause is not None
        _stop, cursor, approval = _paused_outcome_parts(pause, plan_ref="plan-1", visits=visits)
        assert approval["type"] == "ask_user_question"
        assert approval["questions"] == _QUESTIONS
        assert approval["approval_id"] == "plan-1:intervene.interrupt:1"
        assert cursor.node_id == "perceive.main"
        assert cursor.plan_ref == "plan-1"


class TestStep6ResumeInputNormalization:
    """HumanAnswerResumeInputAdapter folds the answer into a typed Turn."""

    def test_answer_normalization(self) -> None:
        adapter = HumanAnswerResumeInputAdapter()
        result = adapter.normalize("Red")
        assert result.input_value == "Red"
        assert result.turn is not None
        assert result.turn.decision.action_type == ActionType.ASK_HUMAN.value
        assert result.turn.observation.success is True
        assert result.turn.observation.payload == "Red"
        assert result.turn.observation.extra["source"] == "human_answer"
        assert result.turn.observation.extra["tool_name"] == "askUserQuestion"

    def test_none_input_passes_through(self) -> None:
        adapter = HumanAnswerResumeInputAdapter()
        result = adapter.normalize(None)
        assert result.input_value is None
        assert result.turn is None


class TestStep7EventTranslation:
    """EventTranslator emits step_start(human_approval) + agent_runtime_end on pause."""

    def test_spine_close_waiting_input(self) -> None:
        from lca.application.runtime.coordinator.event_translator import EventTranslator

        event = {
            "type": "SpineClose",
            "final_state": {"status": "waiting_input"},
            "reason": "waiting_input",
            "pending_tools_calling": [
                {"identifier": "lobe-user-interaction", "apiName": "askUserQuestion"}
            ],
        }
        result = EventTranslator._spine_close(event)
        assert isinstance(result, list)
        assert len(result) == 2
        step_start = result[0]
        runtime_end = result[1]
        assert step_start["type"] == "step_start"
        assert step_start["data"]["phase"] == "human_approval"
        assert step_start["data"]["requiresApproval"] is True
        assert runtime_end["type"] == "agent_runtime_end"
        assert runtime_end["data"]["reason"] == "waiting_input"

    def test_spine_close_completed(self) -> None:
        from lca.application.runtime.coordinator.event_translator import EventTranslator

        event = {
            "type": "SpineClose",
            "final_state": {"status": "done"},
            "reason": "completed",
        }
        result = EventTranslator._spine_close(event)
        assert isinstance(result, dict)
        assert result["type"] == "agent_runtime_end"
        assert result["data"]["reason"] == "completed"


class TestFullLoopIntegration:
    """Full chain: compose → gate → interrupt → pause → approval_request → resume."""

    @pytest.mark.asyncio
    async def test_ask_pause_resume_chain(self) -> None:
        # Step 1: LLM calls askUserQuestion → compose sets needs_approval
        decision = _ask_decision()
        assert decision.needs_approval is True

        # Step 2: approve_gate routes to interrupt
        gate = ApproveGateExecutor()
        gate_output = await gate.node_execute(
            SimpleNamespace(),
            SimpleNamespace(port_values={"decision": decision, "command": None}),
        )
        gate_routing = gate_output.port_values["approval_routing"]
        assert gate_routing.next_hint == "approve_interrupt"

        # Step 3: interrupt emits Command + terminate
        interrupt = InterruptExecutor()
        interrupt_output = await interrupt.node_execute(
            SimpleNamespace(),
            SimpleNamespace(port_values={"decision": decision, "spine_seq": 10}),
        )
        cmd = interrupt_output.port_values["command"]
        assert isinstance(cmd, Command)
        routing = interrupt_output.port_values["routing"]
        assert routing.should_terminate is True

        # Step 4: driver detects pause
        visit = SimpleNamespace(
            node_id="intervene.interrupt",
            outputs={
                "decision": decision,
                "routing": routing,
                "command": cmd,
            },
        )
        pause = _pause_from_interrupt((visit,))
        assert pause is not None

        # Step 5: approval_request carries questions
        _, cursor, approval = _paused_outcome_parts(pause, plan_ref="plan-x", visits=(visit,))
        assert approval["questions"] == _QUESTIONS
        assert cursor.node_id == "perceive.main"

        # Step 6: user answer folds into resume input
        adapter = HumanAnswerResumeInputAdapter()
        resume_input = adapter.normalize("Blue")
        assert resume_input.turn is not None
        assert resume_input.turn.observation.payload == "Blue"

        # Step 7: WS events carry the pause to frontend
        from lca.application.runtime.coordinator.event_translator import EventTranslator

        events = EventTranslator._spine_close(
            {
                "final_state": {"status": "waiting_input"},
                "reason": "waiting_input",
                "pending_tools_calling": [],
            }
        )
        assert isinstance(events, list)
        assert events[0]["data"]["phase"] == "human_approval"
        assert events[1]["data"]["reason"] == "waiting_input"


_MACHINE_ROOT = "F:\\下载"
_MACHINE_HOME = "C:\\Users\\li"
_SSH_KEY = "C:\\Users\\li\\.ssh\\id_rsa"
_HOME_CONFIG = (
    "C:\\Users\\li\\AppData\\Roaming\\io.github.clash-verge-rev.clash-verge-rev\\verge.yaml"
)


def _machine_bindings() -> PlaneBindings:
    return PlaneBindings(
        primary=PlaneRef(
            id="m-lipcmain",
            label="lipcmain",
            kind=PlaneKind.MACHINE,
            root=_MACHINE_ROOT,
            outputs_dir=f"{_MACHINE_ROOT}\\outputs",
            platform="Windows",
            home=_MACHINE_HOME,
        )
    )


def _machine_decision(path: str) -> Decision:
    return _compose(
        tool_calls=(
            ToolCall(call_id="tc-m", tool_name="local_readFile", arguments={"path": path}),
        ),
        delegations=(),
        intent="",
    )


class TestMachineAccessConsentChain:
    """A machine call the access policy gates reaches intervene.interrupt.

    This is the consent half of ADR-0246 §1.1. Authorization decides the
    verdict; the graph pause carries it. The run must not fail silently the way
    run_5fd426ea0367 did.
    """

    def test_credential_read_sets_needs_approval(self) -> None:
        with plane_bindings_scope(_machine_bindings()):
            assert _machine_decision(_SSH_KEY).needs_approval is True

    def test_read_inside_grant_does_not_pause(self) -> None:
        with plane_bindings_scope(_machine_bindings()):
            assert _machine_decision(_HOME_CONFIG).needs_approval is False

    def test_no_bound_plane_means_no_machine_opinion(self) -> None:
        assert _machine_decision(_SSH_KEY).needs_approval is False

    def test_sandbox_plane_does_not_gate_twice(self) -> None:
        sandbox = PlaneBindings(
            primary=PlaneRef(
                id="sb-1",
                label="Onlyboxes",
                kind=PlaneKind.SANDBOX,
                root="/mnt/data",
                outputs_dir="/mnt/data/outputs",
            )
        )
        with plane_bindings_scope(sandbox):
            decision = _compose(
                tool_calls=(
                    ToolCall(
                        call_id="tc-s",
                        tool_name="readFile",
                        arguments={"path": "/etc/passwd"},
                    ),
                ),
                delegations=(),
                intent="",
            )
        assert decision.needs_approval is False

    @pytest.mark.asyncio
    async def test_gated_machine_call_routes_to_interrupt(self) -> None:
        with plane_bindings_scope(_machine_bindings()):
            decision = _machine_decision(_SSH_KEY)
        output = await ApproveGateExecutor().node_execute(
            SimpleNamespace(),
            SimpleNamespace(port_values={"decision": decision, "command": None}),
        )
        routing = output.port_values["approval_routing"]
        assert routing.next_hint == "approve_interrupt"
        assert routing.next_node == "intervene.interrupt"

    @pytest.mark.asyncio
    async def test_allowed_machine_call_routes_to_envelope(self) -> None:
        with plane_bindings_scope(_machine_bindings()):
            decision = _machine_decision(_HOME_CONFIG)
        output = await ApproveGateExecutor().node_execute(
            SimpleNamespace(),
            SimpleNamespace(port_values={"decision": decision, "command": None}),
        )
        routing = output.port_values["approval_routing"]
        assert routing.next_hint == "approve_skipped"
        assert routing.next_node == "act.envelope"

    def test_all_three_producers_classify_identically(self) -> None:
        calls = (
            ToolCall(call_id="tc-m", tool_name="local_readFile", arguments={"path": _SSH_KEY}),
        )
        with plane_bindings_scope(_machine_bindings()):
            assert requires_human_input(calls) is False
            assert machine_calls_need_approval(calls) is True
            assert (
                DefaultDecisionClassifier()
                .classify(_tool_call_response("local_readFile", {"path": _SSH_KEY}))
                .needs_approval
                is True
            )
