"""reflect sub-package: gather_inputs, call_critic, extract_memory, write_extract.

These nodes are loaded by ``agent_lab.nodes.__init__`` so their
@node(...) decorators register them with NodeRegistry at import time.
"""

from agent_lab.nodes.reflect.call_critic.plugin import CallCriticNode
from agent_lab.nodes.reflect.combine.plugin import GatherInputsNode
from agent_lab.nodes.reflect.extract_memory.plugin import ExtractMemoryNode
from agent_lab.nodes.reflect.write_extract.plugin import WriteExtractNode

__all__ = ["CallCriticNode", "ExtractMemoryNode", "GatherInputsNode", "WriteExtractNode"]
