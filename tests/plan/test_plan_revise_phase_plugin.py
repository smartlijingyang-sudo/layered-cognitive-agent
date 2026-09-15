"""Tests for region.plan.revise plugin.

Pins the typed ``plan.revise`` node contract (ADR-0228 §Decision 3):
reads ``state.task_list`` + ``reflection`` and emits a revised
``TaskList`` with a monotonic revision. Enforces idempotency, the
``replan_requested`` reset rule, the ``depends_on`` blocking rule, and
the explicit ``blocked_tasks`` override.
"""

from __future__ import annotations

import pytest

from lca.contracts.models.cognition.task import (
    Reflection,
    TaskEntry,
    TaskId,
    TaskList,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.nodes.plan.revise.revise import PlanReviseExecutor


def _ctx() -> NodeContext:
    """Minimal NodeContext; revise does not read runtime."""
    return NodeContext(runtime={}, budget={}, metadata={})


async def _run(
    *,
    task_list: TaskList,
    reflection: Reflection,
) -> TaskList:
    """Execute the revise node with the given TaskList + Reflection."""
    executor = PlanReviseExecutor()
    out = await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "state": type("_S", (), {"task_list": task_list})(),
                "reflection": reflection,
            },
        ),
    )
    result = out.port_values["task_list"]
    assert isinstance(result, TaskList)
    return result


@pytest.mark.asyncio
async def test_revise_empty_task_list_with_no_replan_emits_empty_list() -> None:
    """Case 1: empty TaskList + reflection(replan_requested=False)
    → emit empty TaskList, revision is unchanged (true no-op per C6)."""
    result = await _run(
        task_list=TaskList(),
        reflection=Reflection(replan_requested=False),
    )
    assert result.entries == ()
    assert result.revision == 0


@pytest.mark.asyncio
async def test_revise_pending_entry_with_replan_bumps_revision() -> None:
    """Case 2: 1 pending entry + reflection(replan_requested=True)
    → revision bumped, entry status remains pending."""
    entry = TaskEntry(
        task_id=TaskId("t1"),
        objective="do thing",
        status="pending",
        created_at_turn=1,
    )
    result = await _run(
        task_list=TaskList(entries=(entry,), revision=4),
        reflection=Reflection(replan_requested=True),
    )
    assert result.revision == 5
    assert len(result.entries) == 1
    assert result.entries[0].task_id == TaskId("t1")
    assert result.entries[0].status == "pending"


@pytest.mark.asyncio
async def test_revise_met_depends_on_keeps_entry_pending() -> None:
    """Case 3: entry1.depends_on=(entry2.task_id), entry2 completed
    → entry1 stays pending (dependency is satisfied)."""
    entry1 = TaskEntry(
        task_id=TaskId("t1"),
        objective="downstream",
        status="pending",
        depends_on=(TaskId("t2"),),
        created_at_turn=1,
    )
    entry2 = TaskEntry(
        task_id=TaskId("t2"),
        objective="upstream",
        status="completed",
        created_at_turn=1,
        completed_at_turn=3,
    )
    result = await _run(
        task_list=TaskList(entries=(entry1, entry2)),
        reflection=Reflection(replan_requested=False),
    )
    by_id = {entry.task_id: entry for entry in result.entries}
    assert by_id[TaskId("t1")].status == "pending"
    assert by_id[TaskId("t2")].status == "completed"


@pytest.mark.asyncio
async def test_revise_unmet_depends_on_blocks_entry() -> None:
    """Case 4: entry1.depends_on=(entry2.task_id), entry2 not completed
    → entry1.status='blocked'."""
    entry1 = TaskEntry(
        task_id=TaskId("t1"),
        objective="downstream",
        status="pending",
        depends_on=(TaskId("t2"),),
        created_at_turn=1,
    )
    entry2 = TaskEntry(
        task_id=TaskId("t2"),
        objective="upstream",
        status="pending",
        created_at_turn=1,
    )
    result = await _run(
        task_list=TaskList(entries=(entry1, entry2)),
        reflection=Reflection(replan_requested=False),
    )
    by_id = {entry.task_id: entry for entry in result.entries}
    assert by_id[TaskId("t1")].status == "blocked"
    assert by_id[TaskId("t2")].status == "pending"


@pytest.mark.asyncio
async def test_revise_blocked_tasks_overrides_status() -> None:
    """Case 5: reflection(blocked_tasks=(task_id_1,)) → entry[t1].status='blocked'."""
    entry1 = TaskEntry(
        task_id=TaskId("t1"),
        objective="thing one",
        status="pending",
        created_at_turn=1,
    )
    entry2 = TaskEntry(
        task_id=TaskId("t2"),
        objective="thing two",
        status="pending",
        created_at_turn=1,
    )
    result = await _run(
        task_list=TaskList(entries=(entry1, entry2)),
        reflection=Reflection(
            replan_requested=False,
            blocked_tasks=(TaskId("t1"),),
            rationale="t1 is gated on external system",
        ),
    )
    by_id = {entry.task_id: entry for entry in result.entries}
    assert by_id[TaskId("t1")].status == "blocked"
    assert by_id[TaskId("t2")].status == "pending"


@pytest.mark.asyncio
async def test_revise_is_idempotent_across_calls() -> None:
    """Idempotency: identical inputs across two executions yield identical outputs."""
    entry = TaskEntry(
        task_id=TaskId("t1"),
        objective="do thing",
        status="pending",
        created_at_turn=1,
    )
    reflection = Reflection(replan_requested=True)
    out_a = await _run(task_list=TaskList(entries=(entry,)), reflection=reflection)
    out_b = await _run(task_list=TaskList(entries=(entry,)), reflection=reflection)
    assert out_a == out_b


@pytest.mark.asyncio
async def test_revise_does_not_re_stamp_completed_entries() -> None:
    """Completed entries are never re-stamped, even when replan_requested=True."""
    entry = TaskEntry(
        task_id=TaskId("t1"),
        objective="done",
        status="completed",
        created_at_turn=1,
        completed_at_turn=2,
    )
    result = await _run(
        task_list=TaskList(entries=(entry,)),
        reflection=Reflection(replan_requested=True),
    )
    assert result.entries[0].status == "completed"
    assert result.entries[0].completed_at_turn == 2


@pytest.mark.asyncio
async def test_revise_unmet_depends_on_beats_replan_requested() -> None:
    """replan_requested does NOT clear a blocked-by-dependency entry;
    the depends_on rule wins (a replan is no excuse to skip an unmet dep)."""
    entry1 = TaskEntry(
        task_id=TaskId("t1"),
        objective="downstream",
        status="pending",
        depends_on=(TaskId("t2"),),
        created_at_turn=1,
    )
    entry2 = TaskEntry(
        task_id=TaskId("t2"),
        objective="upstream",
        status="pending",
        created_at_turn=1,
    )
    result = await _run(
        task_list=TaskList(entries=(entry1, entry2)),
        reflection=Reflection(replan_requested=True),
    )
    by_id = {entry.task_id: entry for entry in result.entries}
    assert by_id[TaskId("t1")].status == "blocked"


@pytest.mark.asyncio
async def test_revise_rejects_non_reflection_port_value() -> None:
    """A non-Reflection value on the reflection port is a contract bug."""
    executor = PlanReviseExecutor()
    with pytest.raises(TypeError):
        await executor.node_execute(
            _ctx(),
            NodeInput(
                port_values={
                    "state": TaskList(),
                    "reflection": {"replan_requested": True},
                },
            ),
        )
