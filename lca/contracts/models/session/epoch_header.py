"""EpochHeader re-export for the run session writer Protocol.

Canonical ``EpochHeader`` lives at :mod:`lca_kernel.events.fold.fold`.
Re-exported here so the contracts/session namespace owns the import name.
"""

from lca_kernel.events.fold.fold import EpochHeader

__all__ = ["EpochHeader"]
