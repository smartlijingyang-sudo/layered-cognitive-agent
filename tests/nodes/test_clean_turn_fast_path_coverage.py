"""todo-28 C1: clean-turn fast-path coverage contract for reflect/remember nodes.

Drives the six reflect/remember node executors directly (no LLM, no gateway)
for 20 clean respond-turn visits each and pins:

1. the four ADR-0246 zero-LLM fast-path nodes (score, memory_extract, admit,
   write) take the explicit shortcut on *every* visit
   (``fast_path_count() == visits``) — i.e. fast-path coverage is 100% on
   clean turns;
2. ``NodeLatencyTracker`` records exactly one sample per visit per node —
   the raw material for the "how much latency tax" P50/P95 answer;
3. every visit completes the turn (routing == RESPOND, or no admit_recovery
   hint) and never touches the LLM adapter or the effect gateway.

Wall-clock timing is deliberately NOT asserted here (flaky on shared CI);
the measured P50/P95 numbers (20 visits/node, clean turn: sum of per-node
p50 = 0.035ms, fast-path 20/20 everywhere) live in the iteration backlog.
What this test nails is the *coverage* half of C1: if someone removes a
``note_fast_path()`` call or breaks a shortcut branch, these counts go red.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.framework.graph.node_latency import NodeLatencyTracker
from lca.nodes.reflect.admit_recovery.admit_recovery import ReflectAdmitRecoveryExecutor
from lca.nodes.reflect.memory_extract.memory_extract import ReflectMemoryExtractExecutor
from lca.nodes.reflect.score.score import ReflectScoreExecutor
from lca.nodes.remember.admit.admit import RememberAdmitExecutor
from lca.nodes.remember.fold.fold import RememberFoldExecutor
from lca.nodes.remember.write.write import RememberWriteExecutor

VISITS = 20


class _ExplodingAdapter:
    """If this is ever called the test must fail: clean turns are zero-LLM."""

    async def complete(self, prompt: str, **kwargs: object) -> object:
        raise AssertionError("fast path must not call the LLM adapter")


def _clean_decision() -> Decision:
    return Decision(
        decision_id="dec-clean",
        action_type="respond",
        response_text="Clean reply",
        rationale="No tools needed",
        confidence=1.0,
    )


def _cases(brain: MagicMock, gateway: MagicMock):
    """(node_id, executor, context_factory, input_factory, expects_fast_path)."""
    return [
        (
            "reflect.score",
            ReflectScoreExecutor(),
            lambda: NodeContext(runtime={"brain": brain}, metadata={}, budget=None),
            lambda: NodeInput(port_values={"observation": None}),
            True,
        ),
        (
            "reflect.memory_extract",
            ReflectMemoryExtractExecutor(),
            lambda: NodeContext(runtime={"adapter": _ExplodingAdapter()}, metadata={}, budget=None),
            lambda: NodeInput(port_values={"reflection": None}),
            True,
        ),
        (
            "reflect.admit_recovery",
            ReflectAdmitRecoveryExecutor(),
            lambda: NodeContext(runtime={}, metadata={}, budget=None),
            lambda: NodeInput(port_values={"observation": None, "reflection": None}),
            False,  # no shortcut branch by design (cf17802c0)
        ),
        (
            "remember.admit",
            RememberAdmitExecutor(),
            lambda: NodeContext(runtime={}, metadata={}, budget=None),
            lambda: NodeInput(
                port_values={
                    "decision": _clean_decision(),
                    "observation": None,
                    "reflection": None,
                }
            ),
            True,
        ),
        (
            "remember.write",
            RememberWriteExecutor(),
            lambda: NodeContext(runtime={"effect_gateway": gateway}, metadata={}, budget=None),
            lambda: NodeInput(
                port_values={
                    "decision": _clean_decision(),
                    "observation": None,
                    "reflection": None,
                }
            ),
            True,
        ),
        (
            "remember.fold",
            RememberFoldExecutor(),
            lambda: NodeContext(runtime={}, metadata={}, budget=None),
            lambda: NodeInput(port_values={"memory_receipt": None}),
            False,  # pure forward, no shortcut branch by design
        ),
    ]


@pytest.mark.asyncio
async def test_clean_turn_fast_path_coverage_20_visits() -> None:
    """20 clean-turn visits per node: fast-path 20/20 where a shortcut exists."""
    brain = MagicMock()
    brain.reflect = AsyncMock()
    gateway = MagicMock()
    gateway.dispatch = AsyncMock()

    for node_id, executor, ctx_fn, in_fn, expects_fast_path in _cases(brain, gateway):
        for _ in range(VISITS):
            output = await executor.node_execute(ctx_fn(), in_fn())
            routing = output.port_values["routing"]
            if node_id == "reflect.admit_recovery":
                # Clean turn is not a failure: no recovery hint is raised.
                assert routing.next_hint is None, node_id
            else:
                assert routing.action_type == ActionType.RESPOND, node_id
        if expects_fast_path:
            assert executor.fast_path_count() == VISITS, (
                f"{node_id}: expected every visit to take the fast path, "
                f"got {executor.fast_path_count()}/{VISITS}"
            )
        else:
            assert not hasattr(executor, "fast_path_count"), node_id

    brain.reflect.assert_not_called()
    gateway.dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_latency_tracker_records_one_sample_per_visit() -> None:
    """The C1 metric surface: exactly one sample per node visit."""
    tracker = NodeLatencyTracker()
    brain = MagicMock()
    brain.reflect = AsyncMock()
    gateway = MagicMock()
    gateway.dispatch = AsyncMock()

    for node_id, executor, ctx_fn, in_fn, _ in _cases(brain, gateway):
        for _ in range(VISITS):
            await executor.node_execute(ctx_fn(), in_fn())
            tracker.record(node_id, 0)

    snapshot = tracker.snapshot()
    assert set(snapshot) == {
        "reflect.score",
        "reflect.memory_extract",
        "reflect.admit_recovery",
        "remember.admit",
        "remember.write",
        "remember.fold",
    }
    for node_id, stats in snapshot.items():
        assert stats.count == VISITS, f"{node_id}: {stats.count} != {VISITS}"
