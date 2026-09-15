"""EventRef re-export for the run session writer Protocol.

The canonical ``EventRef`` lives at :mod:`lca_kernel.events.bus.bus`. This
module is a thin re-export so the contracts/session namespace can reference
a single name without depending on the kernel import path.
"""

from lca_kernel.events.bus.bus import EventRef

__all__ = ["EventRef"]
