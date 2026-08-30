"""Regression coverage for composable, passive phase observation plugins."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field

import pytest

from lca.contracts.capabilities import PHASE_OBSERVER, PHASE_OBSERVER_REGISTRY
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_phase_graph import SemanticPhase
from lca.contracts.protocols.journal.phase_observation import PhaseStateSnapshot
from lca.harness.declarative.phase_observation import (
    CompositePhaseObserver,
    InMemoryPhaseObserverRegistry,
    ObserverFailureMode,
    PhaseObserverContribution,
    PhaseObserverError,
    phase_state_snapshot,
)
from lca.plugins.composer.runtime_assembly import _require_runtime
from lca.plugins.providers import phase_observer, phase_observer_tracing


@dataclass
class _RecordingObserver:
    name: str
    events: list[str]

    def observe(
        self,
        *,
        semantic_phase: SemanticPhase,
        state: PhaseStateSnapshot,
    ) -> AbstractContextManager[object]:
        del semantic_phase, state
        return self._record()

    @contextmanager
    def _record(self) -> Iterator[None]:
        self.events.append(f"{self.name}.enter")
        try:
            yield
        finally:
            self.events.append(f"{self.name}.exit")


class _EnterFailingObserver:
    def observe(
        self,
        *,
        semantic_phase: SemanticPhase,
        state: PhaseStateSnapshot,
    ) -> AbstractContextManager[object]:
        del semantic_phase, state
        return _EnterFailingContext()


class _EnterFailingContext(AbstractContextManager[object]):
    def __enter__(self) -> object:
        raise RuntimeError("observer unavailable")

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> bool:
        del exc_type, exc_value, traceback
        return False


class _SuppressingObserver:
    def observe(
        self,
        *,
        semantic_phase: SemanticPhase,
        state: PhaseStateSnapshot,
    ) -> AbstractContextManager[object]:
        del semantic_phase, state
        return self._suppress()

    @contextmanager
    def _suppress(self) -> Iterator[None]:
        try:
            yield
        except ValueError:
            return


@dataclass
class _PluginContext:
    services: dict[str, object] = field(default_factory=dict)

    def provide(self, key: object, value: object, **kwargs: object) -> None:
        del kwargs
        self.services[str(key)] = value

    def require(self, key: object) -> object:
        return self.services[str(key)]


def _state() -> PhaseStateSnapshot:
    return phase_state_snapshot(AgentState(trace_id="trace", task="task", budget=Budget()))


def test_registry_orders_contributions_and_rejects_duplicate_ids() -> None:
    registry = InMemoryPhaseObserverRegistry()
    events: list[str] = []
    registry.register(PhaseObserverContribution("late", _RecordingObserver("late", events), 200))
    registry.register(PhaseObserverContribution("early", _RecordingObserver("early", events), 10))

    assert [item.id for item in registry.snapshot()] == ["early", "late"]
    with pytest.raises(KeyError, match="already registered"):
        registry.register(PhaseObserverContribution("early", _RecordingObserver("other", events)))


def test_composite_observer_nests_contributions_in_deterministic_order() -> None:
    events: list[str] = []
    observer = CompositePhaseObserver(
        (
            PhaseObserverContribution("late", _RecordingObserver("late", events), 200),
            PhaseObserverContribution("early", _RecordingObserver("early", events), 10),
        )
    )

    with observer.observe(semantic_phase=SemanticPhase.THINK, state=_state()):
        events.append("executor")

    assert events == ["early.enter", "late.enter", "executor", "late.exit", "early.exit"]


def test_composite_freezes_registry_snapshot_for_runtime_locality() -> None:
    registry = InMemoryPhaseObserverRegistry()
    events: list[str] = []
    registry.register(PhaseObserverContribution("first", _RecordingObserver("first", events)))
    observer = CompositePhaseObserver(registry.snapshot())
    registry.register(PhaseObserverContribution("later", _RecordingObserver("later", events)))

    with observer.observe(semantic_phase=SemanticPhase.PERCEIVE, state=_state()):
        events.append("executor")

    assert events == ["first.enter", "executor", "first.exit"]
    assert [item.id for item in observer.contributions] == ["first"]


def test_observer_failure_is_fail_open_by_default() -> None:
    observer = CompositePhaseObserver(
        (PhaseObserverContribution("unavailable", _EnterFailingObserver()),)
    )
    events: list[str] = []

    with observer.observe(semantic_phase=SemanticPhase.ACT, state=_state()):
        events.append("executor")

    assert events == ["executor"]


def test_strict_observer_failure_fails_closed_with_contribution_identity() -> None:
    observer = CompositePhaseObserver(
        (PhaseObserverContribution("audit", _EnterFailingObserver()),),
        failure_mode=ObserverFailureMode.FAIL_CLOSED,
    )

    with (
        pytest.raises(PhaseObserverError, match=r"'audit'.*enter"),
        observer.observe(semantic_phase=SemanticPhase.ACT, state=_state()),
    ):
        pytest.fail("executor must not run after strict observer failure")


def test_observer_cannot_suppress_executor_error() -> None:
    observer = CompositePhaseObserver(
        (PhaseObserverContribution("passive", _SuppressingObserver()),)
    )

    with (
        pytest.raises(ValueError, match="executor failed"),
        observer.observe(semantic_phase=SemanticPhase.THINK, state=_state()),
    ):
        raise ValueError("executor failed")


@pytest.mark.asyncio
async def test_plugins_contribute_then_freeze_the_default_tracing_observer() -> None:
    registry = InMemoryPhaseObserverRegistry()
    tracing_context = _PluginContext({PHASE_OBSERVER_REGISTRY.key: registry})
    await phase_observer_tracing.setup.setup(tracing_context, phase_observer_tracing.Config())

    provider_context = _PluginContext({PHASE_OBSERVER_REGISTRY.key: registry})
    await phase_observer.setup.setup(provider_context, phase_observer.Config())
    composite = provider_context.services[PHASE_OBSERVER.key]

    assert isinstance(composite, CompositePhaseObserver)
    assert composite.failure_mode is ObserverFailureMode.FAIL_OPEN
    assert [item.id for item in composite.contributions] == ["tracing"]


class _RuntimeLike:
    async def run(self, *args: object, **kwargs: object) -> object:
        del args, kwargs
        return object()

    async def resume(self, *args: object, **kwargs: object) -> object:
        del args, kwargs
        return object()


def test_runtime_factory_output_must_implement_runtime_protocol() -> None:
    runtime = _RuntimeLike()

    assert _require_runtime(runtime) is runtime
    with pytest.raises(TypeError, match="must return Runtime"):
        _require_runtime(object())
