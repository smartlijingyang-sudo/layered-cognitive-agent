"""Plugin base — thin compat shim for hook helper re-exports.

.. deprecated::
    This module is a PR-D final cleanup compat shim. The old
    ``GraphPlugin`` dataclass and ``register_plugin`` no-op decorator
    have been removed (ADR-0209 §1.1 + PR-D final 1/2 + 2/2).
    Hook helper re-exports remain so legacy call sites
    (``from agent_lab.plugins.base import HookContext`` etc.) keep
    working; new code should import from
    ``lca.plugins.lab.internal.hooks`` directly.

    delete-when: all consumers (lca/, scripts/, hooks/) import the 4
    hook helpers from ``lca.plugins.lab.internal.hooks``. The
    profile_loader is already on the new path; only this shim remains.
"""

from lca.plugins.lab.internal.hooks import (
    Bind,
    HookContext,
    HookEvent,
    fanout_hooks,
)

__all__ = [
    "Bind",
    "HookContext",
    "HookEvent",
    "fanout_hooks",
]