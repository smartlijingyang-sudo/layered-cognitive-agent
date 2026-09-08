"""Singleton LCA Session holder for agent_lab runtime.

The Session is the SOLE fact-write seam per ADR-0186/0191/0194. agent_lab
nodes access it through this holder so the framework boots without
requiring every caller to pass a Session explicitly.

Pattern mirrors agent_lab.tools.registry (the named-tool inventory):
  - configure_session(session): set at boot
  - session(): lazy-build a default Session if not configured

Both the runner and tests call configure_session() at boot. The default
fallback is a real LCA Session (in-memory, no durability) — sufficient
for ad-hoc demos and integration tests; production profiles inject a
durable-backed Session (e.g. backed by JSONL).
"""

from __future__ import annotations

from typing import Any

_SESSION_SINGLETON: dict[str, Any] = {}


def configure_session(session: Any) -> None:
    """Set the singleton Session. Called by the runner at boot."""
    _SESSION_SINGLETON["value"] = session


def session() -> Any:
    """Return the configured Session; build a default in-memory one if absent."""
    sess = _SESSION_SINGLETON.get("value")
    if sess is not None:
        return sess
    from lca.session.append import Session
    sess = Session(session_id="agent_lab_default")
    _SESSION_SINGLETON["value"] = sess
    return sess


__all__ = ["configure_session", "session"]
