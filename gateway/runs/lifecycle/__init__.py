"""lifecycle subpackage of gateway.runs — split per ADR-0105 §11.2.

Re-exports RunLifecycleCoordinator for callers using
``from gateway.runs.lifecycle import RunLifecycleCoordinator``.
"""

from gateway.runs.lifecycle.lifecycle import (
    RunLifecycleCoordinator,
    ensure_session_hub,
)

__all__ = ["RunLifecycleCoordinator", "ensure_session_hub"]
