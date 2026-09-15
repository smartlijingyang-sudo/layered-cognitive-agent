"""Tests for region.plan.compose plugin.

Verifies the typed ``plan.compose`` node that seeds ``TaskList`` on
first entry (ADR-0228 §Decision 3). The compose node is a pure
port-to-port transform: no runtime capability, no state mutation,
typed ``task_list`` output.
"""

from __future__ import annotations

import pytest

from lca.contracts.models.cognition.task import (
    TaskEntry,
    TaskId,
    TaskList,
)
from lca.contracts.models.core.execution.decision import Decision, Observation
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.nodes.plan.compose.compose import (
    PlanComposeExecutor,
    _compose_entries,
    _short_task_id,
)


def _ctx() -> NodeContext:
    """Minimal NodeContext; plan.compose does not read runtime."""
    return NodeContext(runtime={}, budget={}, metadata={})


def _decision(action_type: str = "use_tool", objective: str = "X") -> Decision:
    return Decision(
        decision_id="d-1",
        action_type=action_type,
        rationale=objective,
        confidence=0.9,
    )


def _observation() -> Observation:
    return Observation(observation_id="o-1", success=True, payload="")


def _agent_state(*, step: int = 0, task_list: TaskList | None = None) -> AgentState:
    return AgentState(
        trace_id="trace-1",
        task="root",
        budget=Budget(),
        step=step,
        task_list=task_list or TaskList(),
    )


@pytest.mark.asyncio
async def test_compose_seeds_single_entry_on_empty_state() -> None:
    """Empty state.task_list + decision → emit one pending entry."""
    executor = PlanComposeExecutor()
    state = _agent_state(step=3)
    output = await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "state": state,
                "decision": _decision(objective="investigate X"),
                "observation": _observation(),
            }
        ),
    )
    task_list: TaskList = output.port_values["task_list"]
    assert isinstance(task_list, TaskList)
    assert task_list.revision == 1
    assert len(task_list.entries) == 1
    entry = task_list.entries[0]
    assert entry.objective == "investigate X"
    assert entry.status == "pending"
    assert entry.depends_on == ()
    assert entry.created_at_turn == 3
    assert entry.completed_at_turn is None


@pytest.mark.asyncio
async def test_compose_is_idempotent_when_entries_present() -> None:
    """Non-empty task_list + same decision → same entries, no duplication."""
    executor = PlanComposeExecutor()
    seed = TaskEntry(
        task_id=TaskId("seed-1"),
        objective="investigate X",
        status="pending",
        created_at_turn=2,
    )
    state = _agent_state(
        step=4,
        task_list=TaskList(entries=(seed,), revision=2),
    )
    output = await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "state": state,
                "decision": _decision(objective="investigate X"),
                "observation": _observation(),
            }
        ),
    )
    task_list: TaskList = output.port_values["task_list"]
    assert task_list.entries == (seed,)
    # The decision did not duplicate the entry; revision still bumps so
    # listeners see the re-entry through plan.compose.
    assert task_list.revision == 3


@pytest.mark.asyncio
async def test_compose_bumps_revision_with_two_entries_unchanged() -> None:
    """Two-entry list + decision → entries unchanged but revision increments."""
    executor = PlanComposeExecutor()
    e1 = TaskEntry(task_id=TaskId("a"), objective="a", created_at_turn=1)
    e2 = TaskEntry(task_id=TaskId("b"), objective="b", created_at_turn=1)
    state = _agent_state(
        step=5,
        task_list=TaskList(entries=(e1, e2), revision=7),
    )
    output = await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "state": state,
                "decision": _decision(),
                "observation": _observation(),
            }
        ),
    )
    task_list: TaskList = output.port_values["task_list"]
    assert task_list.entries == (e1, e2)
    assert task_list.revision == 8


@pytest.mark.asyncio
async def test_compose_seed_uses_state_step_for_created_at_turn() -> None:
    """``created_at_turn`` is sourced from ``state.step`` (no AgentState.turn field)."""
    executor = PlanComposeExecutor()
    state = _agent_state(step=42)
    output = await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "state": state,
                "decision": _decision(action_type="respond"),
                "observation": None,
            }
        ),
    )
    task_list: TaskList = output.port_values["task_list"]
    assert len(task_list.entries) == 1
    assert task_list.entries[0].created_at_turn == 42


@pytest.mark.asyncio
async def test_compose_accepts_bare_task_list_input() -> None:
    """A bare ``TaskList`` on the state port is honored (typed shortcut)."""
    executor = PlanComposeExecutor()
    bare = TaskList()  # empty → seed
    output = await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "state": bare,
                "decision": _decision(objective="shortcut seed"),
                "observation": _observation(),
            }
        ),
    )
    task_list: TaskList = output.port_values["task_list"]
    assert task_list.revision == 1
    assert task_list.entries[0].objective == "shortcut seed"


@pytest.mark.asyncio
async def test_compose_depends_on_field_is_preserved_when_seeded_via_helper() -> None:
    """``depends_on`` is type-allowed on TaskEntry; compose doesn't invent deps.

    The seed path produces an entry with ``depends_on=()``; this test
    verifies the typed contract is honored and a manually constructed
    depends_on tuple survives a fold through ``_compose_entries``.
    """
    seed_entry = TaskEntry(
        task_id=TaskId("dep-1"),
        objective="follow-up",
        depends_on=(TaskId("a"), TaskId("b")),
        created_at_turn=1,
    )
    existing = (seed_entry,)
    decision = _decision(objective="ignored when entries exist")
    next_entries = _compose_entries(
        existing,
        decision,
        observation=None,
        current_step=99,
    )
    assert next_entries == existing
    assert next_entries[0].depends_on == (TaskId("a"), TaskId("b"))


def test_short_task_id_is_deterministic_and_short() -> None:
    """``_short_task_id`` returns a stable, content-addressed prefix."""
    a = _short_task_id("objective-x|0|d-1")
    b = _short_task_id("objective-x|0|d-1")
    c = _short_task_id("objective-y|0|d-1")
    assert a == b
    assert a != c
    assert len(a) == 12


@pytest.mark.asyncio
async def test_compose_rejects_non_decision_input() -> None:
    """A non-Decision on the decision port raises TypeError (typed boundary)."""
    executor = PlanComposeExecutor()
    with pytest.raises(TypeError):
        await executor.node_execute(
            _ctx(),
            NodeInput(
                port_values={
                    "state": _agent_state(),
                    "decision": {"action_type": "respond"},  # plain dict
                    "observation": _observation(),
                }
            ),
        )


@pytest.mark.asyncio
async def test_compose_pure_across_instances() -> None:
    """Two separately-constructed executors agree on the same input.

    Strengthens the brief's no-hidden-state requirement: equality
    across fresh instances proves the executor carries no instance
    state that leaks across calls.
    """
    state = _agent_state(step=1)
    decision = _decision(objective="same input")
    observation = _observation()
    inp = NodeInput(
        port_values={
            "state": state,
            "decision": decision,
            "observation": observation,
        }
    )
    out_a = await PlanComposeExecutor().node_execute(_ctx(), inp)
    out_b = await PlanComposeExecutor().node_execute(_ctx(), inp)
    assert out_a.port_values["task_list"] == out_b.port_values["task_list"]
