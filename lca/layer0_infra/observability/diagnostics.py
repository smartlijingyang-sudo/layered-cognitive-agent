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

from dataclasses import dataclass, field
from enum import Enum
from typing import cast

from lca.contracts.atoms.enums import MemoryLayer
from lca.contracts.models.observability.journal import (
    ApprovalResolved,
    ContextManifested,
    GateDecided,
    InboxFollowupCreated,
    MemoryCommitted,
    StampedEvent,
    ToolInvoked,
)
from lca.layer0_infra.observability.journal.engine import RunStore


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
) -> DiagnosisReport:
    """Diagnose why the model didn't see an expected manifest item kind.

    Spec §24.5.2: walk
        journal → InboxFollowupCreated → inbox-facts sensor → Hub.merge →
        Budgeter.select → Manifest.items → Brain.think(manifest)

    The check stops at the earliest step where evidence is missing.
    """
    findings: list[Finding] = []

    inbox = [
        e.seq for e in store.events
        if isinstance(e.event, InboxFollowupCreated)
        and (trace_id is None or e.scope.trace_id == trace_id)
    ]
    manifests = [
        e.seq for e in store.events
        if isinstance(e.event, ContextManifested)
        and (trace_id is None or e.scope.trace_id == trace_id)
    ]

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

    if not manifests:
        findings.append(
            Finding(
                pattern=DiagnosePattern.MODEL_NOT_SEEN,
                severity="high",
                summary="No ContextManifested events; Hub did not run.",
                evidence_refs=tuple(inbox),
                detail="Check: PerceiveHub is wired into CognitiveRuntime.",
            )
        )
        return DiagnosisReport(DiagnosePattern.MODEL_NOT_SEEN, tuple(findings))

    last_manifest_seq = manifests[-1]
    last_manifest = store.get_event(last_manifest_seq)
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
) -> DiagnosisReport:
    """Diagnose why the loop is stuck in repeated patterns.

    Spec §24.5.3: count recent tool invocations + GateDecided events.
    A repeat-tool-call warning without a budget hint is a Brain that
    is not reading the PolicyFact fold.
    """
    findings: list[Finding] = []
    tool_events: list[StampedEvent] = [
        e for e in store.events
        if isinstance(e.event, ToolInvoked)
        and (trace_id is None or e.scope.trace_id == trace_id)
    ]
    gate_events: list[StampedEvent] = [
        e for e in store.events
        if isinstance(e.event, GateDecided)
        and (trace_id is None or e.scope.trace_id == trace_id)
    ]

    if len(tool_events) < window:
        return DiagnosisReport(DiagnosePattern.LOOP_STUCK, ())

    recent = tool_events[-window:]
    tool_names = [cast(ToolInvoked, e.event).tool_name for e in recent]
    repeats = sum(
        1 for i in range(1, len(tool_names))
        if tool_names[i] == tool_names[i - 1]
    )
    if repeats >= window - 1:
        warnings = [e for e in gate_events if cast(GateDecided, e.event).verdict == "warn"]
        if not warnings:
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
            findings.append(
                Finding(
                    pattern=DiagnosePattern.LOOP_STUCK,
                    severity="medium",
                    summary=(
                        f"{len(warnings)} GateDecided warn events but loop still repeats; "
                        "Brain may not be reading the PolicyFact fold."
                    ),
                    evidence_refs=tuple(e.seq for e in warnings),
                )
            )

    return DiagnosisReport(DiagnosePattern.LOOP_STUCK, tuple(findings))


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
            window=int(cast(str, kwargs.get("window", 10))),
            trace_id=cast("str | None", kwargs.get("trace_id")),
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
