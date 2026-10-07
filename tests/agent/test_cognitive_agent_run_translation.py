"""RA-023: ``Agent.run()`` translates non-convergence into a failed Result.

The interpreter legitimately raises ``LoopObligationExceededError`` when
a run fails to converge; the translation seam lives in
``CognitiveAgent._run_lifecycle_body`` so callers (Team pipeline, cron
workers, handoffs) get a fail-closed Result instead of a graph-internal
error type. ``asyncio.CancelledError`` must still propagate, and other
exceptions keep the fail-loud behavior.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import pytest

from lca.agent.cognitive_agent import CognitiveAgent, _loop_obligation_failed_result
from lca.contracts.models.core.execution.result import Result
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.models.observability.journal.journal import RunScope
from lca.contracts.protocols.graph.errors import LoopObligationExceededError


def _agent() -> CognitiveAgent:
    # The failure paths of _run_lifecycle_body never touch instance
    # state, so a bare instance is enough to pin the translation seam.
    return CognitiveAgent.__new__(CognitiveAgent)


def _body_kwargs(execute: Callable[[], Awaitable[Result]]) -> dict:
    return {
        "objective": "do it",
        "ctx": None,
        "role": "tester",
        "top_level": True,
        "scope": RunScope(trace_id="t-1", run_id="r-1"),
        "execute": execute,
        "resumed_snapshot": None,
        "iteration_kind": "fresh",
        "iteration_trace_id": "t-1",
    }


def _loop_err() -> LoopObligationExceededError:
    return LoopObligationExceededError(
        "plan 'p': edge 'act' → 'think' exhausted loop.maxIterations=5 "
        "(taken=5); no fallback edge matched.",
        plan_id="p",
        source="act",
        target="think",
        max_iterations=5,
        taken=5,
    )


async def test_loop_obligation_translated_to_failed_result() -> None:
    async def execute() -> Result:
        raise _loop_err()

    result = await _agent()._run_lifecycle_body(**_body_kwargs(execute))
    assert result.status == TaskStatus.FAILED
    assert "LoopObligationExceededError" in (result.error or "")
    assert result.total_steps == 5
    assert result.extra["loop_obligation"] == {
        "plan_id": "p",
        "edge": {"source": "act", "target": "think"},
        "max_iterations": 5,
        "taken": 5,
    }


async def test_cancelled_error_still_propagates() -> None:
    async def execute() -> Result:
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await _agent()._run_lifecycle_body(**_body_kwargs(execute))


async def test_other_errors_still_raise() -> None:
    async def execute() -> Result:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        await _agent()._run_lifecycle_body(**_body_kwargs(execute))


def test_failed_result_helper_preserves_facts() -> None:
    result = _loop_obligation_failed_result(
        _loop_err(), scope=RunScope(trace_id="t-9"), partial_output="partial"
    )
    assert result.status == TaskStatus.FAILED
    assert result.trace_id == "t-9"
    assert result.total_steps == 5
    assert result.output == "partial"
    # zero Budget per the Result contract for non-COMPLETED runs
    assert result.budget_used.used_steps == 0
