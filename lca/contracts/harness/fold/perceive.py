"""Pure fold helpers for gate decisions and context manifests (ADR-0191 R1)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from lca.contracts.harness.tasks.session import SessionEvent
from lca.contracts.models.core.perceive.perception import ContextItem, ContextManifest
from lca.contracts.models.core.policy.gate_policy import GateDecided, PolicyFact

_GATE_DECIDED = "gate.decided.v1"
_CONTEXT_MANIFESTED = "context.manifested.v1"


def _payload(event: SessionEvent) -> dict[str, Any]:
    data = event.data
    return data if isinstance(data, dict) else {}


def _policy_fact_from_payload(payload: dict[str, Any]) -> PolicyFact | None:
    kind = payload.get("policy_fact_kind")
    if not isinstance(kind, str) or not kind:
        return None
    message = payload.get("policy_fact_message")
    source = payload.get("policy_fact_source")
    return PolicyFact(
        kind=kind,
        message=str(message or ""),
        source=str(source or ""),
    )


def _gate_decided_from_payload(payload: dict[str, Any]) -> GateDecided | None:
    event_id = payload.get("event_id")
    gate = payload.get("gate")
    verdict = payload.get("verdict")
    if not all(isinstance(value, str) and value for value in (event_id, gate, verdict)):
        return None
    is_rewritten = payload.get("is_rewritten")
    if not isinstance(is_rewritten, bool):
        return None
    tool_name = payload.get("tool_name")
    rationale = payload.get("rationale")
    return GateDecided(
        event_id=event_id,
        gate=gate,
        verdict=verdict,
        is_rewritten=is_rewritten,
        policy_fact=_policy_fact_from_payload(payload),
        tool_name=tool_name if isinstance(tool_name, str) else None,
        rationale=rationale if isinstance(rationale, str) else None,
    )


def _step_from_payload(payload: dict[str, Any]) -> int | None:
    step = payload.get("step")
    if isinstance(step, int) and not isinstance(step, bool):
        return step
    return None


def _context_item_from_wire(item: dict[str, Any]) -> ContextItem | None:
    kind = item.get("kind")
    provenance = item.get("provenance")
    if not isinstance(kind, str) or not kind:
        return None
    if not isinstance(provenance, str) or not provenance:
        return None
    payload_repr = item.get("payload_repr")
    extra = item.get("extra")
    return ContextItem(
        kind=kind,  # type: ignore[arg-type]
        payload=payload_repr,
        provenance=provenance,
        extra=dict(extra) if isinstance(extra, dict) else {},
    )


def fold_policy_facts_from_events(
    events: Sequence[SessionEvent],
    *,
    through_step: int,
) -> list[PolicyFact]:
    """Fold ``gate.decided.v1`` facts into ordered PolicyFact views through ``through_step``."""
    facts: list[PolicyFact] = []
    for event in events:
        if event.type != _GATE_DECIDED:
            continue
        payload = _payload(event)
        step = _step_from_payload(payload)
        if step is None or step > through_step:
            continue
        policy_fact = _policy_fact_from_payload(payload)
        if policy_fact is not None:
            facts.append(policy_fact)
    return facts


def fold_gate_decisions_from_events(
    events: Sequence[SessionEvent],
    *,
    step: int,
) -> list[GateDecided]:
    """Fold ``gate.decided.v1`` facts for one think step."""
    decisions: list[GateDecided] = []
    for event in events:
        if event.type != _GATE_DECIDED:
            continue
        payload = _payload(event)
        if _step_from_payload(payload) != step:
            continue
        gate_decided = _gate_decided_from_payload(payload)
        if gate_decided is not None:
            decisions.append(gate_decided)
    return decisions


def fold_context_manifest_from_events(
    events: Sequence[SessionEvent],
    *,
    step: int,
) -> ContextManifest | None:
    """Fold the latest ``context.manifested.v1`` fact for ``step``."""
    manifest: ContextManifest | None = None
    for event in events:
        if event.type != _CONTEXT_MANIFESTED:
            continue
        payload = _payload(event)
        if _step_from_payload(payload) != step:
            continue
        digest = payload.get("digest")
        raw_items = payload.get("items")
        if not isinstance(digest, str):
            continue
        if not isinstance(raw_items, (list, tuple)):
            continue
        items: list[ContextItem] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            item = _context_item_from_wire(raw_item)
            if item is not None:
                items.append(item)
        manifest = ContextManifest(items=tuple(items), digest=digest)
    return manifest


__all__ = [
    "fold_context_manifest_from_events",
    "fold_gate_decisions_from_events",
    "fold_policy_facts_from_events",
]
