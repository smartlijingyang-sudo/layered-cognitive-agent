# COMPAT(owner: ADR-0195 P3-02, from: handlers/runs/execute/environment_bindings.py,
#         to: carrier/runs/execute/environment_bindings.py,
#         delete_when: rg handlers/runs/execute/environment_bindings 生产 import = 0,
#         forbidden_new_usage: 新 carrier 代码不得 import 本路径)
"""Shim — see ``carrier/runs/execute/environment_bindings.py``."""

from lca.plugins.transport.webserver.carrier.runs.execute.environment_bindings import *  # noqa: F403
from lca.plugins.transport.webserver.carrier.runs.execute.environment_bindings import (
    RunProviders,
    resolve_bindings,
    resolve_descriptor_registry,
    resolve_driver,
    resolve_run_providers,
)

__all__ = [
    "RunProviders",
    "resolve_bindings",
    "resolve_descriptor_registry",
    "resolve_driver",
    "resolve_run_providers",
]
