"""Unified model-visible message read path (ADR-0193)."""

from __future__ import annotations

from typing import Any

from lca.plugins.session.runtime.messages.messages import derive_messages

__all__ = ["model_visible_messages"]


def model_visible_messages(session: Any, *, registry: Any | None = None) -> list[dict[str, Any]]:
    """Read model-visible messages: projection when registry attached, else pure fold."""
    reg = registry if registry is not None else getattr(session, "_projections", None)
    if reg is not None:
        snap = reg.snapshot(session, keys=["model_visible"])
        view = snap.values.get("model_visible")
        if isinstance(view, dict):
            raw = view.get("messages")
            if isinstance(raw, list):
                return [dict(item) for item in raw if isinstance(item, dict)]
    return derive_messages(session.snapshot_events())
