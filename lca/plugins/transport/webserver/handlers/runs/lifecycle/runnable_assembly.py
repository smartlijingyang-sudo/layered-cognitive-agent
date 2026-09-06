# COMPAT(owner: ADR-0195 P3-04, from: handlers/runs/lifecycle/runnable_assembly.py,
#         to: carrier/runs/lifecycle/runnable_assembly.py,
#         delete_when: rg handlers/runs/lifecycle/runnable_assembly 生产 import = 0,
#         forbidden_new_usage: 新 carrier 代码不得 import 本路径)
"""Shim — see ``carrier/runs/lifecycle/runnable_assembly.py``."""

from lca.plugins.transport.webserver.carrier.runs.lifecycle.runnable_assembly import *  # noqa: F403
from lca.plugins.transport.webserver.carrier.runs.lifecycle.runnable_assembly import (
    CognitiveRunnableAssembler,
    LlmResolver,
    RunnableAssemblyRequest,
    RunnableBuildRequest,
    tools_from_scope,
)

__all__ = [
    "CognitiveRunnableAssembler",
    "LlmResolver",
    "RunnableAssemblyRequest",
    "RunnableBuildRequest",
    "tools_from_scope",
]
