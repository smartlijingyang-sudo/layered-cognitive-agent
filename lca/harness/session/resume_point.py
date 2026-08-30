"""Serialize the stable approval resume point at the Session Spine seam.

Only one shape crosses this seam: :class:`ApprovalResumePoint`. The public
serialise / deserialise pair is the only contract for that round-trip; the two
snapshot adapters are 5-line shims that keep callers outside this module
ignorant of whether a snapshot or a payload arrives first.
"""

from __future__ import annotations

from collections.abc import Mapping

from lca.contracts.atoms.ids import RunId, TraceId
from lca.contracts.harness.collaboration.agent import ApprovalResumePoint
from lca.contracts.models.core.state import StateSnapshot
from lca.contracts.protocols.declarative.declarative_execution import PhaseRunCursor


def serialize_resume_point(point: ApprovalResumePoint) -> dict[str, object]:
    """Return JSON-compatible data for the append-only Session journal."""

    return {
        "approval_id": point.approval_id,
        "snapshot_id": point.snapshot_id,
        "step": point.step,
        "state_ref": point.state_ref,
        "plan_ref": point.plan_ref,
        "node_id": point.node_id,
        "visit_counts": [list(item) for item in point.visit_counts],
        "edge_counts": [list(item) for item in point.edge_counts],
        "artifacts": dict(point.artifacts),
        "causation_refs": list(point.causation_refs),
        "budget_snapshot": dict(point.budget_snapshot),
        "trace_id": point.trace_id,
        "run_id": point.run_id,
    }


def deserialize_resume_point(payload: Mapping[str, object]) -> ApprovalResumePoint:
    """Rebuild one point from its journal representation, failing closed."""

    return ApprovalResumePoint(
        approval_id=_text(payload, "approval_id"),
        snapshot_id=_text(payload, "snapshot_id"),
        step=_non_negative_int(payload["step"], "step"),
        state_ref=_text(payload, "state_ref"),
        plan_ref=_text(payload, "plan_ref"),
        node_id=_text(payload, "node_id"),
        visit_counts=_pairs(payload["visit_counts"]),
        edge_counts=_triples(payload["edge_counts"]),
        artifacts=_mapping(payload["artifacts"], "artifacts"),
        causation_refs=_strings(payload["causation_refs"], "causation_refs"),
        budget_snapshot={
            key: _non_negative_int(value, f"budget_snapshot[{key!r}]")
            for key, value in _mapping(payload["budget_snapshot"], "budget_snapshot").items()
        },
        trace_id=TraceId(_optional_text(payload, "trace_id")),
        run_id=RunId(_optional_text(payload, "run_id")),
    )


def resume_point_to_state_snapshot(point: ApprovalResumePoint) -> StateSnapshot:
    """Reconstruct the existing runtime snapshot without reviving a live object."""

    return StateSnapshot(
        snapshot_id=point.snapshot_id,
        step=point.step,
        state_ref=point.state_ref,
        trace_id=point.trace_id,
        run_id=point.run_id,
        phase_cursor=PhaseRunCursor(
            plan_ref=point.plan_ref,
            node_id=point.node_id,
            visit_counts=point.visit_counts,
            edge_counts=point.edge_counts,
            artifacts=dict(point.artifacts),
            causation_refs=point.causation_refs,
            budget_snapshot=dict(point.budget_snapshot),
        ),
    )


def resume_point_from_state_snapshot(approval_id: str, snapshot: object) -> ApprovalResumePoint:
    """Extract the serializable recovery surface from an existing runtime snapshot."""

    cursor = getattr(snapshot, "phase_cursor", None)
    if cursor is None:
        raise ValueError("approval resume requires a declarative phase_cursor")
    return ApprovalResumePoint(
        approval_id=approval_id,
        snapshot_id=_attr_text(snapshot, "snapshot_id"),
        step=_attr_non_negative_int(snapshot, "step"),
        state_ref=_attr_text(snapshot, "state_ref"),
        plan_ref=_attr_text(cursor, "plan_ref"),
        node_id=_attr_text(cursor, "node_id"),
        visit_counts=tuple((str(name), int(count)) for name, count in cursor.visit_counts),
        edge_counts=tuple(
            (str(source), str(target), int(count)) for source, target, count in cursor.edge_counts
        ),
        artifacts=dict(cursor.artifacts),
        causation_refs=tuple(str(reference) for reference in cursor.causation_refs),
        budget_snapshot={str(key): int(value) for key, value in cursor.budget_snapshot.items()},
        trace_id=TraceId(_attr_optional_text(snapshot, "trace_id")),
        run_id=RunId(_attr_optional_text(snapshot, "run_id")),
    )


def _text(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"resume point {field} must be a non-empty string")
    return value


def _optional_text(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field, "")
    return value if isinstance(value, str) else ""


def _non_negative_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"resume point {field} must be a non-negative integer")
    return value


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"resume point {field} must be a mapping")
    return {str(key): item for key, item in value.items()}


def _strings(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"resume point {field} must be a sequence")
    if not all(isinstance(item, str) for item in value):
        raise ValueError(f"resume point {field} must contain strings")
    return tuple(value)


def _pairs(value: object) -> tuple[tuple[str, int], ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("resume point visit_counts must be a sequence")
    pairs: list[tuple[str, int]] = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError("resume point visit_counts must contain [name, count] pairs")
        pairs.append((str(item[0]), _non_negative_int(item[1], "visit_counts count")))
    return tuple(pairs)


def _triples(value: object) -> tuple[tuple[str, str, int], ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("resume point edge_counts must be a sequence")
    triples: list[tuple[str, str, int]] = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            raise ValueError(
                "resume point edge_counts must contain [source, target, count] triples"
            )
        triples.append(
            (str(item[0]), str(item[1]), _non_negative_int(item[2], "edge_counts count"))
        )
    return tuple(triples)


def _attr_text(value: object, field: str) -> str:
    candidate = getattr(value, field, None)
    if not isinstance(candidate, str) or not candidate.strip():
        raise ValueError(f"resume point {field} must be a non-empty string")
    return candidate


def _attr_optional_text(value: object, field: str) -> str:
    candidate = getattr(value, field, "")
    return candidate if isinstance(candidate, str) else ""


def _attr_non_negative_int(value: object, field: str) -> int:
    return _non_negative_int(getattr(value, field, None), field)


__all__ = [
    "deserialize_resume_point",
    "resume_point_from_state_snapshot",
    "resume_point_to_state_snapshot",
    "serialize_resume_point",
]
