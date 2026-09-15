"""``lca.nodes.think.history`` — session-history assembly sub-group.

Re-exports the per-node carrier at the sub-group level so callers can do
``from lca.nodes.think.history import history_assemble``.
"""

from lca.nodes.think.history.assemble import history_assemble

__all__ = ["history_assemble"]
