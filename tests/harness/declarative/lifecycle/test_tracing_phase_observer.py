"""Tests for ``TracingPhaseObserver`` and the injected ``SpanOpener`` port.

The observer must not import the infrastructure ``span`` implementation; it
receives a ``SpanOpener`` from the composition boundary.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lca.contracts.atoms.telemetry.telemetry import ATTR_AGENT_ROLE, ATTR_STEP, SpanName
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import SemanticPhase
from lca.contracts.protocols.journal.phase.observation import PhaseStateSnapshot
from lca.harness.declarative.lifecycle.phase_observation import TracingPhaseObserver

REPO = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class _OpenedSpan:
    name: object
    attributes: dict[str, Any]


class _RecordingSpanOpener:
    def __init__(self) -> None:
        self.opened: list[_OpenedSpan] = []

    def __call__(self, name: object, **attributes: Any) -> AbstractContextManager[object]:
        self.opened.append(_OpenedSpan(name, attributes))
        return nullcontext()


@contextmanager
def _custom_context(_name: object, **_attributes: Any) -> Iterator[None]:
    yield


def _state(step: int = 3) -> PhaseStateSnapshot:
    return PhaseStateSnapshot(
        trace_id="trace-1",
        agent_role="assistant",
        step=step,
        status=TaskStatus.WORKING,
        budget=None,  # type: ignore[arg-type]
    )


def test_tracing_observer_opens_span_for_known_phase() -> None:
    opener = _RecordingSpanOpener()
    observer = TracingPhaseObserver(span_opener=opener)
    with observer.observe(semantic_phase=SemanticPhase.THINK, state=_state()):
        pass
    assert len(opener.opened) == 1
    assert opener.opened[0].name == SpanName.LOOP_PHASE_THINK
    assert opener.opened[0].attributes[ATTR_AGENT_ROLE] == "assistant"
    assert opener.opened[0].attributes[ATTR_STEP] == 3


def test_tracing_observer_returns_nullcontext_for_unknown_phase() -> None:
    opener = _RecordingSpanOpener()
    observer = TracingPhaseObserver(span_opener=opener)
    with observer.observe(semantic_phase="unknown-phase", state=_state()):  # type: ignore[arg-type]
        pass
    assert opener.opened == []


def test_tracing_observer_default_is_noop() -> None:
    observer = TracingPhaseObserver()
    with observer.observe(semantic_phase=SemanticPhase.PERCEIVE, state=_state()):
        pass  # Must not raise without an injected span opener.


def test_tracing_observer_uses_injected_context_manager() -> None:
    observer = TracingPhaseObserver(span_opener=_custom_context)
    with observer.observe(semantic_phase=SemanticPhase.ACT, state=_state()):
        pass  # The injected opener's context is entered.


def test_phase_observation_module_has_no_infrastructure_import() -> None:
    source = (
        REPO / "lca" / "harness" / "declarative" / "lifecycle" / "phase_observation.py"
    ).read_text(encoding="utf-8")
    assert "lca.infrastructure" not in source
    assert "SpanOpener" in source
