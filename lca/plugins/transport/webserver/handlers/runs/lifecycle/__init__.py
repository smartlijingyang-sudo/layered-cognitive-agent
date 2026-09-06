# COMPAT(owner: ADR-0195 P3-04, from: handlers/runs/lifecycle,
#         to: carrier/runs/lifecycle,
#         delete_when: rg handlers/runs/lifecycle 生产 import = 0,
#         forbidden_new_usage: 新 carrier 代码不得 import 本路径)
"""Shim — re-exports ``carrier/runs/lifecycle``."""

from __future__ import annotations


def __getattr__(name: str):
    if name in ("RunLifecycleCoordinator", "ensure_session_hub"):
        from lca.plugins.transport.webserver.carrier.runs.lifecycle.lifecycle import (
            RunLifecycleCoordinator,
            ensure_session_hub,
        )

        globals()["RunLifecycleCoordinator"] = RunLifecycleCoordinator
        globals()["ensure_session_hub"] = ensure_session_hub
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["RunLifecycleCoordinator", "ensure_session_hub"]
