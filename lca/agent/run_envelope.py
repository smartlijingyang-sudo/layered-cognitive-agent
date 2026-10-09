"""Run-lifecycle envelope shared by CognitiveAgent and TeamHandle (RA-082).

One agent_loop.iteration envelope: emit iteration start/end, record the
carrier's Started/Finished journal events, translate execute() outcomes
(success / cancelled / loop-obligation / error) into finish facts.

Carriers (agent, team) differ only in *what* they record and *how* they
translate outcomes — those differences arrive as an EnvelopeSpec. The
envelope owns the shape (try/except/finally cascade); the spec owns the
content. Journal payloads are byte-identical to the pre-convergence code:
agent keeps its CancelledError / LoopObligationExceededError branches,
team keeps its single generic-except behavior.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol

from lca.contracts.models.core.execution.result import Result
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.protocols.graph.errors import LoopObligationExceededError


class RunEventSessionBinder(Protocol):
    """Composition-injected binder for the run-boundary Session (ADR-0186)."""

    def bound(self, run_id: str) -> AbstractContextManager[object | None]: ...


@dataclass(frozen=True)
class TranslatedOutcome:
    """Outcome translation for one execute() exit path.

    disposition "return": the envelope returns ``result`` (agent's
    loop-obligation fail-closed path). disposition "raise": the envelope
    re-raises the in-flight exception.
    """

    status: str
    output: str
    steps: int
    error: str
    outcome: str  # "success" | "cancelled" | "failure"
    disposition: str  # "return" | "raise"
    result: Result | None = None


@dataclass(frozen=True)
class EnvelopeSpec:
    """Carrier-supplied content for the run-lifecycle envelope."""

    iteration_kind: str
    trace_id: str
    role: str
    begin_section: Callable[[], Any]
    emit_started: Callable[[], None]
    emit_resumed: Callable[[], None]
    translate_success: Callable[[Result], TranslatedOutcome]
    translate_cancelled: Callable[[], TranslatedOutcome]
    translate_loop_obligation: Callable[[BaseException], TranslatedOutcome]
    translate_error: Callable[[Exception], TranslatedOutcome]
    emit_finished: Callable[[str, str, int, str], None]
    end_section: Callable[[Any], None]


def _apply(translated: TranslatedOutcome) -> tuple[str, str, int, str, str]:
    return (
        translated.status,
        translated.output,
        translated.steps,
        translated.error,
        translated.outcome,
    )


async def run_envelope(
    *,
    spec: EnvelopeSpec,
    execute: Callable[[], Awaitable[Result]],
) -> Result:
    """Run one agent_loop.iteration inside the shared lifecycle envelope."""
    # Deferred like the pre-convergence call sites (avoids import cycles).
    from lca.loop.emit.cognitive.agent_spawn import (
        emit_agent_loop_iteration_end,
        emit_agent_loop_iteration_start,
    )

    emit_agent_loop_iteration_start(
        trace_id=spec.trace_id,
        role=spec.role,
        iteration_kind=spec.iteration_kind,
    )
    token = spec.begin_section()
    spec.emit_started()
    spec.emit_resumed()
    # Default CANCELED: CancelledError is BaseException and skips
    # except Exception, but finally still emits Finished. (Preserved.)
    finish_status = TaskStatus.CANCELED.value
    finish_output = ""
    finish_steps = 0
    finish_error = ""
    iteration_outcome = "success"
    try:
        result = await execute()
        translated = spec.translate_success(result)
        finish_status, finish_output, finish_steps, finish_error, iteration_outcome = _apply(
            translated
        )
        return result
    except asyncio.CancelledError:
        translated = spec.translate_cancelled()
        finish_status, finish_output, finish_steps, finish_error, iteration_outcome = _apply(
            translated
        )
        raise
    except LoopObligationExceededError as err:
        translated = spec.translate_loop_obligation(err)
        finish_status, finish_output, finish_steps, finish_error, iteration_outcome = _apply(
            translated
        )
        if translated.disposition == "return":
            if translated.result is None:
                raise RuntimeError(
                    "run_envelope: 'return' disposition without a result"
                ) from err
            return translated.result
        raise
    except Exception as err:
        translated = spec.translate_error(err)
        finish_status, finish_output, finish_steps, finish_error, iteration_outcome = _apply(
            translated
        )
        raise
    finally:
        spec.emit_finished(finish_status, finish_output, finish_steps, finish_error)
        spec.end_section(token)
        emit_agent_loop_iteration_end(
            trace_id=spec.trace_id,
            role=spec.role,
            iteration_kind=spec.iteration_kind,
            outcome=iteration_outcome,
        )
