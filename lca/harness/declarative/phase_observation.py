"""Read-only observation implementations for declarative phase execution.

Observation is deliberately outside the phase transaction's control path. A
profile may compose multiple independently contributed observers, but an
observer cannot mutate phase state or suppress an executor failure.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import AbstractContextManager, ExitStack, contextmanager, nullcontext
from enum import StrEnum

import structlog

from lca.contracts.atoms.telemetry import ATTR_AGENT_ROLE, ATTR_STEP, SpanName
from lca.contracts.protocols.declarative.declarative_phase_graph import SemanticPhase
from lca.contracts.protocols.journal.phase_observation import (
    PhaseObserver,
    PhaseObserverContribution,
    PhaseObserverRegistry,
    PhaseStateSnapshot,
)
from lca.harness.declarative.phase_observation_snapshot import phase_state_snapshot
from lca.infrastructure.observability import span

_log = structlog.get_logger("lca.runtime.phase_observer")


class ObserverFailureMode(StrEnum):
    """Declare whether observation faults may affect phase execution."""

    FAIL_OPEN = "fail_open"
    FAIL_CLOSED = "fail_closed"


class PhaseObserverError(RuntimeError):
    """A contributed observer failed while strict observation is enabled."""

    def __init__(self, contribution_id: str, operation: str) -> None:
        super().__init__(
            f"phase observer contribution {contribution_id!r} failed during {operation}"
        )
        self.contribution_id = contribution_id
        self.operation = operation


class InMemoryPhaseObserverRegistry(PhaseObserverRegistry):
    """Collect unique observer contributions and expose a stable frozen snapshot.

    The registry is a neutral seam. It owns no default behavior: profile-loaded
    provider plugins explicitly contribute observers during boot. A duplicate
    identifier is rejected so activation order cannot silently replace an audit
    or telemetry capability.
    """

    def __init__(self) -> None:
        self._contributions: dict[str, PhaseObserverContribution] = {}

    def register(self, contribution: PhaseObserverContribution) -> None:
        _validate_contribution(contribution)
        if contribution.id in self._contributions:
            raise KeyError(
                f"phase_observer_registry: contribution {contribution.id!r} already registered"
            )
        self._contributions[contribution.id] = contribution

    def snapshot(self) -> tuple[PhaseObserverContribution, ...]:
        """Return a deterministic boot snapshot ordered by priority then identity."""

        return tuple(
            sorted(self._contributions.values(), key=lambda item: (item.priority, item.id))
        )


class CompositePhaseObserver(PhaseObserver):
    """Bracket a phase with a frozen ordered set of read-only observers.

    A composite is constructed after profile boot. Later registry changes cannot
    alter an in-flight runtime binding, preserving the same execution locality as
    frozen executor bindings. ``fail_open`` is the default because telemetry
    must not become a hidden agent-control path; strict profiles may opt into
    ``fail_closed`` when observation itself is a compliance requirement.
    """

    def __init__(
        self,
        contributions: Sequence[PhaseObserverContribution] = (),
        *,
        failure_mode: ObserverFailureMode = ObserverFailureMode.FAIL_OPEN,
    ) -> None:
        for contribution in contributions:
            _validate_contribution(contribution)
        self._contributions = tuple(
            sorted(contributions, key=lambda item: (item.priority, item.id))
        )
        self._failure_mode = failure_mode

    @property
    def contributions(self) -> tuple[PhaseObserverContribution, ...]:
        """Expose the immutable contribution snapshot for diagnostics and tests."""

        return self._contributions

    @property
    def failure_mode(self) -> ObserverFailureMode:
        """Return the explicit observer-failure policy for this runtime binding."""

        return self._failure_mode

    def observe(
        self,
        *,
        semantic_phase: SemanticPhase,
        state: PhaseStateSnapshot,
    ) -> AbstractContextManager[object]:
        """Enter every observer without granting it control over phase execution."""

        return self._observe_all(semantic_phase=semantic_phase, state=state)

    @contextmanager
    def _observe_all(
        self,
        *,
        semantic_phase: SemanticPhase,
        state: PhaseStateSnapshot,
    ) -> Iterator[None]:
        with ExitStack() as stack:
            for contribution in self._contributions:
                stack.enter_context(
                    _guarded_observer_context(
                        contribution,
                        semantic_phase=semantic_phase,
                        state=state,
                        failure_mode=self._failure_mode,
                    )
                )
            yield


_PHASE_TO_LOOP_SPAN: dict[SemanticPhase, SpanName] = {
    SemanticPhase.PERCEIVE: SpanName.LOOP_PHASE_PERCEIVE,
    SemanticPhase.THINK: SpanName.LOOP_PHASE_THINK,
    SemanticPhase.ACT: SpanName.LOOP_PHASE_ACT,
    SemanticPhase.REFLECT: SpanName.LOOP_PHASE_REFLECT,
}


class TracingPhaseObserver(PhaseObserver):
    """Map standard semantic phases to existing loop spans."""

    def observe(
        self,
        *,
        semantic_phase: SemanticPhase,
        state: PhaseStateSnapshot,
    ) -> AbstractContextManager[object]:
        span_name = _PHASE_TO_LOOP_SPAN.get(semantic_phase)
        if span_name is None:
            return nullcontext()
        return span(
            span_name,
            **{
                ATTR_AGENT_ROLE: state.agent_role,
                ATTR_STEP: state.step,
            },
        )


class NullPhaseObserver(PhaseObserver):
    """Explicit no-op observer for focused tests and observation-free drivers."""

    def observe(
        self,
        *,
        semantic_phase: SemanticPhase,
        state: PhaseStateSnapshot,
    ) -> AbstractContextManager[object]:
        del semantic_phase, state
        return nullcontext()


@contextmanager
def _guarded_observer_context(
    contribution: PhaseObserverContribution,
    *,
    semantic_phase: SemanticPhase,
    state: PhaseStateSnapshot,
    failure_mode: ObserverFailureMode,
) -> Iterator[None]:
    """Run one observer without allowing it to intercept executor control flow."""

    manager: AbstractContextManager[object]
    try:
        manager = contribution.observer.observe(semantic_phase=semantic_phase, state=state)
        manager.__enter__()
    except Exception as exc:
        _handle_observer_failure(
            contribution,
            semantic_phase=semantic_phase,
            operation="enter",
            failure_mode=failure_mode,
            error=exc,
        )
        yield
        return

    try:
        yield
    except BaseException as executor_error:
        try:
            manager.__exit__(
                type(executor_error),
                executor_error,
                executor_error.__traceback__,
            )
        except Exception as exc:
            _handle_observer_failure(
                contribution,
                semantic_phase=semantic_phase,
                operation="exit",
                failure_mode=failure_mode,
                error=exc,
            )
        raise
    else:
        try:
            manager.__exit__(None, None, None)
        except Exception as exc:
            _handle_observer_failure(
                contribution,
                semantic_phase=semantic_phase,
                operation="exit",
                failure_mode=failure_mode,
                error=exc,
            )


def _validate_contribution(contribution: PhaseObserverContribution) -> None:
    """Validate open plugin input before the concrete registry accepts it."""

    if not isinstance(contribution, PhaseObserverContribution):
        raise TypeError("phase observer registry requires PhaseObserverContribution")
    if not contribution.id.strip():
        raise ValueError("phase observer contribution id must not be empty")
    if not isinstance(contribution.observer, PhaseObserver):
        raise TypeError("phase observer contribution must implement PhaseObserver")


def _handle_observer_failure(
    contribution: PhaseObserverContribution,
    *,
    semantic_phase: SemanticPhase,
    operation: str,
    failure_mode: ObserverFailureMode,
    error: Exception,
) -> None:
    """Log a passive observer failure or raise a strict, attributable error."""

    if failure_mode is ObserverFailureMode.FAIL_CLOSED:
        raise PhaseObserverError(contribution.id, operation) from error
    _log.warning(
        "phase_observer_failed",
        observer_id=contribution.id,
        observer_type=type(contribution.observer).__name__,
        phase=semantic_phase.value,
        operation=operation,
        exc_info=True,
    )


__all__ = [
    "CompositePhaseObserver",
    "InMemoryPhaseObserverRegistry",
    "NullPhaseObserver",
    "ObserverFailureMode",
    "PhaseObserver",
    "PhaseObserverContribution",
    "PhaseObserverError",
    "PhaseObserverRegistry",
    "PhaseStateSnapshot",
    "TracingPhaseObserver",
    "phase_state_snapshot",
]
