# COMPAT(owner: ADR-0195 P3-02, from: handlers/runs/execute,
#         to: carrier/runs/execute,
#         delete_when: rg handlers/runs/execute 生产 import = 0,
#         forbidden_new_usage: 新 carrier 代码不得 import 本路径)
"""Shim — re-exports ``carrier/runs/execute``."""

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
