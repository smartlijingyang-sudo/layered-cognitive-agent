# PR-B — Body provider plugin (PR-D stub)
"""lab.body provider — stub marker for PR-B.

PR-D will fully implement this provider, composing SimpleBody +
PipelineSafeExecutor + Transport. Until then, this is just a marker
so the loader allow-list is consistent and capability checks succeed.
"""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_marker = {"id": "lab.body", "stage": "composition"}
_LAB_HOOKS["lab.body"] = _marker

__all__ = ["_marker"]