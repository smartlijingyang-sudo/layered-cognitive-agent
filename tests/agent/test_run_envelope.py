"""RA-082: run-lifecycle envelope — outcome-translation matrix + cascade tests.

The outcome matrix (exit path x carrier) was previously unwritable: the
translation logic was embedded in CognitiveAgent._run_lifecycle_body and
TeamHandle._run_body. After converging both onto lca.agent.run_envelope,
the translators are module-level and table-testable, and the shared
try/except/finally cascade is pinned once.
"""

from __future__ import annotations

import asyncio

import pytest

from lca.agent.cognitive_agent import (
    _agent_translate_cancelled,
    _agent_translate_error,
    _agent_translate_loop_obligation,
    _agent_translate_success,
)
from lca.agent.run_envelope import EnvelopeSpec, run_envelope
from lca.agent.team_handle import (
    _team_translate_cancelled,
    _team_translate_error,
    _team_translate_loop_obligation,
    _team_translate_success,
)
from lca.contracts.models.core.execution.result import Result
from lca.contracts.models.core.policy.budget import Budget
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.models.observability.journal.journal import RunScope
from lca.contracts.protocols.graph.errors import LoopObligationExceededError


def _ok_result(**kw) -> Result:
    return Result(
        trace_id="t",
        status=TaskStatus.COMPLETED,
        final_state_ref="",
        total_steps=3,
        budget_used=Budget(),
        output="done",
        **kw,
    )


def _scope() -> RunScope:
    return RunScope(trace_id="t-1", run_id="r-1")


def _loop_err() -> LoopObligationExceededError:
    return LoopObligationExceededError(
        "no convergence",
        plan_id="p",
        source="a",
        target="b",
        max_iterations=3,
        taken=3,
    )


# --- translation matrix: agent flavor ---


def test_matrix_agent_success() -> None:
    t = _agent_translate_success(_ok_result())
    assert (
        t.status,
        t.output,
        t.steps,
        t.error,
        t.outcome,
        t.disposition,
    ) == (TaskStatus.COMPLETED.value, "done", 3, "", "success", "return")
    assert t.result is not None


def test_matrix_agent_cancelled() -> None:
    t = _agent_translate_cancelled()
    assert (t.status, t.error, t.outcome, t.disposition) == (
        TaskStatus.CANCELED.value,
        "canceled",
        "cancelled",
        "raise",
    )


def test_matrix_agent_loop_obligation() -> None:
    t = _agent_translate_loop_obligation(_loop_err(), scope=_scope())
    assert t.status == TaskStatus.FAILED.value
    assert t.outcome == "failure"
    assert t.disposition == "return"
    assert "LoopObligationExceededError" in t.error
    assert t.result is not None
    assert t.result.status == TaskStatus.FAILED
    assert t.result.extra["loop_obligation"]["taken"] == 3


def test_matrix_agent_error() -> None:
    t = _agent_translate_error(ValueError("boom"))
    assert (t.status, t.error, t.outcome, t.disposition) == (
        TaskStatus.FAILED.value,
        "ValueError: boom",
        "failure",
        "raise",
    )


# --- translation matrix: team flavor ---


def test_matrix_team_success() -> None:
    # Team does NOT take finish_error from result.error (pre-convergence behavior).
    t = _team_translate_success(_ok_result(error="ignored"))
    assert (t.status, t.output, t.steps, t.error, t.outcome, t.disposition) == (
        TaskStatus.COMPLETED.value,
        "done",
        3,
        "",
        "success",
        "return",
    )


def test_matrix_team_cancelled() -> None:
    # Preserved odd-but-current: CANCELED status with "success" outcome,
    # because the team never had a CancelledError branch.
    t = _team_translate_cancelled()
    assert (t.status, t.outcome, t.disposition) == (
        TaskStatus.CANCELED.value,
        "success",
        "raise",
    )


def test_matrix_team_loop_obligation() -> None:
    # Team has no loop-obligation branch: identical to the generic error path.
    t = _team_translate_loop_obligation(_loop_err())
    assert (t.status, t.error, t.outcome, t.disposition) == (
        TaskStatus.FAILED.value,
        "LoopObligationExceededError: no convergence",
        "failure",
        "raise",
    )


def test_matrix_team_error() -> None:
    t = _team_translate_error(ValueError("boom"))
    assert (t.status, t.error, t.outcome, t.disposition) == (
        TaskStatus.FAILED.value,
        "ValueError: boom",
        "failure",
        "raise",
    )


# --- shared cascade: run_envelope drives the spec ---


def _agent_spec(rec: dict) -> EnvelopeSpec:
    """EnvelopeSpec with the agent's real translators and recording stubs."""
    return EnvelopeSpec(
        iteration_kind="fresh",
        trace_id="trace-1",
        role="agent:test",
        begin_section=lambda: rec.setdefault("sections", []).append("begin") or "tok",
        emit_started=lambda: rec.setdefault("events", []).append("started"),
        emit_resumed=lambda: rec.setdefault("events", []).append("resumed"),
        translate_success=_agent_translate_success,
        translate_cancelled=_agent_translate_cancelled,
        translate_loop_obligation=lambda err: _agent_translate_loop_obligation(
            err, scope=_scope()
        ),
        translate_error=_agent_translate_error,
        emit_finished=lambda s, o, n, e: rec.update(finished=(s, o, n, e)),
        end_section=lambda tok: rec.setdefault("sections", []).append(("end", tok)),
    )


def _team_spec(rec: dict) -> EnvelopeSpec:
    return EnvelopeSpec(
        iteration_kind="fresh",
        trace_id="trace-1",
        role="team:test",
        begin_section=lambda: None,
        emit_started=lambda: rec.setdefault("events", []).append("started"),
        emit_resumed=lambda: rec.setdefault("events", []).append("resumed"),
        translate_success=_team_translate_success,
        translate_cancelled=_team_translate_cancelled,
        translate_loop_obligation=_team_translate_loop_obligation,
        translate_error=_team_translate_error,
        emit_finished=lambda s, o, n, e: rec.update(finished=(s, o, n, e)),
        end_section=lambda _tok: None,
    )


async def test_envelope_success_returns_result_and_finishes() -> None:
    rec: dict = {}
    result = _ok_result()

    async def execute() -> Result:
        return result

    out = await run_envelope(spec=_agent_spec(rec), execute=execute)
    assert out is result
    assert rec["finished"] == (TaskStatus.COMPLETED.value, "done", 3, "")
    assert rec["events"] == ["started", "resumed"]
    assert rec["sections"] == ["begin", ("end", "tok")]


async def test_envelope_cancelled_reraises_with_cancelled_facts() -> None:
    rec: dict = {}

    async def execute() -> Result:
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await run_envelope(spec=_agent_spec(rec), execute=execute)
    assert rec["finished"] == (TaskStatus.CANCELED.value, "", 0, "canceled")


async def test_envelope_loop_obligation_returns_failed_result() -> None:
    rec: dict = {}

    async def execute() -> Result:
        raise _loop_err()

    out = await run_envelope(spec=_agent_spec(rec), execute=execute)
    assert out.status == TaskStatus.FAILED
    assert "LoopObligationExceededError" in (out.error or "")
    status, _o, _n, error = rec["finished"]
    assert status == TaskStatus.FAILED.value
    assert "LoopObligationExceededError" in error


async def test_envelope_error_reraises_with_failed_facts() -> None:
    rec: dict = {}

    async def execute() -> Result:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        await run_envelope(spec=_agent_spec(rec), execute=execute)
    status, _o, _n, error = rec["finished"]
    assert status == TaskStatus.FAILED.value
    assert error == "ValueError: boom"


async def test_envelope_team_loop_obligation_reraises() -> None:
    # Team has no loop-obligation branch: the error propagates like any error,
    # with the generic-error finish facts.
    rec: dict = {}

    async def execute() -> Result:
        raise _loop_err()

    with pytest.raises(LoopObligationExceededError):
        await run_envelope(spec=_team_spec(rec), execute=execute)
    status, _o, _n, error = rec["finished"]
    assert status == TaskStatus.FAILED.value
    assert error == "LoopObligationExceededError: no convergence"
