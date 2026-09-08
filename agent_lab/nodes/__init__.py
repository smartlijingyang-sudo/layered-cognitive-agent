"""nodes — ant-worker library. Each node: single execute(inputs) -> outputs.

No if/else business logic inside nodes. Business goes into routing nodes
(route_on / barrier / join) or into config.
"""

import agent_lab.nodes.control
import agent_lab.nodes.llm
import agent_lab.nodes.mv

# Auto-import node modules so registrations run.
import agent_lab.nodes.passthrough
import agent_lab.nodes.tool  # noqa: F401
from agent_lab.nodes.base import Node, NodeRegistry, invoke, register

__all__ = ["Node", "NodeRegistry", "invoke", "register"]
