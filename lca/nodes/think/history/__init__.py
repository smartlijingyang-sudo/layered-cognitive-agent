"""``lca.nodes.think.history`` — session-history assembly sub-group.

Re-exports the per-node executor and its cordis ``@plugin(...)`` carrier
so callers can do ``from lca.nodes.think.history import HistoryDeriveExecutor``
or ``from lca.nodes.think.history import setup``.
"""

from lca.nodes.think.history.assemble import HistoryDeriveExecutor, setup

__all__ = ["HistoryDeriveExecutor", "setup"]
