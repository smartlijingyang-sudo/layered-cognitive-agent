"""Round 89 regression: ``DelegateOperation`` shares the cache/invoke/record
seam between single and multi delegation paths.

Before R89, ``_execute_one`` and ``_execute_many`` inlined the same
``cached_delegation_observation → _invoke → _record_return`` sequence.
Two inline copies of the same bookkeeping is the textbook place where
single-path fixes never reach the multi-path (and vice versa).

R89 introduces ``_resolve_observation`` and ``_aggregate_observations``:
- ``_resolve_observation`` is the single cache/invoke/record seam.
- ``_aggregate_observations`` folds N observations into one multi-delegate
  Observation with member payload, subtasks, and task_ids.
- ``execute`` calls ``_resolve_observation`` once per spec (sequentially or
  via ``asyncio.gather``) and tags/aggregates accordingly.
"""

from __future__ import annotations

import asyncio

from lca.contracts.atoms.enums import ActionType, MemoryRecordKind
from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import (
    OBS_MEMBER_RESULTS,
    OBS_MEMBER_SUBTASKS,
    OBS_RESULT_KIND,
    OBS_TASK_IDS,
)
from lca.contracts.models.core.decision import (
    Decision,
    DelegationSpec,
    Observation,
)
from lca.contracts.models.core.state import AgentState, Budget
from lca.infrastructure.transport.transport_registry import TransportRegistry
from lca.cognition.body.action_handlers import DelegateOperation


def _state() -> AgentState:
    return AgentState(trace_id="t", task="task", budget=Budget())


def _spec(role: str, subtask: str = "do work") -> DelegationSpec:
    return DelegationSpec(target_role=role, subtask=subtask)


class TestResolveObservationSeam:
    """R89: cache/invoke/record lives in one helper, both paths use it."""

    def test_resolve_observation_is_async(self) -> None:
        """Sanity: the seam preserves the async shape of the inner invoke."""
        op = DelegateOperation(TransportRegistry())
        assert asyncio.iscoroutinefunction(op._resolve_observation)

    def test_resolve_returns_cache_when_present(self) -> None:
        """Cache hit short-circuits the transport path."""
        from datetime import datetime, timezone

        from lca.contracts.models.team.delegation import DelegationResult
        from lca.contracts.models.team.team_awareness import TeamAwareness

        op = DelegateOperation(TransportRegistry())
        state = _state()
        spec = _spec("writer", subtask="specific task")
        state.team_awareness = TeamAwareness(
            results=[
                DelegationResult(
                    result_id="r1",
                    target_role="writer",
                    subtask="specific task",
                    output="cached",
                    success=True,
                    error=None,
                    task_id="t1",
                    step=1,
                    returned_at=datetime.now(tz=timezone.utc),
                )
            ]
        )
        observed = asyncio.run(op._resolve_observation(spec, state))
        assert observed is not None
        assert observed.success is True
        assert observed.payload == "cached"
        assert observed.extra.get("cache_hit") is True

    def test_resolve_falls_through_to_invoke_on_cache_miss(self) -> None:
        """Cache miss invokes the transport; the result is returned (no
        synthetic delay or extra wrapping)."""
        op = DelegateOperation(TransportRegistry())
        state = _state()
        spec = _spec("writer")
        # No cache entry; the transport registry has nothing registered,
        # so _invoke will raise. We just want to confirm we enter the
        # fall-through branch — proven by the immediate raise before the
        # ``_record_return`` line is even reachable.
        try:
            asyncio.run(op._resolve_observation(spec, state))
        except Exception:
            return  # expected: no transport registered
        raise AssertionError("expected an exception on cache-miss without transport")


class TestAggregateObservationsShape:
    """R89: aggregation is its own helper with a stable output shape."""

    def test_aggregates_member_payload(self) -> None:
        op = DelegateOperation(TransportRegistry())
        specs = [_spec("writer"), _spec("reviewer")]
        observations = [
            Observation(observation_id=new_id("obs"), success=True, payload="w-out"),
            Observation(observation_id=new_id("obs"), success=False, payload=None, error="r-fail"),
        ]
        out = op._aggregate_observations(specs, observations)
        assert out.success is False
        assert out.extra[OBS_MEMBER_RESULTS]["writer"] == "w-out"
        assert out.extra[OBS_MEMBER_RESULTS]["reviewer"] == "r-fail"
        assert out.extra[OBS_MEMBER_SUBTASKS]["writer"] == "do work"
        assert out.extra[OBS_MEMBER_SUBTASKS]["reviewer"] == "do work"
        assert out.extra[OBS_RESULT_KIND] == MemoryRecordKind.DELEGATION_RESULT
        assert len(out.extra[OBS_TASK_IDS]) == 2
        assert out.error == "one or more delegates failed"

    def test_all_success_aggregates_to_success(self) -> None:
        op = DelegateOperation(TransportRegistry())
        specs = [_spec("writer"), _spec("reviewer")]
        observations = [
            Observation(observation_id=new_id("obs"), success=True, payload="ok1"),
            Observation(observation_id=new_id("obs"), success=True, payload="ok2"),
        ]
        out = op._aggregate_observations(specs, observations)
        assert out.success is True
        assert out.error is None


class TestExecuteShape:
    """Sanity: execute() wires the new helpers correctly."""

    def test_empty_delegations_raises_tool_execution_error(self) -> None:
        from lca.contracts.models.core.result import ToolExecutionError

        op = DelegateOperation(TransportRegistry())
        decision = Decision(
            decision_id="d",
            action_type=ActionType.DELEGATE.value,
            rationale="",
            confidence=0.5,
            response_text="",
            delegations=[],
        )
        try:
            asyncio.run(op.execute(decision, _state()))
        except ToolExecutionError:
            return
        raise AssertionError("expected ToolExecutionError on empty delegations")

    def test_single_delegation_uses_tag_delegation_extra(self) -> None:
        """The single-path branch must still call tag_delegation_extra."""
        from datetime import datetime, timezone

        from lca.contracts.models.team.delegation import DelegationResult
        from lca.contracts.models.team.team_awareness import TeamAwareness

        op = DelegateOperation(TransportRegistry())
        state = _state()
        spec = _spec("writer", subtask="specific task")
        state.team_awareness = TeamAwareness(
            results=[
                DelegationResult(
                    result_id="r1",
                    target_role="writer",
                    subtask="specific task",
                    output="cached",
                    success=True,
                    error=None,
                    task_id="t1",
                    step=1,
                    returned_at=datetime.now(tz=timezone.utc),
                )
            ]
        )
        decision = Decision(
            decision_id="d",
            action_type=ActionType.DELEGATE.value,
            rationale="",
            confidence=0.5,
            response_text="",
            delegations=[spec],
        )
        out = asyncio.run(op.execute(decision, state))
        # _resolve_observation returns the cache-hit Observation already
        # tagged; execute() tags once more (idempotent for the same spec).
        assert out.success is True
        assert out.payload == "cached"
        assert out.extra["member_results"] == {"writer": "cached"}
        assert out.extra["member_subtasks"] == {"writer": "specific task"}
