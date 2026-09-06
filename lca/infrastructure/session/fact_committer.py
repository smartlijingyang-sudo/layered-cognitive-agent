"""Session-backed FactCommitter (ADR-0192 E0/E2).

Maps declarative ``RunFact`` kinds and observations to Session catalog events
or authorized spine structural EPs. Replaces ``RuntimeJournalCommitter``'s
``record_runtime`` → Journal plane path for production runs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

import structlog

from lca.contracts.harness.memory.events import ContextInjected
from lca.contracts.protocols.act.command_envelope import RunFact
from lca.contracts.protocols.observability.fact_committer import FactCommitter
from lca.harness.session.emit import emit
from lca.infrastructure.observability.domain_event_publish import publish_structural_event
from lca.infrastructure.session.bindings import resolve_session_reader

_log = structlog.get_logger(__name__)


def _json_safe(value: object) -> object:
    if is_dataclass(value):
        return asdict(value)  # type: ignore[arg-type]
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class SessionFactCommitter(FactCommitter):
    """Route declarative facts to Session catalog or spine EPs."""

    def __init__(self, *, sequence: int = 0) -> None:
        self._sequence = sequence

    @property
    def sequence(self) -> int:
        return self._sequence

    def commit_fact(self, fact: RunFact, *, plan_ref: str, node_ref: str) -> str:
        self._sequence += 1
        kind = fact.kind or "unknown"
        payload = dict(fact.payload)

        if kind == "context.injected":
            return self._commit_context_injected(payload, node_ref=node_ref)

        if kind == "context.manifested":
            return self._commit_context_manifested_payload(payload, node_ref=node_ref)

        return self._commit_spine_fact(
            execution_point=f"phase.fact.{kind}" if not kind.startswith("phase.") else kind,
            payload={
                "plan_ref": plan_ref,
                "node_ref": node_ref,
                "fact_id": fact.fact_id,
                "kind": kind,
                "payload": _json_safe(payload),
            },
            node_ref=node_ref,
            fallback_label=f"{plan_ref}:{node_ref}:fact:{self._sequence}",
        )

    def commit_evidence(self, evidence_ref: str, *, plan_ref: str, node_ref: str) -> str:
        self._sequence += 1
        return self._commit_spine_fact(
            execution_point="phase.evidence",
            payload={"plan_ref": plan_ref, "evidence_ref": evidence_ref},
            node_ref=node_ref,
            fallback_label=evidence_ref,
        )

    def commit_observation(self, observation: object, *, plan_ref: str, node_ref: str) -> str:
        self._sequence += 1
        return self._commit_spine_fact(
            execution_point="effect.receipt",
            payload={
                "plan_ref": plan_ref,
                "observation_type": type(observation).__name__,
                "observation": _json_safe(observation),
            },
            node_ref=node_ref,
            fallback_label=f"{node_ref}:observation:{self._sequence}",
        )

    def _commit_context_injected(self, payload: Mapping[str, object], *, node_ref: str) -> str:
        session = resolve_session_reader()
        if session is None:
            _log.info(
                "fact_committer.no_session",
                kind="context.injected",
                payload=dict(payload),
            )
            return f"noop:context.injected:{self._sequence}"
        source = str(payload.get("source", "perceive"))
        content_ref = str(payload.get("content_ref", ""))
        model_visible = bool(payload.get("model_visible", True))
        event = emit(
            session,
            ContextInjected(source=source, content_ref=content_ref, model_visible=model_visible),
            actor=node_ref,
        )
        return f"{session.id}:{event.seq}"

    def _commit_context_manifested_payload(
        self, payload: Mapping[str, object], *, node_ref: str
    ) -> str:
        from lca.contracts.models.core.perception import ContextManifest
        from lca.infrastructure.session.cognitive_emit import emit_context_manifested

        session = resolve_session_reader()
        if session is None:
            _log.info(
                "fact_committer.no_session",
                kind="context.manifested",
                payload=dict(payload),
            )
            return f"noop:context.manifested:{self._sequence}"
        step = int(payload.get("step", 0))
        digest = str(payload.get("digest", ""))
        manifest = ContextManifest(items=(), digest=digest)
        event = emit_context_manifested(session, manifest, step=step, actor=node_ref)
        if event is None:
            return f"noop:context.manifested:{self._sequence}"
        return f"{session.id}:{getattr(event, 'seq', self._sequence)}"

    def _commit_spine_fact(
        self,
        *,
        execution_point: str,
        payload: dict[str, object],
        node_ref: str,
        fallback_label: str,
    ) -> str:
        from lca.plugins.events.publishers.spine_reflector_runtime.plugin import ReflectorClass

        ref = publish_structural_event(
            execution_point=execution_point,
            channel="fact",
            payload=payload,
            producer=ReflectorClass,
        )
        if ref is None:
            return fallback_label
        event_id = getattr(ref, "event_id", "") or ""
        return event_id or fallback_label


def emit_diagnostic(
    *,
    category: str,
    operation: str,
    plugin: str = "",
    attributes: dict[str, Any] | None = None,
    output: dict[str, Any] | None = None,
    status: str = "failed",
) -> None:
    """Structured diagnostic when Session unbound; spine EP when bound (ADR-0192).

    Replaces direct ``record_runtime`` from cognition for non-catalog diagnostics.
    """
    session = resolve_session_reader()
    payload = {
        "category": category,
        "operation": operation,
        "plugin": plugin,
        "status": status,
        "attributes": attributes or {},
        "output": output or {},
    }
    if session is None:
        _log.warning(
            "diagnostic.unbound",
            category=category,
            operation=operation,
            plugin=plugin,
            output=output,
        )
        return
    from lca.plugins.events.publishers.spine_reflector_runtime.plugin import ReflectorClass

    publish_structural_event(
        execution_point="runtime.diagnostic",
        channel="diagnostic",
        payload=payload,
        producer=ReflectorClass,
    )


__all__ = ["SessionFactCommitter", "emit_diagnostic"]
