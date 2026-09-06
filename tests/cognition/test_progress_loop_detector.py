"""ProgressLoopDetector unit tests."""

from __future__ import annotations

import pytest

from lca.cognition.brain.decision_gates.progress.loop_detector import ProgressLoopDetector
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.decision import Decision, Observation, ToolCall, Turn
from lca.contracts.models.core.state.state import AgentState, Budget


def _listfiles_turn(*, directory: str, stdout: str, decision_id: str) -> Turn:
    return Turn(
        decision=Decision(
            decision_id=decision_id,
            action_type=ActionType.USE_TOOL,
            rationale="list",
            confidence=0.9,
            tool_calls=[
                ToolCall(
                    call_id=f"{decision_id}-call",
                    tool_name="listFiles",
                    arguments={"directoryPath": directory},
                )
            ],
        ),
        observation=Observation(
            observation_id=f"{decision_id}-obs",
            success=True,
            payload={"stdout": stdout},
        ),
    )


@pytest.mark.asyncio
async def test_successful_inspect_with_delivery_does_not_count_as_no_progress() -> None:
    """Successful listFiles with substantive output breaks the no-progress streak."""
    substantive = '[{"name": "a.txt", "type": "file"}, {"name": "b.txt", "type": "file"}]'
    state = AgentState(trace_id="t", task="list once", budget=Budget())
    state.history.append(_listfiles_turn(directory=".", stdout=substantive, decision_id="d0"))

    detector = ProgressLoopDetector()
    assert detector._count_consecutive_no_progress(state) == 0


@pytest.mark.asyncio
async def test_repeated_empty_inspect_results_count_as_no_progress() -> None:
    state = AgentState(trace_id="t", task="poll", budget=Budget())
    for index in range(4):
        state.history.append(
            _listfiles_turn(directory=".", stdout="", decision_id=f"d{index}")
        )

    detector = ProgressLoopDetector()
    assert detector._count_consecutive_no_progress(state) == 4


@pytest.mark.asyncio
async def test_stall_after_delivery_counts_non_producer_tools() -> None:
    substantive = '[{"name": "a.txt", "type": "file"}, {"name": "b.txt", "type": "file"}]'
    state = AgentState(trace_id="t", task="list once", budget=Budget())
    state.history.append(_listfiles_turn(directory=".", stdout=substantive, decision_id="d0"))
    state.history.append(_listfiles_turn(directory=".", stdout=substantive, decision_id="d1"))

    detector = ProgressLoopDetector()
    assert detector._count_producer_stall_after_delivery(state) == 1
