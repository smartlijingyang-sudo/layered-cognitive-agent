"""R4 tests for EnvelopeEmitter Protocol + SpineEnvelopeEmitter default impl (ADR-0177).

The Protocol is the SSOT for runtime/agent envelope-emit helpers; the
default impl wraps the existing spine reflectors.  This test drives
both ends to prove:

1. Protocol signatures match what runtime/agent callers will use.
2. SpineEnvelopeEmitter emits via the spine reflector module.
3. SpineEnvelopeEmitter is a no-op when the spine reflector raises
   (preserves the existing ``_safe_append`` swallow behaviour).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lca.runtime.envelope_emitter import SpineEnvelopeEmitter

if TYPE_CHECKING:
    import pytest


def test_spine_envelope_emitter_satisfies_protocol() -> None:
    """``SpineEnvelopeEmitter`` structurally satisfies ``EnvelopeEmitter``."""
    emitter = SpineEnvelopeEmitter()
    # Each Protocol method must be callable on the implementation.
    for name in (
        "emit_reducer_apply_start",
        "emit_reducer_apply_end",
        "emit_checkpoint_create",
        "emit_resume_start",
        "emit_resume_end",
        "emit_lifecycle_finally",
        "emit_exception_caught",
        "emit_exception_finally",
        "emit_agent_loop_iteration_start",
        "emit_agent_loop_iteration_end",
        "emit_event_publisher_publish",
    ):
        assert callable(getattr(emitter, name)), f"{name} not callable"


def test_spine_envelope_emitter_dispatches_to_runtime_reflector() -> None:
    """Reducer apply emits flow through ``emit_runtime_reducer_apply_*``."""
    calls: list[tuple[str, dict[str, str]]] = []

    class _FakeRuntime:
        def emit_runtime_reducer_apply_start(self, *, method: str) -> None:
            calls.append(("start", {"method": method}))

        def emit_runtime_reducer_apply_end(self, *, method: str, outcome: str) -> None:
            calls.append(("end", {"method": method, "outcome": outcome}))

    fake = _FakeRuntime()
    emitter = SpineEnvelopeEmitter()
    emitter._runtime = lambda: fake  # type: ignore[assignment]

    emitter.emit_reducer_apply_start(method="apply_step_advanced")
    emitter.emit_reducer_apply_end(method="apply_step_advanced", outcome="success")

    assert calls == [
        ("start", {"method": "apply_step_advanced"}),
        ("end", {"method": "apply_step_advanced", "outcome": "success"}),
    ]


def test_spine_envelope_emitter_forwards_exception_record_to_ssot_emitter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``emit_exception_caught`` forwards the normalized record unchanged.

    The record goes to the single emitter
    (``lca.infrastructure.observability.spine.exception_emit``), never to
    the 4-key reflector helper (ADR-0169 SSOT).
    """
    from lca.contracts.observability import exc_to_record
    from lca.infrastructure.observability.spine import exception_emit

    captured: list[object] = []

    def _capture(record: object) -> None:
        captured.append(record)

    monkeypatch.setattr(exception_emit, "emit_exception_caught", _capture)

    emitter = SpineEnvelopeEmitter()
    record = exc_to_record(ValueError("boom"), boundary="terminal_driver", trace_id="trace-env")
    emitter.emit_exception_caught(record)

    assert captured == [record]


def test_spine_envelope_emitter_dispatches_to_agent_spawn_reflector() -> None:
    """Agent-loop iteration emits flow through ``emit_agent_loop_iteration_*``."""
    calls: list[tuple[str, dict[str, str]]] = []

    class _FakeAgentSpawn:
        def emit_agent_loop_iteration_start(
            self,
            *,
            trace_id: str,
            role: str,
            iteration_kind: str,
        ) -> None:
            calls.append(("start", {"trace_id": trace_id, "role": role, "kind": iteration_kind}))

        def emit_agent_loop_iteration_end(
            self,
            *,
            trace_id: str,
            role: str,
            iteration_kind: str,
            outcome: str,
        ) -> None:
            calls.append(
                (
                    "end",
                    {
                        "trace_id": trace_id,
                        "role": role,
                        "kind": iteration_kind,
                        "outcome": outcome,
                    },
                )
            )

    fake = _FakeAgentSpawn()
    emitter = SpineEnvelopeEmitter()
    emitter._agent_spawn = lambda: fake  # type: ignore[assignment]

    emitter.emit_agent_loop_iteration_start(trace_id="t-1", role="coder", kind="fresh")
    emitter.emit_agent_loop_iteration_end(
        trace_id="t-1", role="coder", kind="fresh", outcome="success"
    )

    assert calls == [
        ("start", {"trace_id": "t-1", "role": "coder", "kind": "fresh"}),
        (
            "end",
            {
                "trace_id": "t-1",
                "role": "coder",
                "kind": "fresh",
                "outcome": "success",
            },
        ),
    ]


def test_spine_envelope_emitter_swallows_reflector_exceptions() -> None:
    """If the underlying reflector raises, the envelope emitter silently no-ops.

    The spine reflectors wrap ``spine.append`` in ``try/except`` so a
    broken sink never crashes the runtime.  ``SpineEnvelopeEmitter`` must
    preserve that behaviour even if a caller injects a misbehaving
    reflector stub.
    """

    class _Boom:
        def emit_runtime_reducer_apply_start(self, *, method: str) -> None:
            raise RuntimeError("spine unavailable")

    emitter = SpineEnvelopeEmitter()
    emitter._runtime = lambda: _Boom()  # type: ignore[assignment]

    # Must not raise.
    emitter.emit_reducer_apply_start(method="x")
