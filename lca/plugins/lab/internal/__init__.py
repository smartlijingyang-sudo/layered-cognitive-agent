"""Internal helpers for the LCA lab plugin family.

PR-A.2 — hook helper 私有化；PR-A.3 — 引入 ``loader`` 装载
``lca.plugins.lab.*`` @plugin carriers。本模块仅供 lca.plugins.lab.*
plugin 与 agent_lab graph/compile / runtime/runner 在过渡期使用；
PR-D 整体删除 agent_lab.plugins.base 后,本模块依旧承载 hook helper
与 loader。

Public consumers must not import from this package directly. The symbols
here are wired into the @plugin setup() / runner / compiler paths; they
are not a stable API surface.
"""

from lca.plugins.lab.internal.hooks import (
    Bind,
    HookContext,
    HookEvent,
    fanout_hooks,
)
from lca.plugins.lab.internal.loader import (
    get_instance,
    known_subpackages,
    list_ids,
    load_all,
    registered_lca_packages,
    resolve_plugin,
    reset_for_tests,
)

__all__ = [
    "Bind",
    "HookContext",
    "HookEvent",
    "fanout_hooks",
    "get_instance",
    "known_subpackages",
    "list_ids",
    "load_all",
    "registered_lca_packages",
    "resolve_plugin",
    "reset_for_tests",
]
