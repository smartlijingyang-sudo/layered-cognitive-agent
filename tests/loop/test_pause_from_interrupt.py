"""Driver pause translation: interrupt-terminal visits become a paused outcome.

``PlanInterpreter`` stops at ``RoutingDecision(should_terminate=True)``;
``DeclarativeExecution`` must then translate that terminal into a PAUSED
outcome (approval_request + durable cursor) instead of falling through
to the ERROR→FAILED stop-decision path. Otherwise the run dies right
after issuing the pause (inline resume → empty fanout → FAILED).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.decision import Decision, ToolCall
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.loop.driver import _pause_from_interrupt, _paused_outcome_parts


def _pause_visit(node_id: str = "intervene.interrupt", occurrence: int = 1):
    decision = Decision(
        decision_id="dec-1",
        action_type=ActionType.USE_TOOL.value,
        rationale="",
        confidence=1.0,
        tool_calls=[
            ToolCall(
                call_id="c1",
                tool_name="askUserQuestion",
                arguments={
                    "questions": [
                        {
                            "question": "Which color?",
                            "header": "Color",
                            "options": [
                                {"label": "Red", "description": "red"},
                                {"label": "Blue", "description": "blue"},
                            ],
                        }
                    ]
                },
            )
        ],
        needs_approval=True,
    )
    routing = RoutingDecision(
        action_type=ActionType.ASK_HUMAN,
        should_terminate=True,
        next_hint="intervene.resume",
    )
    visits = tuple(
        SimpleNamespace(node_id=node_id, outputs={"decision": decision, "routing": routing})
        for _ in range(occurrence)
    )
    return visits, decision


def test_pause_detected_with_decision_and_occurrence() -> None:
    visits, decision = _pause_visit(occurrence=2)
    pause = _pause_from_interrupt(visits)
    assert pause is not None
    assert pause["node_id"] == "intervene.interrupt"
    assert pause["occurrence"] == 2
    assert pause["decision"] is decision


def test_control_stop_verdict_is_not_a_pause() -> None:
    """Loop-control STOP verdicts keep the existing stop-decision path."""
    visits = (
        SimpleNamespace(
            node_id="think.guard",
            outputs={
                "routing": RoutingDecision(
                    action_type=ActionType.RESPOND,
                    should_terminate=True,
                    next_hint="stop",
                )
            },
        ),
    )
    assert _pause_from_interrupt(visits) is None


def test_no_routing_is_not_a_pause() -> None:
    visits = (SimpleNamespace(node_id="act.envelope", outputs={"envelope": {}}),)
    assert _pause_from_interrupt(visits) is None
    assert _pause_from_interrupt(()) is None


def test_paused_parts_shape() -> None:
    """stop/cursor/approval_request satisfy the finalizer's PAUSED contract."""
    visits, _ = _pause_visit()
    pause = _pause_from_interrupt(visits)
    assert pause is not None
    stop, cursor, approval = _paused_outcome_parts(pause, plan_ref="plan-1", visits=visits)
    assert stop.status is None
    assert cursor.node_id == "perceive.main"
    assert cursor.plan_ref == "plan-1"
    assert approval["approval_id"] == "plan-1:intervene.interrupt:1"
    assert approval["type"] == "ask_user_question"
    assert approval["questions"][0]["question"] == "Which color?"


def test_paused_parts_tolerate_missing_questions() -> None:
    decision = Decision(
        decision_id="dec-2",
        action_type=ActionType.USE_TOOL.value,
        rationale="",
        confidence=1.0,
        tool_calls=[ToolCall(call_id="c9", tool_name="askUserQuestion", arguments={})],
        needs_approval=True,
    )
    visits = (
        SimpleNamespace(
            node_id="intervene.interrupt",
            outputs={
                "routing": RoutingDecision(
                    action_type=ActionType.ASK_HUMAN,
                    should_terminate=True,
                    next_hint="intervene.resume",
                ),
                "decision": decision,
            },
        ),
    )
    pause = _pause_from_interrupt(visits)
    assert pause is not None
    _, _, approval = _paused_outcome_parts(pause, plan_ref="p", visits=visits)
    assert approval["questions"] == []


@pytest.mark.asyncio
async def test_execute_translates_interrupt_terminal_to_paused() -> None:
    """End of driver.execute with a pause visit: PAUSED kind + approval triple.

    Regression for the mutable-default crash: the outcome shim must
    construct with a dict approval_request (only present on pause).
    """
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    from lca.contracts.models.core.state.state import AgentState, Budget
    from lca.loop.driver import DeclarativeExecution

    visits, _ = _pause_visit()
    interpretation = SimpleNamespace(
        output={},
        visits=visits,
        terminal_node="intervene.interrupt",
        facts=(),
    )

    async def _fake_run(*args: object, **kwargs: object) -> object:
        return interpretation

    bindings = MagicMock()
    bindings.require_executable_plan.return_value = SimpleNamespace(bundles=())
    bindings.plan_ref.return_value = "plan-1"
    bindings.new_interpreter.return_value = SimpleNamespace(run=_fake_run)
    journal = SimpleNamespace(sequence=9)
    seen: dict[str, object] = {}

    async def _fake_finalize(
        *, interpretation: object, plan_ref: str, journal_sequence: int
    ) -> object:
        seen["outcome"] = interpretation.outcome  # type: ignore[attr-defined]
        return SimpleNamespace(status="paused-stub")

    finalizer = SimpleNamespace(finalize=_fake_finalize)
    driver = DeclarativeExecution(bindings, journal=journal, result_finalizer=finalizer)
    with patch("lca.framework.graph.lifter.lift_graph_spec", return_value=object()):
        await driver.execute(AgentState(trace_id="t", task="q", budget=Budget()))

    from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
        ExecutionOutcome,
    )

    outcome = seen["outcome"]
    assert outcome.kind is ExecutionOutcome.PAUSED
    assert outcome.approval_request["approval_id"] == "plan-1:intervene.interrupt:1"
    assert outcome.cursor.node_id == "perceive.main"
    assert outcome.stop.status is None
