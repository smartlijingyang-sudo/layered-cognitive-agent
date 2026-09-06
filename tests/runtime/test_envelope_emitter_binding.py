"""R4 tests for EnvelopeEmitter Protocol + SpineEnvelopeEmitter default impl (ADR-0177).

The Protocol is the SSOT for runtime/agent envelope-emit helpers; the
default impl wraps the existing spine reflectors.  This test drives
both ends to prove:

1. Protocol signatures match what runtime/agent callers will use.
2. SpineEnvelopeEmitter emits via ``runtime_emit`` / ``agent_spawn_emit``.
3. SpineEnvelopeEmitter is a no-op when the emit helper raises
   (preserves the existing ``_safe_append`` swallow behaviour).
"""

from __future__ import annotations

from unittest.mock import patch

from lca.runtime.projection.envelope_emitter import SpineEnvelopeEmitter


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
        "emit_exception_finally",
        "emit_agent_loop_iteration_start",
        "emit_agent_loop_iteration_end",
        "emit_event_publisher_publish",
    ):
        assert callable(getattr(emitter, name)), f"{name} not callable"


def test_spine_envelope_emitter_dispatches_to_runtime_emit() -> None:
    """Reducer apply emits flow through ``runtime_emit`` FactGateway helpers."""
    calls: list[tuple[str, dict[str, str]]] = []

    def _start(*, method: str) -> None:
        calls.append(("start", {"method": method}))

    def _end(*, method: str, outcome: str) -> None:
        calls.append(("end", {"method": method, "outcome": outcome}))

    emitter = SpineEnvelopeEmitter()
    with patch(
        "lca.runtime.envelope_emitter.emit_runtime_reducer_apply_start",
        side_effect=_start,
    ), patch(
        "lca.runtime.envelope_emitter.emit_runtime_reducer_apply_end",
        side_effect=_end,
    ):
        emitter.emit_reducer_apply_start(method="apply_step_advanced")
        emitter.emit_reducer_apply_end(method="apply_step_advanced", outcome="success")

    assert calls == [
        ("start", {"method": "apply_step_advanced"}),
        ("end", {"method": "apply_step_advanced", "outcome": "success"}),
    ]


def test_envelope_emitter_does_not_own_exception_caught() -> None:
    """``exception.caught`` is observability SSOT, not an envelope method."""
    from lca.contracts.protocols.runtime.envelope.envelope_emitter import EnvelopeEmitter

    assert "emit_exception_caught" not in EnvelopeEmitter.__dict__
    assert not hasattr(SpineEnvelopeEmitter, "emit_exception_caught")


def test_spine_envelope_emitter_dispatches_to_agent_spawn_emit() -> None:
    """Agent-loop iteration emits flow through ``agent_spawn_emit`` helpers."""
    calls: list[tuple[str, dict[str, str]]] = []

    def _start(*, trace_id: str, role: str, iteration_kind: str) -> None:
        calls.append(("start", {"trace_id": trace_id, "role": role, "kind": iteration_kind}))

    def _end(*, trace_id: str, role: str, iteration_kind: str, outcome: str) -> None:
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

    emitter = SpineEnvelopeEmitter()
    with patch(
        "lca.runtime.envelope_emitter.emit_agent_loop_iteration_start",
        side_effect=_start,
    ), patch(
        "lca.runtime.envelope_emitter.emit_agent_loop_iteration_end",
        side_effect=_end,
    ):
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
        pass

    emitter = SpineEnvelopeEmitter()
    with patch(
        "lca.runtime.envelope_emitter.emit_runtime_reducer_apply_start",
        side_effect=RuntimeError("spine unavailable"),
    ):
        emitter.emit_reducer_apply_start(method="x")
