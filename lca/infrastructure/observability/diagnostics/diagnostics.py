"""Cognitive diagnostics — root-cause patterns from spec §24.5.

Each pattern encodes the canonical "what to check" sequence for a
named failure mode.  The CLI (``lca-ops diagnose``) drives these;
unit tests drive them against synthetic journal runs.

Patterns:
- ``model_not_seen`` — manifest missing a kind the user expected.
- ``loop_stuck``     — repeated tool calls / no progress.
- ``memory_poisoned`` — a poisoned record reached the prompt.
- ``approval_rejected`` — an ApprovalResolved(false) was emitted.

Each pattern returns a list of ``Finding`` records the caller can
render (table / JSON / log).  No side effects.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import cast

from lca.contracts.atoms.enums import MemoryLayer
from lca.contracts.harness.tasks.session import SessionEvent
from lca.contracts.models.observability.journal import (
    ApprovalResolved,
    ContextManifested,
    GateDecided,
    InboxFollowupCreated,
    MemoryCommitted,
    StampedEvent,
    ToolInvoked,
)
from lca.infrastructure.observability.journal.engine.engine import RunStore

_CONTEXT_MANIFESTED_V1 = "context.manifested.v1"


def _manifest_evidence_from_session(
    session_events: Sequence[SessionEvent] | None,
) -> tuple[bool, tuple[str, ...]]:
    if not session_events:
        return False, ()
    kinds: list[str] = []
    for event in session_events:
        if event.type != _CONTEXT_MANIFESTED_V1:
            continue
        data = event.data if isinstance(event.data, dict) else {}
        items = data.get("items")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get("kind"):
                    kinds.append(str(item["kind"]))
        digest = data.get("digest")
        if digest:
            kinds.append(f"digest:{digest}")
    return bool(kinds or any(e.type == _CONTEXT_MANIFESTED_V1 for e in session_events)), tuple(kinds)


class DiagnosePattern(str, Enum):
    """The four canonical patterns from spec §24.5."""

    MODEL_NOT_SEEN = "model_not_seen"
    LOOP_STUCK = "loop_stuck"
    MEMORY_POISONED = "memory_poisoned"
    APPROVAL_REJECTED = "approval_rejected"


@dataclass(frozen=True)
class Finding:
    """A single root-cause observation."""

    pattern: DiagnosePattern
    severity: str  # "low" | "medium" | "high"
    summary: str
    evidence_refs: tuple[int, ...] = ()
    detail: str = ""


@dataclass(frozen=True)
class DiagnosisReport:
    pattern: DiagnosePattern
    findings: tuple[Finding, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.findings


def diagnose_model_not_seen(
    store: RunStore,
    *,
    expected_kind: str,
    trace_id: str | None = None,
    session_events: Sequence[SessionEvent] | None = None,
) -> DiagnosisReport:
    """Diagnose why the model didn't see an expected manifest item kind.

    Prefers Session ``context.manifested.v1`` facts (ADR-0192); falls back to
    legacy Journal ``ContextManifested`` when session snapshot is absent.
    """
    findings: list[Finding] = []

    inbox = [
        e.seq
        for e in store.events
        if isinstance(e.event, InboxFollowupCreated)
        and (trace_id is None or e.scope.trace_id == trace_id)
    ]
    manifests = [
        e.seq
        for e in store.events
        if isinstance(e.event, ContextManifested)
        and (trace_id is None or e.scope.trace_id == trace_id)
    ]
    session_has_manifest, session_kinds = _manifest_evidence_from_session(session_events)

    if not inbox:
        findings.append(
            Finding(
                pattern=DiagnosePattern.MODEL_NOT_SEEN,
                severity="medium",
                summary=f"No InboxFollowupCreated events; '{expected_kind}' cannot reach the prompt.",
                evidence_refs=(),
                detail=(
                    "Check: did /runs create the request via Inbox.followup? "
                    "Production must go through Inbox → journal → inbox-facts sensor."
                ),
            )
        )
        return DiagnosisReport(DiagnosePattern.MODEL_NOT_SEEN, tuple(findings))

    if not manifests and not session_has_manifest:
        findings.append(
            Finding(
                pattern=DiagnosePattern.MODEL_NOT_SEEN,
                severity="high",
                summary="No context manifest facts; PerceiveHub or PhaseFactEmitter did not run.",
                evidence_refs=tuple(inbox),
                detail="Check: PerceiveHub is wired; PhaseFactEmitter emits context.manifested.v1.",
            )
        )
        return DiagnosisReport(DiagnosePattern.MODEL_NOT_SEEN, tuple(findings))

    if session_has_manifest:
        item_kinds = tuple(
            k for k in session_kinds if not k.startswith("digest:")
        )
        if expected_kind not in item_kinds:
            findings.append(
                Finding(
                    pattern=DiagnosePattern.MODEL_NOT_SEEN,
                    severity="medium",
                    summary=(
                        f"Session manifest has no '{expected_kind}' item; "
                        f"observed: {item_kinds or session_kinds}"
                    ),
                    evidence_refs=(),
                    detail=(
                        "Check: Profile references the sensor; Budgeter didn't drop it; "
                        "the sensor's read didn't throw."
                    ),
                )
            )
        return DiagnosisReport(DiagnosePattern.MODEL_NOT_SEEN, tuple(findings))

    last_manifest_seq = manifests[-1]
    stamped_manifest = store.get(last_manifest_seq)
    last_manifest = stamped_manifest.event if stamped_manifest is not None else None
    if not isinstance(last_manifest, ContextManifested):
        findings.append(
            Finding(
                pattern=DiagnosePattern.MODEL_NOT_SEEN,
                severity="high",
                summary="Last ContextManifested event has unexpected shape.",
                evidence_refs=(last_manifest_seq,),
            )
        )
        return DiagnosisReport(DiagnosePattern.MODEL_NOT_SEEN, tuple(findings))

    if expected_kind not in last_manifest.item_kinds:
        findings.append(
            Finding(
                pattern=DiagnosePattern.MODEL_NOT_SEEN,
                severity="medium",
                summary=(
                    f"Manifest at seq {last_manifest_seq} has no '{expected_kind}' "
                    f"item; observed kinds: {last_manifest.item_kinds}"
                ),
                evidence_refs=(last_manifest_seq,),
                detail=(
                    "Check: Profile references the sensor; Budgeter didn't drop it; "
                    "the sensor's read didn't throw."
                ),
            )
        )

    return DiagnosisReport(DiagnosePattern.MODEL_NOT_SEEN, tuple(findings))


def diagnose_loop_stuck(
    store: RunStore,
    *,
    window: int = 10,
    trace_id: str | None = None,
    session_events: Sequence[SessionEvent] | None = None,
) -> DiagnosisReport:
    """Diagnose why the loop is stuck in repeated patterns.

    Spec §24.5.3: count recent tool invocations + GateDecided events.
    Session ``gate.decided.v1`` facts are consulted when journal
    ``GateDecided`` events are absent (ADR-0191 migration).
    """
    findings: list[Finding] = []
    tool_events: list[StampedEvent] = [
        e
        for e in store.events
        if isinstance(e.event, ToolInvoked) and (trace_id is None or e.scope.trace_id == trace_id)
    ]
    gate_events: list[StampedEvent] = [
        e
        for e in store.events
        if isinstance(e.event, GateDecided) and (trace_id is None or e.scope.trace_id == trace_id)
    ]

    if len(tool_events) < window:
        return DiagnosisReport(DiagnosePattern.LOOP_STUCK, ())

    recent = tool_events[-window:]
    tool_names = [cast("ToolInvoked", e.event).tool_name for e in recent]
    repeats = sum(1 for i in range(1, len(tool_names)) if tool_names[i] == tool_names[i - 1])
    if repeats >= window - 1:
        warnings = [e for e in gate_events if cast("GateDecided", e.event).verdict == "warn"]
        session_warn_count = _session_gate_warn_count(session_events)
        if not warnings and session_warn_count == 0:
            findings.append(
                Finding(
                    pattern=DiagnosePattern.LOOP_STUCK,
                    severity="high",
                    summary=(
                        "Tool name repeated in last "
                        f"{window} invocations with no GateDecided warn; "
                        "LoopBreaker may not be wired."
                    ),
                    evidence_refs=tuple(e.seq for e in recent),
                    detail="Check: RepeatToolCallGate is on the chain.",
                )
            )
        else:
            warn_count = len(warnings) if warnings else session_warn_count
            evidence_refs = tuple(e.seq for e in warnings) if warnings else (-1,)
            findings.append(
                Finding(
                    pattern=DiagnosePattern.LOOP_STUCK,
                    severity="medium",
                    summary=(
                        f"{warn_count} GateDecided warn events but loop still repeats; "
                        "Brain may not be reading the PolicyFact fold."
                    ),
                    evidence_refs=evidence_refs,
                )
            )

    return DiagnosisReport(DiagnosePattern.LOOP_STUCK, tuple(findings))


def _session_gate_warn_count(session_events: Sequence[SessionEvent] | None) -> int:
    if not session_events:
        return 0
    count = 0
    for event in session_events:
        if event.type != "gate.decided.v1":
            continue
        data = event.data if isinstance(event.data, dict) else {}
        if data.get("verdict") == "warn":
            count += 1
    return count


def diagnose_memory_poisoned(store: RunStore) -> DiagnosisReport:
    """Diagnose whether a poisoned memory record reached the prompt.

    Spec §24.5.4: walk MemoryCommitted events; flag any record with
    authority=model_inference that was committed without screening.
    """
    findings: list[Finding] = []
    for stamped in store.events:
        event = stamped.event
        if not isinstance(event, MemoryCommitted):
            continue
        # In v3.0 we don't have a PoisonPatternRegistry on the
        # committed event itself; the heuristic is: layer=procedural
        # + record_kind=auto_acquired are higher-risk.  Future ADR
        # will add the explicit poison flag.
        if event.layer == MemoryLayer.PROCEDURAL:
            findings.append(
                Finding(
                    pattern=DiagnosePattern.MEMORY_POISONED,
                    severity="low",
                    summary="Procedural memory commit; verify poison screening passed.",
                    evidence_refs=(stamped.seq,),
                )
            )

    return DiagnosisReport(DiagnosePattern.MEMORY_POISONED, tuple(findings))


def diagnose_approval_rejected(store: RunStore) -> DiagnosisReport:
    """Diagnose the chain around an ``ApprovalResolved(approved=False)``."""
    findings: list[Finding] = []
    for stamped in store.events:
        event = stamped.event
        if not isinstance(event, ApprovalResolved):
            continue
        if event.approved:
            continue
        findings.append(
            Finding(
                pattern=DiagnosePattern.APPROVAL_REJECTED,
                severity="high",
                summary=f"Approval {event.envelope_id} denied by {event.resolver!r}.",
                evidence_refs=(stamped.seq,),
                detail=(
                    "Check: tool risk level matches resolver's authority; "
                    "envelope.capability_grant is a subset of the principal's grant."
                ),
            )
        )
    return DiagnosisReport(DiagnosePattern.APPROVAL_REJECTED, tuple(findings))


def diagnose(
    store: RunStore,
    *,
    pattern: DiagnosePattern,
    **kwargs: object,
) -> DiagnosisReport:
    """Dispatch to the right pattern."""
    if pattern == DiagnosePattern.MODEL_NOT_SEEN:
        return diagnose_model_not_seen(
            store,
            expected_kind=str(kwargs.get("expected_kind", "")),
            trace_id=cast("str | None", kwargs.get("trace_id")),
        )
    if pattern == DiagnosePattern.LOOP_STUCK:
        return diagnose_loop_stuck(
            store,
            window=int(cast("str", kwargs.get("window", 10))),
            trace_id=cast("str | None", kwargs.get("trace_id")),
            session_events=cast("Sequence[SessionEvent] | None", kwargs.get("session_events")),
        )
    if pattern == DiagnosePattern.MEMORY_POISONED:
        return diagnose_memory_poisoned(store)
    if pattern == DiagnosePattern.APPROVAL_REJECTED:
        return diagnose_approval_rejected(store)
    raise ValueError(f"unknown pattern: {pattern!r}")


__all__ = [
    "DiagnosePattern",
    "DiagnosisReport",
    "Finding",
    "diagnose",
    "diagnose_approval_rejected",
    "diagnose_loop_stuck",
    "diagnose_memory_poisoned",
    "diagnose_model_not_seen",
]
