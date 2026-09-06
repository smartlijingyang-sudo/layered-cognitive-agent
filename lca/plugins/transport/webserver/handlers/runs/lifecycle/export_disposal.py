# COMPAT(owner: ADR-0195 P3-04, from: handlers/runs/lifecycle/export_disposal.py,
#         to: carrier/runs/lifecycle/export_disposal.py,
#         delete_when: rg handlers/runs/lifecycle/export_disposal 生产 import = 0,
#         forbidden_new_usage: 新 carrier 代码不得 import 本路径)
"""Shim — see ``carrier/runs/lifecycle/export_disposal.py``."""

from lca.plugins.transport.webserver.carrier.runs.lifecycle.export_disposal import *  # noqa: F403
from lca.plugins.transport.webserver.carrier.runs.lifecycle.export_disposal import (
    EXPORT_DISPOSE_TIMEOUT_S,
    dispose_export,
)

__all__ = ["EXPORT_DISPOSE_TIMEOUT_S", "dispose_export"]
