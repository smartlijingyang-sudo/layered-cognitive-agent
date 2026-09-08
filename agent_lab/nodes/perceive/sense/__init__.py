"""sense package — triggers @node registration for all sense nodes."""
from agent_lab.nodes.perceive.sense.user.plugin import SenseUser
from agent_lab.nodes.perceive.sense.tool_results.plugin import SenseToolResults
from agent_lab.nodes.perceive.sense.memory.plugin import SenseMemory

__all__ = ["SenseUser", "SenseToolResults", "SenseMemory"]
