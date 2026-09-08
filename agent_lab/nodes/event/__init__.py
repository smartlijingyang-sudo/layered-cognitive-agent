"""event sub-package: emit_event_node, tail_event_node.

These nodes are loaded by ``agent_lab.nodes.__init__`` so their
@node(...) decorators register them with NodeRegistry at import time.
"""

from agent_lab.nodes.event.emit.plugin import EmitEventNode
from agent_lab.nodes.event.tail.plugin import TailEventNode

__all__ = ["EmitEventNode", "TailEventNode"]
