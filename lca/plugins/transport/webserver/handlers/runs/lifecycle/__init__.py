"""lifecycle subpackage of lca.plugins.transport.webserver.handlers.runs — split per ADR-0105 §11.2.

Re-exports RunLifecycleCoordinator via lazy ``__getattr__`` to break the
circular import with lca.plugins.transport.webserver.handlers.runs.execute (which loads this subpackage
during its own ``__init__.py`` execution).
"""

from __future__ import annotations


def __getattr__(name: str):
    if name in ("RunLifecycleCoordinator", "ensure_session_hub"):
        from lca.plugins.transport.webserver.handlers.runs.lifecycle.lifecycle import (
            RunLifecycleCoordinator,
            ensure_session_hub,
        )

        # Bind onto the module so subsequent attribute access is fast.
        globals()["RunLifecycleCoordinator"] = RunLifecycleCoordinator
        globals()["ensure_session_hub"] = ensure_session_hub
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["RunLifecycleCoordinator", "ensure_session_hub"]
