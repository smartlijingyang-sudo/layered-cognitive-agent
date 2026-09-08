# PR-B — Tool registry provider (stub marker for PR-B)
"""lab.tool_registry provider — stub for PR-B.

PR-D will fully implement YAML loading + registration with SimpleToolRegistry.
Until then, this is just a marker so capability checks succeed.
"""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_marker = {"id": "lab.tool_registry", "stage": "composition"}
_LAB_HOOKS["lab.tool_registry"] = _marker

__all__ = ["_marker"]