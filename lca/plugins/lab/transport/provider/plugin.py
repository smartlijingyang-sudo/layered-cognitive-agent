# PR-B — Transport provider (stub marker for PR-B)
"""lab.transport provider — stub for PR-B.

PR-D will fully implement InternalTransport + lab_echo registration.
Until then, this is just a marker.
"""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_marker = {"id": "lab.transport", "stage": "composition"}
_LAB_HOOKS["lab.transport"] = _marker

__all__ = ["_marker"]