"""Lifecycle state contract for delegated subagents."""

from __future__ import annotations

from enum import StrEnum


class SubagentLifecycle(StrEnum):
    ACTIVE = "active"
    DRAINING = "draining"
    DISPOSED = "disposed"
    DISPOSE_FAILED = "dispose_failed"

    def can_accept_work(self) -> bool:
        return self is SubagentLifecycle.ACTIVE


__all__ = ["SubagentLifecycle"]
