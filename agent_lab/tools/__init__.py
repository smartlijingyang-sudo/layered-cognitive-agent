"""agent_lab/tools — non-executable tool registry.

This is a *named-tool lookup* layer, not a graph.  It holds the set of
Tools the agent loop is allowed to dispatch, and nothing else:

  - it does NOT define topology (nodes/edges are not its concern)
  - it does NOT execute anything (Tools execute in SimpleSafeExecutor)
  - it does NOT enforce grants (that's the ``grant_check`` node + the
    caller's ``ToolPermissionManifest``)

The single YAML it reads is ``tools/registry.yaml``: each entry says
"this tool is available; here's how to build it (``module:Factory``)".
The dispatch graph picks a *range* of names out of this set.
"""

from agent_lab.tools.registry import ToolNotFoundError, ToolRegistry

__all__ = ["ToolNotFoundError", "ToolRegistry"]
