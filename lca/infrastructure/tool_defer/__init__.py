"""Deferred tool-namespace loading (Muse L1 alignment).

Per turn, only a one-line catalog per deferred namespace reaches the
model; full parameter schemas load on demand through the ``tool_search``
tool.  See ``lca/contracts/models/cognition/tool_defer.py`` for the
contracts and the package README for the full design.
"""

from lca.infrastructure.tool_defer.policy import DeferPolicy
from lca.infrastructure.tool_defer.session import (
    ToolDeferSession,
    current_defer_session,
    reset_current_defer_session,
    set_current_defer_session,
)
from lca.infrastructure.tool_defer.tool_search import (
    ToolSearchTool,
    tool_search_factory,
)

__all__ = [
    "DeferPolicy",
    "ToolDeferSession",
    "ToolSearchTool",
    "current_defer_session",
    "reset_current_defer_session",
    "set_current_defer_session",
    "tool_search_factory",
]
