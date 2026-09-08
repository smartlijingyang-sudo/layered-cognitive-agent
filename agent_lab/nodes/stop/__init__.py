"""stop sub-package: evaluate_stop node.

These nodes are loaded by ``agent_lab.nodes.__init__`` so their
@node(...) decorators register them with NodeRegistry at import time.
"""

from agent_lab.nodes.stop.evaluate_stop.plugin import EvaluateStopNode

__all__ = ["EvaluateStopNode"]
