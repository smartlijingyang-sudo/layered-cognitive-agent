"""Adapter: agent_lab remember.sub_spec ↔ LCA Session.append + StateStore.save.

LCA contracts consumed (read-only):
  - lca.session.append.Session  — the sole fact-write seam (ADR-0186/0191/0194).
  - lca.contracts.protocols.runtime.infra.infra.StateStore — async save/load.

agent_lab provides (this file):
  - LcaRememberJournalProvider: wraps a Session and exposes
    ``append_journal(reflection, observation, decision, admitted)`` that
    calls ``session.append(event_type, data)`` and returns a journal_fact
    artifact (seq + id from the resulting SessionEvent).
  - LcaRememberStateStoreProvider: wraps a StateStore and exposes
    ``save_state(journal_fact)`` that calls
    ``state_store.save(state) -> str`` and returns a state_ref artifact
    plus a remember_signal.

Both providers follow the fixture_X_name / factory / fallback resolution
so node.config stays JSON-serializable for plan_hash.
"""

from __future__ import annotations

import asyncio
import importlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind

# ---------------------------------------------------------------------------
# Shared: process-local fixture registries (parallels lca_think.py)
# ---------------------------------------------------------------------------
_FIXTURE_SESSIONS: dict[str, Any] = {}
_FIXTURE_STATE_STORES: dict[str, Any] = {}


def register_fixture_session(name: str, session: Any) -> None:
    """Register a Session stub under *name* for test use."""
    _FIXTURE_SESSIONS[name] = session


def unregister_fixture_session(name: str) -> None:
    _FIXTURE_SESSIONS.pop(name, None)


def register_fixture_state_store(name: str, store: Any) -> None:
    """Register a StateStore stub under *name* for test use."""
    _FIXTURE_STATE_STORES[name] = store


def unregister_fixture_state_store(name: str) -> None:
    _FIXTURE_STATE_STORES.pop(name, None)


# ---------------------------------------------------------------------------
# Journal provider
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LcaRememberJournalProvider:
    """Bridge agent_lab remember.commit → LCA Session.append.

    Resolution order for the session:
      1. ``provider_config.fixture_session_name`` (looks up _FIXTURE_SESSIONS)
      2. ``provider_config.session_factory`` (module:Class form)
      3. Fallback: _NoopSession (records nothing)
    """

    _session: Any

    @classmethod
    def from_node_config(cls, config: dict[str, Any]) -> LcaRememberJournalProvider:
        cfg = config.get("provider_config") or {}
        name = cfg.get("fixture_session_name")
        if name and name in _FIXTURE_SESSIONS:
            return cls(_session=_FIXTURE_SESSIONS[name])
        factory = cfg.get("session_factory")
        if isinstance(factory, dict) and factory.get("ref"):
            session_cls = _import_dotted(factory["ref"])
            kwargs = dict(factory.get("kwargs") or {})
            return cls(_session=session_cls(**kwargs))
        # Prefer the process Session owned by session_log / act boot (single SSOT).
        try:
            from agent_lab.nodes.session_log._sink import get_session

            return cls(_session=get_session())
        except Exception:
            return cls(_session=_NoopSession())

    def append_journal(
        self,
        *,
        reflection_artifact: Artifact | None,
        observation_artifact: Artifact | None,
        decision_artifact: Artifact | None,
        admitted_artifact: Artifact | None = None,
        out_port: str = "journal_fact",
    ) -> dict[str, Artifact]:
        """Build a fact payload from turn inputs + admitted and call session.append."""
        event_data = _build_fact_data(
            reflection=reflection_artifact,
            observation=observation_artifact,
            decision=decision_artifact,
            admitted=admitted_artifact,
        )
        event = self._session.append("remember.turn_fact", event_data)
        return {
            out_port: Artifact(
                kind=ArtifactKind.FACT,
                content=_session_event_to_dict(event),
                schema_ref="journal.fact.v1",
            ),
        }


# ---------------------------------------------------------------------------
# StateStore provider
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LcaRememberStateStoreProvider:
    """Bridge agent_lab remember.snapshot → LCA StateStore.save.

    Resolution order for the state_store:
      1. ``provider_config.fixture_state_store_name`` (looks up _FIXTURE_STATE_STORES)
      2. ``provider_config.state_store_factory`` (module:Class form)
      3. Fallback: _NoopStateStore (returns a stub ref)
    """

    _state_store: Any

    @classmethod
    def from_node_config(cls, config: dict[str, Any]) -> LcaRememberStateStoreProvider:
        cfg = config.get("provider_config") or {}
        name = cfg.get("fixture_state_store_name")
        if name and name in _FIXTURE_STATE_STORES:
            return cls(_state_store=_FIXTURE_STATE_STORES[name])
        factory = cfg.get("state_store_factory")
        if isinstance(factory, dict) and factory.get("ref"):
            store_cls = _import_dotted(factory["ref"])
            kwargs = dict(factory.get("kwargs") or {})
            return cls(_state_store=store_cls(**kwargs))
        return cls(_state_store=_NoopStateStore())

    def save_state(
        self,
        *,
        journal_fact_artifact: Artifact | None,
        state_ref_port: str = "state_ref",
        signal_port: str = "remember_signal",
    ) -> dict[str, Artifact]:
        """Build an AgentState dict from journal_fact, call StateStore.save."""
        state_dict = _state_dict_from_journal(journal_fact_artifact)
        ref = _run_async(self._state_store.save(state_dict))
        return {
            state_ref_port: Artifact(
                kind=ArtifactKind.FACT,
                content={
                    "state_ref": str(ref),
                    "ts": datetime.now(UTC).isoformat(),
                },
                schema_ref="state.ref.v1",
            ),
            signal_port: Artifact(
                kind=ArtifactKind.FACT,
                content={
                    "state_ref": str(ref),
                    "phase": "remember",
                    "ts": datetime.now(UTC).isoformat(),
                },
                schema_ref="remember.signal.v1",
            ),
        }


# ---------------------------------------------------------------------------
# Defaults: noop stubs
# ---------------------------------------------------------------------------


class _NoopSession:
    """Records nothing; returns a stub event-like object."""

    def append(self, event_type: str, data: Any) -> Any:
        return _StubSessionEvent(seq=0, id="noop")


class _NoopStateStore:
    """Returns a stub ref without persisting."""

    async def save(self, state: Any) -> str:
        return "noop:stub_ref"


class _StubSessionEvent:
    """Minimal stand-in for SessionEvent in noop mode."""

    def __init__(self, seq: int, id: str) -> None:
        self.seq = seq
        self.id = id


# ---------------------------------------------------------------------------
# Helpers — artifact ⇄ dict conversions
# ---------------------------------------------------------------------------


def _build_fact_data(
    *,
    reflection: Artifact | None,
    observation: Artifact | None,
    decision: Artifact | None,
    admitted: Artifact | None = None,
) -> dict[str, Any]:
    """Merge turn artifacts + admitted candidates into one JSON-serializable dict."""
    return {
        "reflection": _artifact_content_or_none(reflection),
        "observation": _artifact_content_or_none(observation),
        "decision": _artifact_content_or_none(decision),
        "admitted": _artifact_content_or_none(admitted),
        "ts": datetime.now(UTC).isoformat(),
    }


def _artifact_content_or_none(artifact: Artifact | None) -> Any:
    if artifact is None or artifact.content is None:
        return None
    return artifact.content


def _session_event_to_dict(event: Any) -> dict[str, Any]:
    """Convert a SessionEvent (or stub) to a JSON-serializable dict."""
    return {
        "seq": getattr(event, "seq", 0),
        "id": getattr(event, "id", ""),
    }


def _state_dict_from_journal(journal_fact: Artifact | None) -> dict[str, Any]:
    """Derive a state dict payload from the journal_fact artifact."""
    if journal_fact is None or journal_fact.content is None:
        return {"journal_seq": 0}
    content = journal_fact.content
    if isinstance(content, dict):
        return {
            "journal_seq": content.get("seq", 0),
            "journal_id": content.get("id", ""),
            "ts": datetime.now(UTC).isoformat(),
        }
    return {"raw": str(content)}


def _import_dotted(ref: str) -> Any:
    if ":" in ref:
        mod, _, attr = ref.partition(":")
        obj = importlib.import_module(mod)
        return getattr(obj, attr)
    return importlib.import_module(ref)


def _run_async(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    try:
        import nest_asyncio  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "LcaRemember* provider called inside a running event loop; "
            "install nest_asyncio or invoke node.execute() outside a loop"
        ) from exc
    nest_asyncio.apply()
    return asyncio.run(coro)


__all__ = [
    "LcaRememberJournalProvider",
    "LcaRememberStateStoreProvider",
    "register_fixture_session",
    "register_fixture_state_store",
    "unregister_fixture_session",
    "unregister_fixture_state_store",
]
