"""Adapter: agent_lab event_log graph ↔ LCA Session.append / snapshot_events.

LCA contracts consumed (write):
  - lca.session.append.Session.append(event_type, data, ...)
  - lca.session.append.Session.snapshot_events(from_seq, to_seq_exclusive)

agent_lab provides (this file):
  - LcaEventEmitProvider: wraps Session.append → event_fact artifact
    (seq + id).
  - LcaEventTailProvider: wraps Session.snapshot_events → events list
    artifact.

Both providers follow the fixture_session_name / session_factory / fallback
resolution pattern. The fallback is a process-local _NoopSession that
increments a counter — sufficient for tests and dry runs without a real
LCA runtime.

The fixture session registry is separate from lca_memory.py; documented
here to avoid confusion. Tests may share one Session instance across emit
and tail providers — that is intentional and safe (same underlying log).
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind

# ---------------------------------------------------------------------------
# SessionEvent — lazy import with local fallback
# ---------------------------------------------------------------------------


def _try_import_session_event() -> type | None:
    """Lazy-import the real SessionEvent dataclass from lca_kernel."""
    try:
        from lca_kernel.events.session.session import SessionEvent  # type: ignore[import-not-found]

        return SessionEvent
    except ImportError:
        return None


def _try_import_session_class() -> type | None:
    """Lazy-import the real Session from lca.session.append."""
    try:
        from lca.session.append import Session  # type: ignore[import-not-found]

        return Session
    except ImportError:
        return None


@dataclass(frozen=True)
class _LocalSessionEvent:
    """Minimal SessionEvent stand-in when lca_kernel is not importable.

    Mirrors the frozen dataclass shape at
    lca/contracts/harness/tasks/session.py:SessionEvent — enough for tests
    and dry runs to produce seq / id / type / data / time / actor /
    visibility / ignorable / surface_op / source_event_seqs.
    """

    type: str
    seq: int
    time: int
    data: dict[str, Any]
    session_id: str
    actor: str | None = None
    provider: str | None = None
    visibility: str = "model"
    ignorable: bool = False
    surface_op: Any | None = None
    source_event_seqs: tuple[int, ...] | None = None

    @property
    def id(self) -> str:
        return self.session_id


def _resolve_session_event_cls() -> type:
    """Return the real SessionEvent if importable, else the local stand-in."""
    cls = _try_import_session_event()
    return cls if cls is not None else _LocalSessionEvent


# ---------------------------------------------------------------------------
# _NoopSession — fallback when no real Session is configured
# ---------------------------------------------------------------------------


class _NoopSession:
    """Fallback Session-like object with append() and snapshot_events().

    Stores events in a simple list; increments a counter per append. The
    session_id is a random UUID. Sufficient for tests and dry runs.
    """

    def __init__(self, session_id: str | None = None) -> None:
        self._id = session_id or f"noop-{uuid.uuid4().hex[:12]}"
        self._log: list[Any] = []
        self._lock = threading.Lock()

    @property
    def id(self) -> str:
        return self._id

    @property
    def seq(self) -> int:
        return len(self._log)

    def append(
        self,
        event_type: str,
        data: Any,
        *,
        actor: str | None = None,
        visibility: str = "model",
        ignorable: bool = False,
        surface_op: Any | None = None,
        source_event_seqs: tuple[int, ...] | None = None,
    ) -> Any:
        event_cls = _resolve_session_event_cls()
        with self._lock:
            seq = len(self._log)
            event = event_cls(
                type=event_type,
                seq=seq,
                time=int(time.time() * 1000),
                data=dict(data) if isinstance(data, dict) else {"value": data},
                session_id=self._id,
                actor=actor,
                visibility=visibility,
                ignorable=ignorable,
                surface_op=surface_op,
                source_event_seqs=source_event_seqs,
            )
            self._log.append(event)
            return event

    def snapshot_events(
        self,
        from_seq: int = 0,
        to_seq_exclusive: int | None = None,
    ) -> tuple[Any, ...]:
        with self._lock:
            end = (
                len(self._log)
                if to_seq_exclusive is None
                else min(to_seq_exclusive, len(self._log))
            )
            return tuple(self._log[from_seq:end])


# ---------------------------------------------------------------------------
# Fixture session registry (separate from lca_memory.py)
# ---------------------------------------------------------------------------

_FIXTURE_SESSIONS: dict[str, Any] = {}


def register_fixture_session(name: str, session: Any) -> None:
    """Register a Session instance under a name for test use."""
    _FIXTURE_SESSIONS[name] = session


def unregister_fixture_session(name: str) -> None:
    """Remove a previously registered fixture session."""
    _FIXTURE_SESSIONS.pop(name, None)


# ---------------------------------------------------------------------------
# Session resolution helpers
# ---------------------------------------------------------------------------


def _resolve_session(config: dict[str, Any]) -> Any:
    """Resolve a Session from provider_config.

    Resolution order:
      1. fixture_session_name → _FIXTURE_SESSIONS lookup
      2. session_factory → module:Class dotted import
      3. Fallback: _NoopSession()
    """
    cfg = config.get("provider_config") or {}
    name = cfg.get("fixture_session_name")
    if name and name in _FIXTURE_SESSIONS:
        return _FIXTURE_SESSIONS[name]
    factory = cfg.get("session_factory")
    if isinstance(factory, dict) and factory.get("ref"):
        return _import_and_instantiate(factory)
    return _NoopSession()


def _import_and_instantiate(factory: dict[str, Any]) -> Any:
    import importlib

    ref: str = factory["ref"]
    kwargs: dict[str, Any] = dict(factory.get("kwargs") or {})
    if ":" in ref:
        mod_path, _, attr = ref.partition(":")
        mod = importlib.import_module(mod_path)
        cls = getattr(mod, attr)
    else:
        mod = importlib.import_module(ref)
        cls = mod
    return cls(**kwargs)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _session_event_to_dict(event: Any) -> dict[str, Any]:
    """Convert a SessionEvent (real or local) to a plain dict."""
    return {
        "seq": getattr(event, "seq", 0),
        "type": getattr(event, "type", ""),
        "time": getattr(event, "time", 0),
        "data": dict(getattr(event, "data", {}) or {}),
        "session_id": getattr(event, "session_id", ""),
        "actor": getattr(event, "actor", None),
        "visibility": getattr(event, "visibility", "model"),
        "ignorable": bool(getattr(event, "ignorable", False)),
        "surface_op": getattr(event, "surface_op", None),
        "source_event_seqs": (
            list(event.source_event_seqs or [])
            if getattr(event, "source_event_seqs", None) is not None
            else None
        ),
    }


def _session_event_from_dict(d: dict[str, Any]) -> Any:
    """Reconstruct a SessionEvent (real or local) from a plain dict."""
    event_cls = _resolve_session_event_cls()
    return event_cls(
        type=str(d.get("type", "")),
        seq=int(d.get("seq", 0)),
        time=int(d.get("time", 0)),
        data=dict(d.get("data", {}) or {}),
        session_id=str(d.get("session_id", "")),
        actor=d.get("actor"),
        visibility=str(d.get("visibility", "model")),
        ignorable=bool(d.get("ignorable", False)),
        surface_op=d.get("surface_op"),
        source_event_seqs=(
            tuple(d["source_event_seqs"]) if d.get("source_event_seqs") is not None else None
        ),
    )


# ---------------------------------------------------------------------------
# LcaEventEmitProvider
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LcaEventEmitProvider:
    """Bridge agent_lab emit node → Session.append(event_type, data).

    Writes one durable fact to the Session. Returns an event_fact artifact
    containing the SessionEvent's seq and id.
    """

    _session: Any

    @classmethod
    def from_node_config(cls, config: dict[str, Any]) -> LcaEventEmitProvider:
        session = _resolve_session(config)
        return cls(_session=session)

    def emit(
        self,
        event_type_artifact: Artifact | None,
        event_data_artifact: Artifact | None,
    ) -> dict[str, Artifact]:
        event_type = _extract_text(event_type_artifact)
        event_data = _extract_fact(event_data_artifact)
        session_event = self._session.append(event_type, event_data)
        return {
            "event_fact": Artifact(
                kind=ArtifactKind.FACT,
                content={
                    "seq": getattr(session_event, "seq", 0),
                    "id": getattr(session_event, "session_id", getattr(session_event, "id", "")),
                    "type": getattr(session_event, "type", event_type),
                },
                schema_ref="event.fact.v1",
            )
        }


# ---------------------------------------------------------------------------
# LcaEventTailProvider
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LcaEventTailProvider:
    """Bridge agent_lab tail node → Session.snapshot_events(from_seq, limit).

    Reads recent events from the Session and returns them as a list
    artifact of dicts {seq, type, time, data, actor, visibility}.
    """

    _session: Any

    @classmethod
    def from_node_config(cls, config: dict[str, Any]) -> LcaEventTailProvider:
        session = _resolve_session(config)
        return cls(_session=session)

    def tail(
        self,
        in_from_seq_artifact: Artifact | None,
        in_limit_artifact: Artifact | None,
    ) -> dict[str, Artifact]:
        from_seq = _extract_int(in_from_seq_artifact, default=0)
        limit = _extract_int(in_limit_artifact, default=100)
        to_seq_exclusive = from_seq + limit
        events = self._session.snapshot_events(
            from_seq=from_seq,
            to_seq_exclusive=to_seq_exclusive,
        )
        event_dicts = [_session_event_to_dict(e) for e in events]
        return {
            "events": Artifact(
                kind=ArtifactKind.FACT,
                content=event_dicts,
                schema_ref="event.list.v1",
            )
        }


# ---------------------------------------------------------------------------
# Artifact extraction helpers
# ---------------------------------------------------------------------------


def _extract_text(artifact: Artifact | None) -> str:
    """Extract a string from a TEXT or FACT artifact."""
    if artifact is None:
        return ""
    content = artifact.content
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return str(content.get("text", content.get("value", "")))
    return str(content) if content is not None else ""


def _extract_fact(artifact: Artifact | None) -> dict[str, Any]:
    """Extract a dict from a FACT artifact."""
    if artifact is None:
        return {}
    content = artifact.content
    if isinstance(content, dict):
        return content
    if isinstance(content, list):
        return {"items": content}
    if isinstance(content, str):
        return {"value": content}
    return {}


def _extract_int(artifact: Artifact | None, default: int = 0) -> int:
    """Extract an integer from a TEXT or FACT artifact."""
    if artifact is None:
        return default
    content = artifact.content
    if isinstance(content, int):
        return content
    if isinstance(content, str):
        try:
            return int(content)
        except (ValueError, TypeError):
            return default
    if isinstance(content, dict):
        val = content.get("value", content.get("from_seq", content.get("limit", default)))
        try:
            return int(val)
        except (ValueError, TypeError):
            return default
    return default


__all__ = [
    "LcaEventEmitProvider",
    "LcaEventTailProvider",
    "_session_event_from_dict",
    "_session_event_to_dict",
    "register_fixture_session",
    "unregister_fixture_session",
]
