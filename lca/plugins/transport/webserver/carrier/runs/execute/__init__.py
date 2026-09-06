"""execute subpackage — carrier run trigger surface (ADR-0195 P3-02).

Re-exports the carrier surface from the facade module. Legacy import path:
Legacy import path ``handlers/runs/execute`` removed (ADR-0195 P3-02); use this package.

``RunLifecycleCoordinator`` is lazy-loaded to avoid circular import with
``carrier/runs/lifecycle`` (lifecycle imports ``execution_environment``).
"""

from __future__ import annotations

from lca.plugins.transport.webserver.carrier.runs.execute.execute import (
    create_run_session,
    execute_run,
    resume_run,
    schedule_run,
)

__all__ = [
    "RunLifecycleCoordinator",
    "create_run_session",
    "execute_run",
    "resume_run",
    "schedule_run",
]


def __getattr__(name: str):
    if name == "RunLifecycleCoordinator":
        from lca.plugins.transport.webserver.carrier.runs.lifecycle.lifecycle import (
            RunLifecycleCoordinator,
        )

        globals()["RunLifecycleCoordinator"] = RunLifecycleCoordinator
        return RunLifecycleCoordinator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
